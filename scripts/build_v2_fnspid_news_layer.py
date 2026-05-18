"""Build a historical news layer using the FNSPID dataset (HF Dataset Server probe + Hub CSV stream)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import TextIOWrapper
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import news_provider_utils as npu  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

DATASETS_SERVER = "https://datasets-server.huggingface.co"
FNSPID_DATASET = "Zihan1004/FNSPID"
DEFAULT_CSV_URL = (
    "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv"
)
SECONDARY_CSV_URL = (
    "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/All_external.csv"
)

OUT_DIR = utils.OUT_DIR / "news_confound_master" / "fnspid"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NOISY_SYMBOLS = {"NOW", "SQ", "A", "T", "F", "G", "C", "K", "O", "P"}
CANARY_TICKERS = frozenset({"AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META"})
MAX_ARTICLES_PER_EVENT = 500

PRIMARY_CSV_BASENAME = "nasdaq_exteral_data.csv"
SECONDARY_CSV_BASENAME = "All_external.csv"
SPINE_PATH = OUT_DIR / "fnspid_article_spine.csv"
STREAM_META_PATH = OUT_DIR / "fnspid_stream_meta.json"

PANEL_PATH = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FNSPID static news layer.")
    parser.add_argument("--limit-rows", type=int, default=None, help="Legacy HF datasets stream cap.")
    parser.add_argument("--skip-hf", action="store_true", help="Skip Hugging Face network access.")
    parser.add_argument("--csv-url", default=DEFAULT_CSV_URL, help="Primary CSV URL to stream.")
    parser.add_argument(
        "--also-secondary-csv",
        action="store_true",
        help="Stream All_external.csv after primary for more coverage.",
    )
    parser.add_argument(
        "--reuse-primary-spine",
        action="store_true",
        help="With --also-secondary-csv, skip re-streaming the primary CSV; restore primary hits from fnspid_article_spine.csv and stream only All_external.csv.",
    )
    parser.add_argument("--max-chunks", type=int, default=None, help="Stop after N chunks (debug).")
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument(
        "--legacy-stream",
        action="store_true",
        help="Use datasets.load_dataset streaming only (old path).",
    )
    return parser.parse_args()


def _http_get_json(url: str, timeout: float = 120.0) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "FIN496-fnspid-layer/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def probe_dataset_server(dataset: str = FNSPID_DATASET) -> dict[str, Any]:
    out: dict[str, Any] = {"dataset": dataset, "errors": []}
    try:
        out["is_valid"] = _http_get_json(f"{DATASETS_SERVER}/is-valid?dataset={quote(dataset, safe='')}")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        out["errors"].append(f"is-valid: {exc}")
        out["is_valid"] = {}
    try:
        out["splits"] = _http_get_json(f"{DATASETS_SERVER}/splits?dataset={quote(dataset, safe='')}")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        out["errors"].append(f"splits: {exc}")
        out["splits"] = {}
    return out


def fetch_first_rows(dataset: str, config: str, split: str) -> dict[str, Any]:
    q = urlencode({"dataset": dataset, "config": config, "split": split})
    return _http_get_json(f"{DATASETS_SERVER}/first-rows?{q}")


def try_api_path(path: str, params: dict[str, Any]) -> dict[str, Any]:
    q = urlencode(params)
    try:
        return _http_get_json(f"{DATASETS_SERVER}/{path}?{q}")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def canary_counts_from_first_rows(rows_payload: dict[str, Any]) -> dict[str, Any]:
    preview_rows = rows_payload.get("rows") or []
    by_ticker: dict[str, int] = defaultdict(int)
    for item in preview_rows:
        row = item.get("row") or {}
        sym = str(row.get("Stock_symbol", "") or "").upper().strip()
        if sym in CANARY_TICKERS:
            by_ticker[sym] += 1
    return {"canary_tickers_seen_in_first_preview": dict(by_ticker), "preview_row_count": len(preview_rows)}


def _article_key(url: str, d: date, title: str) -> str:
    u = str(url or "").strip()[:500]
    return hashlib.sha256(f"{u}|{d.isoformat()}|{title[:160]}".encode()).hexdigest()[:28]


@dataclass
class EventArticleState:
    event_id: int
    ticker: str
    event_date: str
    ed: date
    dedupe: set[str] = field(default_factory=set)
    # Compact row: event-window article date, dedupe key (url|date|title hash), Hub CSV basename.
    articles: list[tuple[date, str, str]] = field(default_factory=list)

    def add_if_in_window(self, d: date, title: str, publisher: str, url: str, source_file: str) -> bool:
        if not (self.ed - timedelta(days=7) <= d <= self.ed + timedelta(days=7)):
            return False
        if len(self.articles) >= MAX_ARTICLES_PER_EVENT:
            return False
        key = _article_key(url, d, title)
        if key in self.dedupe:
            return False
        self.dedupe.add(key)
        self.articles.append((d, key, source_file))
        return True

    def add_restored_key(self, d: date, key: str, source_file: str) -> bool:
        if not (self.ed - timedelta(days=7) <= d <= self.ed + timedelta(days=7)):
            return False
        if len(self.articles) >= MAX_ARTICLES_PER_EVENT:
            return False
        if key in self.dedupe:
            return False
        self.dedupe.add(key)
        self.articles.append((d, key, source_file))
        return True

    def source_hit_category(self) -> str:
        srcs = {s for _, _, s in self.articles}
        p = PRIMARY_CSV_BASENAME in srcs
        s = SECONDARY_CSV_BASENAME in srcs
        if not self.articles:
            return "none"
        if p and s:
            return "both"
        if p:
            return "primary_only"
        if s:
            return "secondary_only"
        return "none"

    def finalize_counts(self) -> dict[str, Any]:
        arts = self.articles
        ed = self.ed

        def cnt(pred: Any) -> int:
            return sum(1 for d, _, _ in arts if pred(d))

        n_pri = sum(1 for _, _, s in arts if s == PRIMARY_CSV_BASENAME)
        n_sec = sum(1 for _, _, s in arts if s == SECONDARY_CSV_BASENAME)
        out = {
            "fnspid_hit_pre_7d": cnt(lambda d: ed - timedelta(days=7) <= d <= ed - timedelta(days=1)),
            "fnspid_hit_day0": cnt(lambda d: d == ed),
            "fnspid_hit_post_1d": cnt(lambda d: ed <= d <= ed + timedelta(days=1)),
            "fnspid_hit_post_3d": cnt(lambda d: ed <= d <= ed + timedelta(days=3)),
            "fnspid_hit_post_7d": cnt(lambda d: ed <= d <= ed + timedelta(days=7)),
            "fnspid_total_hits_window": len(arts),
            "fnspid_unique_publishers_window": 0,
            "fnspid_primary_article_count": n_pri,
            "fnspid_secondary_article_count": n_sec,
            "fnspid_hit_sources": self.source_hit_category(),
        }
        titles = [f"k:{key[:10]}" for _, key, _ in arts[:5]]
        out["fnspid_sample_titles_redacted_or_short"] = " | ".join(titles)
        return out

    def legacy_fnspid_counts(self) -> dict[str, int]:
        """Match build_v2_public_news_confound_master pre/post {1,3,7}d definitions."""
        ed = self.ed
        arts = self.articles

        def npre(days: int) -> int:
            lo = ed - timedelta(days=days)
            return sum(1 for d, _, _ in arts if lo <= d < ed)

        def npost(days: int) -> int:
            hi = ed + timedelta(days=days)
            return sum(1 for d, _, _ in arts if ed <= d <= hi)

        return {
            "fnspid_news_count_pre_1d": npre(1),
            "fnspid_news_count_post_1d": npost(1),
            "fnspid_news_count_pre_3d": npre(3),
            "fnspid_news_count_post_3d": npost(3),
            "fnspid_news_count_pre_7d": npre(7),
            "fnspid_news_count_post_7d": npost(7),
        }


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
        return None
    pieces: list[pd.DataFrame] = []
    for path in sorted(files):
        try:
            if path.suffix == ".parquet":
                pieces.append(pd.read_parquet(path))
            else:
                pieces.append(pd.read_csv(path))
        except Exception:
            continue
    if not pieces:
        return None
    return pd.concat(pieces, ignore_index=True)


def load_fnspid_huggingface(limit_rows: int | None = None) -> pd.DataFrame | None:
    try:
        import datasets
    except ImportError:
        return None
    try:
        dataset = datasets.load_dataset("Zihan1004/FNSPID", split="train", streaming=True)
    except Exception:
        return None
    records: list[dict[str, Any]] = []
    try:
        for i, row in enumerate(dataset):
            records.append(row)
            if limit_rows is not None and i + 1 >= limit_rows:
                break
    except Exception:
        if not records:
            return None
    return pd.DataFrame(records)


def narrow_fnspid_to_events(news: pd.DataFrame, ticker_col: str, date_col: str, events: pd.DataFrame) -> pd.DataFrame:
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
    ticker_col = next((c for c in ("Stock_symbol", "ticker", "symbol", "stock_symbol") if c in news.columns), None)
    date_col = next((c for c in ("Date", "date", "published_at") if c in news.columns), None)
    title_col = next((c for c in ("Article_title", "title", "headline") if c in news.columns), None)
    sentiment_col = next((c for c in ("sentiment", "sentiment_score") if c in news.columns), None)
    source_col = next((c for c in ("Publisher", "source", "publisher") if c in news.columns), None)
    if ticker_col is None or date_col is None:
        raise ValueError("ticker/date columns not found")
    news = narrow_fnspid_to_events(news, ticker_col, date_col, events)
    dedup_cols = ["_ticker_upper", "_parsed_date"]
    if title_col in news.columns:
        news["_title_hash"] = news[title_col].astype(str).str.strip().str.lower()
        dedup_cols.append("_title_hash")
    if source_col in news.columns:
        dedup_cols.append(source_col)
    url_col = next((c for c in ("Url", "url", "link") if c in news.columns), None)
    if url_col:
        dedup_cols.append(url_col)
    news = news.drop_duplicates(subset=dedup_cols)
    by_ticker = {t: g for t, g in news.groupby("_ticker_upper")}
    derived_rows = []
    for _, event in events.iterrows():
        event_id = int(event.event_id)
        ticker = str(event.ticker).upper().strip()
        event_date = npu.parse_date(event.event_date)
        row: dict[str, Any] = {
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
        for days in (1, 3, 7):
            pre_dates = window_news[
                (window_news["_parsed_date"] >= event_date - timedelta(days=days))
                & (window_news["_parsed_date"] < event_date)
            ]
            post_dates = window_news[
                (window_news["_parsed_date"] >= event_date)
                & (window_news["_parsed_date"] <= event_date + timedelta(days=days))
            ]
            row[f"fnspid_news_count_pre_{days}d"] = len(pre_dates)
            row[f"fnspid_news_count_post_{days}d"] = len(post_dates)
            if days == 3 and sentiment_col and sentiment_col in window_news.columns:
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
    by_ticker_summary = (
        panel.groupby("ticker")
        .agg(events=("event_id", "count"), hits=("fnspid_news_hit", "sum"), mean_pre_7d=("fnspid_news_count_pre_7d", "mean"))
        .reset_index()
    )
    panel["year"] = pd.to_datetime(panel["event_date"], errors="coerce").dt.year
    by_year_summary = (
        panel.groupby("year")
        .agg(events=("event_id", "count"), hits=("fnspid_news_hit", "sum"), mean_pre_7d=("fnspid_news_count_pre_7d", "mean"))
        .reset_index()
    )
    provider_status = pd.DataFrame(
        [
            {
                "provider": "fnspid_news",
                "status": "success",
                "loaded_records": len(news),
                "events_checked": len(events),
                "hits_found": int(panel["fnspid_news_hit"].sum()),
            }
        ]
    )
    return panel, by_ticker_summary, by_year_summary, provider_status


def build_event_states(events: pd.DataFrame) -> dict[int, EventArticleState]:
    by_eid: dict[int, EventArticleState] = {}
    for _, event in events.iterrows():
        eid = int(event.event_id)
        ticker = str(event.ticker).upper().strip()
        ed = npu.parse_date(event.event_date)
        if ed is None or ticker in NOISY_SYMBOLS:
            continue
        by_eid[eid] = EventArticleState(
            event_id=eid,
            ticker=ticker,
            event_date=str(event.event_date),
            ed=ed,
        )
    return by_eid


def index_events_by_ticker(states: dict[int, EventArticleState]) -> dict[str, list[EventArticleState]]:
    idx: dict[str, list[EventArticleState]] = defaultdict(list)
    for st in states.values():
        idx[st.ticker].append(st)
    return dict(idx)


def stream_csv_into_states(
    csv_url: str,
    source_file: str,
    ticker_to_states: dict[str, list[EventArticleState]],
    chunk_size: int,
    max_chunks: int | None,
    rows_counter: list[int],
    chunks_counter: list[int],
) -> str | None:
    """Stream-filter CSV rows one-by-one (low RAM on RunPod). chunk_size = progress batch only."""
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    ticker_set = set(ticker_to_states.keys())
    rows_since_chunk = 0
    try:
        req = Request(csv_url, headers={"User-Agent": "FIN496-fnspid-stream/1.0"})
        with urlopen(req, timeout=None) as resp:
            text = TextIOWrapper(resp, encoding="utf-8", errors="replace", newline="")
            dict_reader = csv.DictReader(text)
            if dict_reader.fieldnames is None:
                return "no_csv_header"
            fnmap = {str(f).strip(): str(f).strip() for f in dict_reader.fieldnames}

            def pick(*names: str) -> str | None:
                for n in names:
                    if n in fnmap:
                        return n
                return None

            c_date = pick("Date", "date")
            c_sym = pick("Stock_symbol")
            c_title = pick("Article_title")
            c_url = pick("Url", "url")
            if not c_date or not c_sym:
                return f"missing Date or Stock_symbol; columns={list(fnmap.keys())[:15]}"
            for row in dict_reader:
                rows_counter[0] += 1
                rows_since_chunk += 1
                if rows_since_chunk >= chunk_size:
                    chunks_counter[0] += 1
                    rows_since_chunk = 0
                    if max_chunks is not None and chunks_counter[0] > max_chunks:
                        break
                if rows_counter[0] % 500_000 == 0:
                    print(f"FNSPID stream progress: rows_read={rows_counter[0]:,} source={source_file}", flush=True)
                sym = str(row.get(c_sym, "") or "").upper().strip()
                if sym not in ticker_set:
                    continue
                ts = pd.to_datetime(row.get(c_date, ""), utc=True, errors="coerce")
                if pd.isna(ts):
                    continue
                d = ts.date()
                title = str(row.get(c_title, "") or "")[:2000]
                url = str(row.get(c_url, "") or "")
                for st in ticker_to_states.get(sym, ()):
                    st.add_if_in_window(d, title, "", url, source_file)
    except Exception as exc:
        return str(exc)
    return None


def load_spine_into_states(
    path: Path,
    states: dict[int, EventArticleState],
    *,
    sources_allow: set[str] | None = None,
) -> int:
    """Restore compact article rows (no raw headlines/URLs stored on disk)."""
    if not path.exists():
        return 0
    restored = 0
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            eid = int(row.get("event_id", -1))
            st = states.get(eid)
            if st is None:
                continue
            src = str(row.get("source_file", "") or "")
            if sources_allow is not None and src not in sources_allow:
                continue
            d = npu.parse_date(row.get("article_date", ""))
            if d is None:
                continue
            key = str(row.get("article_key", "") or "")
            if not key:
                continue
            if st.add_restored_key(d, key, src):
                restored += 1
    return restored


def write_spine_from_states(states: dict[int, EventArticleState], path: Path) -> None:
    rows: list[dict[str, str | int]] = []
    for st in states.values():
        for d, key, src in st.articles:
            rows.append(
                {
                    "event_id": st.event_id,
                    "ticker": st.ticker,
                    "article_date": d.isoformat(),
                    "article_key": key,
                    "source_file": src,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def read_panel_baseline_counts() -> dict[str, Any]:
    out: dict[str, Any] = {
        "unknown_news_coverage_before": "",
        "media_confounded_before": "",
        "multi_source_clean_before": "",
    }
    if not PANEL_PATH.exists():
        return out
    try:
        pane = pd.read_csv(PANEL_PATH)
    except Exception:
        return out
    col = "news_clean_status_final" if "news_clean_status_final" in pane.columns else "news_clean_status"
    if col not in pane.columns:
        return out
    vc = pane[col].fillna("").astype(str).value_counts()
    out["unknown_news_coverage_before"] = int(vc.get("unknown_news_coverage", 0))
    out["media_confounded_before"] = int(vc.get("media_confounded", 0))
    out["multi_source_clean_before"] = int(vc.get("multi_source_clean", 0))
    return out


def write_empty_status(events: pd.DataFrame, status_str: str) -> None:
    rows = []
    for _, event in events.iterrows():
        rows.append(
            {
                "event_id": int(event.event_id),
                "ticker": str(event.ticker).upper().strip(),
                "event_date": event.event_date,
                "fnspid_checked": False,
                "fnspid_hit_pre_7d": 0,
                "fnspid_hit_day0": 0,
                "fnspid_hit_post_1d": 0,
                "fnspid_hit_post_3d": 0,
                "fnspid_hit_post_7d": 0,
                "fnspid_total_hits_window": 0,
                "fnspid_unique_publishers_window": 0,
                "fnspid_primary_article_count": 0,
                "fnspid_secondary_article_count": 0,
                "fnspid_hit_sources": "none",
                "fnspid_sample_titles_redacted_or_short": "",
                "fnspid_status": status_str,
                "fnspid_error_category": status_str,
            }
        )
    pd.DataFrame(rows).to_csv(OUT_DIR / "fnspid_event_window_hits.csv", index=False)
    _write_compat_empty(events, status_str)


def _write_compat_empty(events: pd.DataFrame, status_str: str) -> None:
    derived = []
    for _, event in events.iterrows():
        derived.append(
            {
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
            }
        )
    pd.DataFrame(derived).to_csv(OUT_DIR / "fnspid_derived_event_panel.csv", index=False)
    pd.DataFrame(columns=["ticker", "events", "hits", "mean_pre_7d"]).to_csv(OUT_DIR / "fnspid_by_ticker.csv", index=False)
    pd.DataFrame(columns=["year", "events", "hits", "mean_pre_7d"]).to_csv(OUT_DIR / "fnspid_by_year.csv", index=False)
    pd.DataFrame(
        columns=["ticker", "n_events", "share_of_sample", "fnspid_events_with_hit", "hit_rate"],
    ).to_csv(OUT_DIR / "fnspid_ticker_coverage.csv", index=False)
    pd.DataFrame(columns=["year", "events", "hits", "events_with_fnspid_hit"]).to_csv(
        OUT_DIR / "fnspid_year_coverage.csv", index=False
    )
    pd.DataFrame([{"provider": "fnspid_news", "status": status_str, "access_method": "none", "rows_scanned": 0}]).to_csv(
        OUT_DIR / "fnspid_provider_status.csv", index=False
    )
    Path(OUT_DIR / "fnspid_summary.md").write_text(f"# FNSPID\n\n**Status**: {status_str}\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    events = utils.event_manifest().copy()
    print(f"Loaded {len(events)} events from manifest.")

    if args.skip_hf:
        write_empty_status(events, "skip_hf_flag")
        return

    if args.legacy_stream:
        news = load_fnspid_local()
        if news is None:
            news = load_fnspid_huggingface(args.limit_rows)
        if news is None:
            write_empty_status(events, "missing_or_failed_loading")
            return
        panel, by_ticker, by_year, status = process_fnspid(events, news)
        panel.to_csv(OUT_DIR / "fnspid_derived_event_panel.csv", index=False)
        by_ticker.to_csv(OUT_DIR / "fnspid_by_ticker.csv", index=False)
        by_year.to_csv(OUT_DIR / "fnspid_by_year.csv", index=False)
        status.to_csv(OUT_DIR / "fnspid_provider_status.csv", index=False)
        Path(OUT_DIR / "fnspid_summary.md").write_text(
            f"# FNSPID News Layer Summary (legacy stream)\n\n**Hits**: {int(panel['fnspid_news_hit'].sum())}\n",
            encoding="utf-8",
        )
        return

    probe = probe_dataset_server()
    iv = probe.get("is_valid") or {}
    filter_try = try_api_path(
        "filter",
        {
            "dataset": FNSPID_DATASET,
            "config": "default",
            "split": "train",
            "where": '"Stock_symbol"=\'AAPL\'',
            "length": 5,
        },
    )
    rows_try = try_api_path(
        "rows", {"dataset": FNSPID_DATASET, "config": "default", "split": "train", "offset": 0, "length": 5}
    )
    row_probe = rows_try.get("error") or rows_try.get("cause_message", "")
    if row_probe:
        print("/rows probe:", str(row_probe)[:200])
    first_rows: dict[str, Any] = {}
    canary_preview: dict[str, Any] = {}
    try:
        first_rows = fetch_first_rows(FNSPID_DATASET, "default", "train")
        canary_preview = canary_counts_from_first_rows(first_rows)
    except Exception as exc:
        first_rows = {"error": str(exc)}
        canary_preview = {}

    baseline = read_panel_baseline_counts()
    derived_path = OUT_DIR / "fnspid_derived_event_panel.csv"
    old_hit_events: int | str = ""
    if derived_path.exists():
        try:
            od = pd.read_csv(derived_path)
            if "fnspid_news_hit" in od.columns:
                ser = od["fnspid_news_hit"]
                if ser.dtype == object:
                    old_hit_events = int(ser.astype(str).str.lower().isin({"true", "1"}).sum())
                else:
                    old_hit_events = int(ser.fillna(0).astype(bool).sum())
        except Exception:
            old_hit_events = ""

    states = build_event_states(events)
    ticker_index = index_events_by_ticker(states)
    primary_rows = [0]
    secondary_rows = [0]
    chunks_used = [0]
    stream_err_pri: str | None = None
    stream_err_sec: str | None = None
    access_bits = [
        f"preview={iv.get('preview')}",
        f"viewer={iv.get('viewer')}",
        f"filter={iv.get('filter')}",
        f"search={iv.get('search')}",
    ]
    print("Dataset server:", ", ".join(access_bits))
    print("Canary first-rows (tickers in first 100 rows):", canary_preview)

    if not ticker_index:
        write_empty_status(events, "no_events_with_parseable_dates")
        return

    prev_meta: dict[str, Any] = {}
    if STREAM_META_PATH.exists():
        try:
            prev_meta = json.loads(STREAM_META_PATH.read_text(encoding="utf-8"))
        except Exception:
            prev_meta = {}

    reuse_pri = bool(args.reuse_primary_spine and args.also_secondary_csv and SPINE_PATH.exists())
    if args.reuse_primary_spine and args.also_secondary_csv and not SPINE_PATH.exists():
        print("reuse_primary_spine requested but fnspid_article_spine.csv missing; streaming primary CSV instead.")
        reuse_pri = False

    if reuse_pri:
        restored = load_spine_into_states(SPINE_PATH, states, sources_allow={PRIMARY_CSV_BASENAME})
        primary_rows[0] = int(prev_meta.get("primary_nasdaq_rows_read", 0) or 0)
        print(f"Restored {restored} compact primary rows from spine; primary CSV rows (last full run) = {primary_rows[0]:,}.")
    else:
        stream_err_pri = stream_csv_into_states(
            args.csv_url,
            PRIMARY_CSV_BASENAME,
            ticker_index,
            args.chunk_size,
            args.max_chunks,
            primary_rows,
            chunks_used,
        )
        if stream_err_pri:
            print(f"Primary CSV stream error: {stream_err_pri}")

    if args.also_secondary_csv:
        stream_err_sec = stream_csv_into_states(
            SECONDARY_CSV_URL,
            SECONDARY_CSV_BASENAME,
            ticker_index,
            args.chunk_size,
            args.max_chunks,
            secondary_rows,
            chunks_used,
        )
        if stream_err_sec:
            print(f"Secondary CSV stream error: {stream_err_sec}")

    if stream_err_pri and not reuse_pri:
        status = f"stream_error_primary:{stream_err_pri[:120]}"
        error_cat = "csv_stream_primary"
    elif stream_err_sec:
        status = f"stream_error_secondary:{stream_err_sec[:120]}"
        error_cat = "csv_stream_secondary"
    else:
        status = "success"
        error_cat = ""

    coverage_ok = (reuse_pri or stream_err_pri is None or primary_rows[0] > 0) and (
        not args.also_secondary_csv or stream_err_sec is None or secondary_rows[0] > 0
    )

    hit_rows = []
    legacy_rows = []
    for _, event in events.iterrows():
        eid = int(event.event_id)
        st = states.get(eid)
        if st is None:
            hit_rows.append(
                {
                    "event_id": eid,
                    "ticker": str(event.ticker).upper().strip(),
                    "event_date": event.event_date,
                    "fnspid_checked": coverage_ok,
                    "fnspid_hit_pre_7d": 0,
                    "fnspid_hit_day0": 0,
                    "fnspid_hit_post_1d": 0,
                    "fnspid_hit_post_3d": 0,
                    "fnspid_hit_post_7d": 0,
                    "fnspid_total_hits_window": 0,
                    "fnspid_unique_publishers_window": 0,
                    "fnspid_primary_article_count": 0,
                    "fnspid_secondary_article_count": 0,
                    "fnspid_hit_sources": "none",
                    "fnspid_sample_titles_redacted_or_short": "",
                    "fnspid_status": status,
                    "fnspid_error_category": error_cat or "skipped_event",
                }
            )
            legacy_rows.append(
                {
                    "event_id": eid,
                    "ticker": str(event.ticker).upper().strip(),
                    "event_date": event.event_date,
                    "fnspid_coverage_available": coverage_ok,
                    "fnspid_news_hit": False,
                    "fnspid_hit_sources": "none",
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
            )
            continue
        band = st.finalize_counts()
        leg = st.legacy_fnspid_counts()
        total_h = int(band["fnspid_total_hits_window"])
        hit_rows.append(
            {
                "event_id": eid,
                "ticker": st.ticker,
                "event_date": st.event_date,
                "fnspid_checked": coverage_ok,
                **band,
                "fnspid_status": status,
                "fnspid_error_category": error_cat,
            }
        )
        arts = st.articles
        first_d = min((a[0] for a in arts), default=None)
        last_d = max((a[0] for a in arts), default=None)
        legacy_rows.append(
            {
                "event_id": eid,
                "ticker": st.ticker,
                "event_date": st.event_date,
                "fnspid_coverage_available": coverage_ok,
                "fnspid_news_hit": total_h > 0,
                "fnspid_hit_sources": band.get("fnspid_hit_sources", st.source_hit_category()),
                **leg,
                "fnspid_mean_sentiment_pre_3d": 0.0,
                "fnspid_mean_sentiment_post_3d": 0.0,
                "fnspid_max_abs_sentiment_pre_3d": 0.0,
                "fnspid_source_count_pre_7d": 0,
                "fnspid_unique_title_count_pre_7d": 0,
                "fnspid_first_article_date_near_event": first_d.isoformat() if first_d else "",
                "fnspid_last_article_date_near_event": last_d.isoformat() if last_d else "",
            }
        )

    hits_df = pd.DataFrame(hit_rows)
    legacy_df = pd.DataFrame(legacy_rows)
    hits_df.to_csv(OUT_DIR / "fnspid_event_window_hits.csv", index=False)
    legacy_df.to_csv(OUT_DIR / "fnspid_derived_event_panel.csv", index=False)

    n_events = len(events)
    tc_rows = []
    for t, grp in legacy_df.groupby("ticker"):
        ne = len(grp)
        nh = int(grp["fnspid_news_hit"].sum())
        tc_rows.append(
            {
                "ticker": t,
                "n_events": ne,
                "share_of_sample": round(ne / max(n_events, 1), 6),
                "fnspid_events_with_hit": nh,
                "hit_rate": round(nh / max(ne, 1), 6),
            }
        )
    tc_df = pd.DataFrame(tc_rows).sort_values("n_events", ascending=False)
    tc_df.to_csv(OUT_DIR / "fnspid_ticker_coverage.csv", index=False)
    by_ticker_out = (
        legacy_df.groupby("ticker")
        .agg(
            events=("event_id", "count"),
            hits=("fnspid_news_hit", "sum"),
            mean_pre_7d=("fnspid_news_count_pre_7d", "mean"),
        )
        .reset_index()
    )
    by_ticker_out.to_csv(OUT_DIR / "fnspid_by_ticker.csv", index=False)

    legacy_df["year"] = pd.to_datetime(legacy_df["event_date"], errors="coerce").dt.year
    ycov = (
        legacy_df.groupby("year")
        .agg(events=("event_id", "count"), hits=("fnspid_news_hit", "sum"))
        .reset_index()
    )
    ycov = ycov.rename(columns={"hits": "events_with_fnspid_hit"})
    ycov.to_csv(OUT_DIR / "fnspid_year_coverage.csv", index=False)
    ycov.rename(columns={"events_with_fnspid_hit": "hits"}).to_csv(OUT_DIR / "fnspid_by_year.csv", index=False)

    hits_found = int(legacy_df["fnspid_news_hit"].sum())
    hit_sub = legacy_df[legacy_df["fnspid_news_hit"].astype(bool)]
    srcvc = hit_sub["fnspid_hit_sources"].value_counts() if "fnspid_hit_sources" in hit_sub.columns else pd.Series(dtype=int)
    n_primary_only = int(srcvc.get("primary_only", 0))
    n_secondary_only = int(srcvc.get("secondary_only", 0))
    n_both = int(srcvc.get("both", 0))
    u_tick_hit = int(legacy_df.loc[legacy_df["fnspid_news_hit"].astype(bool), "ticker"].nunique())

    comparison_rows = [
        {"metric": "primary_nasdaq_rows_read", "value": primary_rows[0]},
        {"metric": "secondary_all_external_rows_read", "value": secondary_rows[0]},
        {"metric": "fnspid_hits_primary_only", "value": n_primary_only},
        {"metric": "fnspid_hits_secondary_only", "value": n_secondary_only},
        {"metric": "fnspid_hits_both", "value": n_both},
        {"metric": "total_fnspid_news_hit_events", "value": hits_found},
        {"metric": "unique_tickers_with_fnspid_hits", "value": u_tick_hit},
        {"metric": "fnspid_hit_events_before_run", "value": old_hit_events},
        {
            "metric": "unknown_news_coverage_before",
            "value": baseline.get("unknown_news_coverage_before", ""),
        },
        {"metric": "media_confounded_before", "value": baseline.get("media_confounded_before", "")},
        {"metric": "multi_source_clean_before", "value": baseline.get("multi_source_clean_before", "")},
        {
            "metric": "unknown_news_coverage_after",
            "value": "rebuild_news_confound_master_layer",
        },
        {
            "metric": "media_confounded_after",
            "value": "rebuild_news_confound_master_layer",
        },
        {
            "metric": "multi_source_clean_after",
            "value": "rebuild_news_confound_master_layer",
        },
    ]
    pd.DataFrame(comparison_rows).to_csv(OUT_DIR / "fnspid_source_comparison.csv", index=False)

    stream_meta = {
        "primary_nasdaq_rows_read": primary_rows[0],
        "secondary_all_external_rows_read": secondary_rows[0],
        "reuse_primary_spine": reuse_pri,
        "also_secondary_csv": bool(args.also_secondary_csv),
    }
    STREAM_META_PATH.write_text(json.dumps(stream_meta, indent=2), encoding="utf-8")
    write_spine_from_states(states, SPINE_PATH)

    fe_note = ""
    if isinstance(filter_try, dict) and filter_try.get("error"):
        fe_note = str(filter_try.get("error", ""))[:200]
    elif isinstance(filter_try, dict) and filter_try.get("cause_message"):
        fe_note = str(filter_try.get("cause_message", ""))[:200]
    else:
        fe_note = "filter_probe_finished"
    prov = pd.DataFrame(
        [
            {
                "provider": "fnspid_news",
                "status": status,
                "access_method": "datasets_server_probe_plus_hub_csv_stream",
                "primary_rows_read": primary_rows[0],
                "secondary_rows_read": secondary_rows[0],
                "rows_scanned_total": primary_rows[0] + secondary_rows[0],
                "chunks": chunks_used[0],
                "csv_primary": args.csv_url.split("/")[-1][:80],
                "csv_secondary": SECONDARY_CSV_BASENAME if args.also_secondary_csv else "",
                "hits_found": hits_found,
                "filter_endpoint_probe_note": fe_note,
            }
        ]
    )
    prov.to_csv(OUT_DIR / "fnspid_provider_status.csv", index=False)

    summary = f"""# FNSPID News Layer Summary

## Access

- **Mode**: Hugging Face Dataset Server **probe** (`/is-valid`, `/splits`, `/first-rows`) plus **stream-filter** of Hub CSV (no full raw file committed).
- **Server capabilities** (from `/is-valid): preview={iv.get("preview")}, viewer={iv.get("viewer")}, filter={iv.get("filter")}, search={iv.get("search")}.
- **Note**: Zihan1004/FNSPID currently has **filter/viewer/search disabled** and `/rows` may error on conversion; substantive coverage requires **CSV streaming**, not paginated API slices.
- **Primary CSV**: `{args.csv_url.split("/")[-1]}`
- **Primary rows read (this run or spine reuse metadata)**: {primary_rows[0]:,}
- **Secondary rows read (All_external.csv)**: {secondary_rows[0]:,}
- **Reuse primary spine**: {reuse_pri}
- **Chunks**: {chunks_used[0]}
- **Stream status**: {status}

## Rows + source mix

See `fnspid_source_comparison.csv` for primary vs secondary row counts, hit overlap, and **news_clean_status** baselines captured before this run.

## API canary (first 100 preview rows)

```json
{json.dumps(canary_preview, indent=0)}
```

## Results

- **Events checked**: {len(events)}
- **FN-SPID events with ≥1 article (±7d, cross-file deduped)**: {hits_found}
- **Hits primary-only / secondary-only / both**: {n_primary_only} / {n_secondary_only} / {n_both}
- **Tickers with ≥1 hit**: {int((legacy_df.groupby("ticker")["fnspid_news_hit"].sum() > 0).sum())}

## Year table

{utils.md_table(ycov.to_dict("records"))}

## Panel baselines (before this run)

- unknown_news_coverage: **{baseline.get("unknown_news_coverage_before", "")}**
- media_confounded: **{baseline.get("media_confounded_before", "")}**
- multi_source_clean: **{baseline.get("multi_source_clean_before", "")}**

`unknown_news_coverage_after`, `media_confounded_after`, and `multi_source_clean_after` refresh when `build_v2_public_news_confound_master_layer.py` completes (see appended section in this file).
"""
    Path(OUT_DIR / "fnspid_summary.md").write_text(summary, encoding="utf-8")
    print(
        f"FNSPID complete: hits={hits_found}, primary_rows={primary_rows[0]:,}, "
        f"secondary_rows={secondary_rows[0]:,}, status={status}"
    )


if __name__ == "__main__":
    main()
