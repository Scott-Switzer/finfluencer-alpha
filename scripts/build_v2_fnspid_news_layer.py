"""Build a historical news layer using the static FNSPID dataset."""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import news_provider_utils as npu  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "news_confound_master" / "fnspid"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NOISY_SYMBOLS = {"NOW", "SQ", "A", "T", "F", "G", "C", "K", "O", "P"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FNSPID static news layer.")
    parser.add_argument("--limit-rows", type=int, default=None)
    parser.add_argument("--skip-hf", action="store_true", help="Skip Hugging Face streaming to avoid network hangs.")
    return parser.parse_args()


def load_fnspid_local() -> pd.DataFrame | None:
    candidates = [
        utils.REPO_ROOT / "data" / "private" / "fnspid",
        utils.REPO_ROOT / "data" / "external" / "fnspid",
        Path("/workspace/data/private/fnspid"),
        Path("/workspace/FIN496CAPSTONE/data/private/fnspid"),
    ]
    files: list[Path] = []
    for folder in candidates:
        if folder.exists():
            files.extend(folder.glob("*.csv"))
            files.extend(folder.glob("*.parquet"))

    if not files:
        print("No local FNSPID files found in candidates.")
        return None

    pieces: list[pd.DataFrame] = []
    for path in sorted(files):
        print(f"Loading local FNSPID file: {path}")
        try:
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path)
            pieces.append(df)
        except Exception as exc:
            print(f"Error loading {path}: {exc}")
    if not pieces:
        return None
    return pd.concat(pieces, ignore_index=True)


def load_fnspid_huggingface(limit_rows: int | None = None) -> pd.DataFrame | None:
    print("Attempting to stream Zihan1004/FNSPID from Hugging Face...")
    try:
        import datasets
    except ImportError:
        print("Hugging Face datasets library not installed.")
        return None

    try:
        # Stream the qualitative Stock_news component from the dataset
        # Zihan1004/FNSPID has Stock_news subset or main
        dataset = datasets.load_dataset(
            "Zihan1004/FNSPID",
            # name=default config 
            split="train",
            streaming=True,
        )
    except Exception as exc:
        print(f"Could not load dataset from HF: {exc}")
        return None

    records = []
    print("Streaming records from HF...")
    try:
        count = 0
        for row in dataset:
            records.append(row)
            count += 1
            if count % 10000 == 0:
                print(f"Streamed {count} records...")
            if limit_rows is not None and count >= limit_rows:
                break
    except Exception as exc:
        print(f"Error while streaming dataset: {exc}")
        if not records:
            return None

    return pd.DataFrame(records)


def narrow_fnspid_to_events(news: pd.DataFrame, ticker_col: str, date_col: str, events: pd.DataFrame) -> pd.DataFrame:
    """Drop rows outside project tickers and wider event-date range to limit RAM."""
    tickers = {str(t).upper().strip() for t in events["ticker"].dropna().unique()}
    news = news.copy()
    news["_parsed_date"] = news[date_col].map(npu.parse_date)
    news = news.dropna(subset=["_parsed_date"])
    news["_ticker_upper"] = news[ticker_col].astype(str).str.upper().str.strip()
    news = news[news["_ticker_upper"].isin(tickers)]
    ed = pd.to_datetime(events["event_date"], errors="coerce").dropna()
    if ed.empty:
        return news
    dmin = ed.min().date() - timedelta(days=14)
    dmax = ed.max().date() + timedelta(days=14)
    return news[(news["_parsed_date"] >= dmin) & (news["_parsed_date"] <= dmax)]


def process_fnspid(events: pd.DataFrame, news: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Identify symbol and date columns
    ticker_col = None
    for c in ["Stock_symbol", "ticker", "symbol", "stock_symbol", "Ticker", "Symbol"]:
        if c in news.columns:
            ticker_col = c
            break

    date_col = None
    for c in ["Date", "date", "published_at", "publishedDate", "time_published", "published"]:
        if c in news.columns:
            date_col = c
            break

    title_col = None
    for c in ["Article_title", "title", "headline", "headline_text", "headline_text_only"]:
        if c in news.columns:
            title_col = c
            break

    sentiment_col = None
    for c in ["sentiment", "sentiment_score", "mean_sentiment"]:
        if c in news.columns:
            sentiment_col = c
            break

    source_col = None
    for c in ["Publisher", "source", "publisher", "source_name", "publisher_name"]:
        if c in news.columns:
            source_col = c
            break

    if ticker_col is None or date_col is None:
        raise ValueError(f"Could not find ticker ({ticker_col}) or date ({date_col}) columns in news data.")

    news = narrow_fnspid_to_events(news, ticker_col, date_col, events)

    # Deduplicate
    dedup_cols = ["_ticker_upper", "_parsed_date"]
    if title_col in news.columns:
        news["_title_hash"] = news[title_col].astype(str).str.strip().str.lower()
        dedup_cols.append("_title_hash")
    if source_col in news.columns:
        dedup_cols.append(source_col)
    url_col = next((c for c in ("Url", "url", "link", "article_url") if c in news.columns), None)
    if url_col:
        dedup_cols.append(url_col)
    news = news.drop_duplicates(subset=dedup_cols)

    by_ticker = {t: g for t, g in news.groupby("_ticker_upper")}

    derived_rows = []
    for _, event in events.iterrows():
        event_id = int(event.event_id)
        ticker = str(event.ticker).upper().strip()
        event_date = npu.parse_date(event.event_date)

        row = {
            "event_id": event_id,
            "ticker": ticker,
            "event_date": event.event_date,
            "fnspid_coverage_available": True,
            "fnspid_news_hit": False,
            "fnspid_news_count_pre_1d": 0,
            "fnspid_news_count_post_1d": 0,
            "fnspid_news_count_pre_3d": 0,
            "fnspid_news_count_post_3d": 0,
            "fnspid_news_count_pre_7d": 0,
            "fnspid_news_count_post_7d": 0,
            "fnspid_mean_sentiment_pre_3d": 0.0,
            "fnspid_mean_sentiment_post_3d": 0.0,
            "fnspid_max_abs_sentiment_pre_3d": 0.0,
            "fnspid_source_count_pre_7d": 0,
            "fnspid_unique_title_count_pre_7d": 0,
            "fnspid_first_article_date_near_event": "",
            "fnspid_last_article_date_near_event": "",
        }

        if event_date is None or ticker in NOISY_SYMBOLS:
            derived_rows.append(row)
            continue

        ticker_news = by_ticker.get(ticker)
        if ticker_news is None or ticker_news.empty:
            derived_rows.append(row)
            continue

        # Check event window (+/- 7 days)
        start = event_date - timedelta(days=7)
        end = event_date + timedelta(days=7)
        window_news = ticker_news[(ticker_news["_parsed_date"] >= start) & (ticker_news["_parsed_date"] <= end)].copy()

        if window_news.empty:
            derived_rows.append(row)
            continue

        row["fnspid_news_hit"] = True
        dates_near = sorted(window_news["_parsed_date"].tolist())
        row["fnspid_first_article_date_near_event"] = dates_near[0].isoformat()
        row["fnspid_last_article_date_near_event"] = dates_near[-1].isoformat()

        # Counts
        for days in (1, 3, 7):
            pre_dates = window_news[
                (window_news["_parsed_date"] >= event_date - timedelta(days=days)) &
                (window_news["_parsed_date"] < event_date)
            ]
            post_dates = window_news[
                (window_news["_parsed_date"] >= event_date) &
                (window_news["_parsed_date"] <= event_date + timedelta(days=days))
            ]
            row[f"fnspid_news_count_pre_{days}d"] = len(pre_dates)
            row[f"fnspid_news_count_post_{days}d"] = len(post_dates)

            if days == 3 and sentiment_col in window_news.columns:
                pre_sent = pd.to_numeric(pre_dates[sentiment_col], errors="coerce").dropna()
                post_sent = pd.to_numeric(post_dates[sentiment_col], errors="coerce").dropna()
                if not pre_sent.empty:
                    row["fnspid_mean_sentiment_pre_3d"] = float(pre_sent.mean())
                    row["fnspid_max_abs_sentiment_pre_3d"] = float(pre_sent.abs().max())
                if not post_sent.empty:
                    row["fnspid_mean_sentiment_post_3d"] = float(post_sent.mean())

            if days == 7:
                if source_col in window_news.columns:
                    row["fnspid_source_count_pre_7d"] = int(pre_dates[source_col].nunique())
                if title_col in window_news.columns:
                    row["fnspid_unique_title_count_pre_7d"] = int(pre_dates[title_col].nunique())

        derived_rows.append(row)

    panel = pd.DataFrame(derived_rows)

    # Aggregates
    by_ticker_summary = (
        panel.groupby("ticker")
        .agg(
            events=("event_id", "count"),
            hits=("fnspid_news_hit", "sum"),
            mean_pre_7d=("fnspid_news_count_pre_7d", "mean"),
        )
        .reset_index()
    )

    panel["year"] = pd.to_datetime(panel["event_date"], errors="coerce").dt.year
    by_year_summary = (
        panel.groupby("year")
        .agg(
            events=("event_id", "count"),
            hits=("fnspid_news_hit", "sum"),
            mean_pre_7d=("fnspid_news_count_pre_7d", "mean"),
        )
        .reset_index()
    )

    provider_status = pd.DataFrame([
        {
            "provider": "fnspid_news",
            "status": "success",
            "loaded_records": len(news),
            "events_checked": len(events),
            "hits_found": int(panel["fnspid_news_hit"].sum()),
        }
    ])

    return panel, by_ticker_summary, by_year_summary, provider_status


def write_empty_status(events: pd.DataFrame, status_str: str) -> None:
    derived_rows = []
    for _, event in events.iterrows():
        derived_rows.append({
            "event_id": int(event.event_id),
            "ticker": str(event.ticker).upper().strip(),
            "event_date": event.event_date,
            "fnspid_coverage_available": False,
            "fnspid_news_hit": False,
            "fnspid_news_count_pre_1d": 0,
            "fnspid_news_count_post_1d": 0,
            "fnspid_news_count_pre_3d": 0,
            "fnspid_news_count_post_3d": 0,
            "fnspid_news_count_pre_7d": 0,
            "fnspid_news_count_post_7d": 0,
            "fnspid_mean_sentiment_pre_3d": 0.0,
            "fnspid_mean_sentiment_post_3d": 0.0,
            "fnspid_max_abs_sentiment_pre_3d": 0.0,
            "fnspid_source_count_pre_7d": 0,
            "fnspid_unique_title_count_pre_7d": 0,
            "fnspid_first_article_date_near_event": "",
            "fnspid_last_article_date_near_event": "",
        })
    pd.DataFrame(derived_rows).to_csv(OUT_DIR / "fnspid_derived_event_panel.csv", index=False)
    pd.DataFrame(columns=["ticker", "events", "hits", "mean_pre_7d"]).to_csv(OUT_DIR / "fnspid_by_ticker.csv", index=False)
    pd.DataFrame(columns=["year", "events", "hits", "mean_pre_7d"]).to_csv(OUT_DIR / "fnspid_by_year.csv", index=False)

    provider_status = pd.DataFrame([
        {
            "provider": "fnspid_news",
            "status": status_str,
            "loaded_records": 0,
            "events_checked": len(events),
            "hits_found": 0,
        }
    ])
    provider_status.to_csv(OUT_DIR / "fnspid_provider_status.csv", index=False)

    summary_md = f"""# FNSPID News Layer Summary

- **Status**: {status_str}
- **Coverage Available**: False
- **Events Checked**: {len(events)}
- **Hits Found**: 0

*Note: FNSPID raw files could not be loaded due to memory/storage/network constraints or missing files.*
"""
    (OUT_DIR / "fnspid_summary.md").write_text(summary_md)
    print(f"Wrote empty/failed status: {status_str}")


def main() -> None:
    args = parse_args()
    events = utils.event_manifest().copy()
    print(f"Loaded {len(events)} events from manifest.")

    # 1. Load local private/external caches
    news = load_fnspid_local()

    # 2. Try streaming from HF if local fails and --skip-hf is not provided
    if news is None:
        if args.skip_hf:
            print("Skipping Hugging Face streaming due to --skip-hf flag.")
        else:
            news = load_fnspid_huggingface(args.limit_rows)

    if news is None:
        write_empty_status(events, "missing_or_failed_loading")
        return

    print(f"Successfully loaded news dataset. Total rows: {len(news)}")

    try:
        panel, by_ticker, by_year, status = process_fnspid(events, news)
        panel.to_csv(OUT_DIR / "fnspid_derived_event_panel.csv", index=False)
        by_ticker.to_csv(OUT_DIR / "fnspid_by_ticker.csv", index=False)
        by_year.to_csv(OUT_DIR / "fnspid_by_year.csv", index=False)
        status.to_csv(OUT_DIR / "fnspid_provider_status.csv", index=False)

        summary_md = f"""# FNSPID News Layer Summary

- **Status**: success
- **Coverage Available**: True
- **Events Checked**: {len(events)}
- **Hits Found**: {int(panel["fnspid_news_hit"].sum())}
- **Unique Tickers with news**: {int(by_ticker[by_ticker["hits"] > 0]["ticker"].nunique())}

## Year Coverage Summary

{utils.md_table(by_year.to_dict("records"))}
"""
        (OUT_DIR / "fnspid_summary.md").write_text(summary_md)
        print("Successfully built FNSPID news layer outputs!")
    except Exception as exc:
        print(f"Error while processing FNSPID news data: {exc}")
        write_empty_status(events, f"processing_failed: {str(exc)}")


if __name__ == "__main__":
    main()
