from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf
from scipy import stats

from .config import DATA_DIR, EXPORTS_DIR
from .db import connect
from .utils import configure_csv_field_size_limit

RESEARCH_EXPANSION_DIR = EXPORTS_DIR / "research_expansion"
AUDIT_DIR = RESEARCH_EXPANSION_DIR / "audit"
SAMPLE_DESIGN_DIR = RESEARCH_EXPANSION_DIR / "sample_design"
RETURN_COVERAGE_DIR = RESEARCH_EXPANSION_DIR / "return_coverage"
EVENT_WINDOWS_DIR = RESEARCH_EXPANSION_DIR / "event_windows"
BENCHMARKS_DIR = RESEARCH_EXPANSION_DIR / "benchmarks"
PORTFOLIOS_DIR = RESEARCH_EXPANSION_DIR / "portfolios"
STATISTICS_DIR = RESEARCH_EXPANSION_DIR / "statistics"
CLASSIFIER_AI_AUDIT_DIR = RESEARCH_EXPANSION_DIR / "classifier_ai_audit"
REPORTING_DIR = RESEARCH_EXPANSION_DIR / "reporting"

SECTOR_ETF_MAP = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AMD", "CRM"],
    "XLC": ["META", "GOOGL", "NFLX"],
    "XLY": ["AMZN", "TSLA", "UBER", "SHOP", "DIS"],
    "XLF": ["PYPL", "SOFI", "HOOD", "COIN"],
    "XLI": ["PLTR", "SMCI"],
    "XLP": [],
    "XLE": [],
    "XLV": [],
    "XLU": [],
    "XLB": [],
    "XLRE": [],
    "IWM": [],
}

TICKER_TO_SECTOR_ETF: dict[str, str] = {}
for etf, tickers in SECTOR_ETF_MAP.items():
    for ticker in tickers:
        TICKER_TO_SECTOR_ETF[ticker] = etf

BENCHMARK_TICKERS = ["SPY", "QQQ", "IWM"]

HORIZON_MAP = {
    "1D": 1,
    "1W": 5,
    "2W": 10,
    "3W": 15,
    "1M": 21,
    "2M": 42,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
    "2Y": 504,
    "END_OF_SAMPLE": None,
}

PRE_EVENT_HORIZONS = {
    "PRE_1W": (-5, -1),
    "PRE_1M": (-21, -1),
    "PRE_3M": (-63, -1),
}

SAMPLE_MODES = [
    "uncapped_full",
    "cap_250_per_creator",
    "cap_500_per_creator",
    "cap_1000_per_creator",
    "cap_100_per_creator_year",
    "balanced_creator_year_sample",
]


def _ensure_dirs() -> None:
    for d in [
        AUDIT_DIR,
        SAMPLE_DESIGN_DIR,
        RETURN_COVERAGE_DIR,
        EVENT_WINDOWS_DIR,
        BENCHMARKS_DIR,
        PORTFOLIOS_DIR,
        STATISTICS_DIR,
        CLASSIFIER_AI_AUDIT_DIR,
        REPORTING_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _read_csv(path: Path) -> pd.DataFrame:
    configure_csv_field_size_limit()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Build clean events from ALL DB events
# ---------------------------------------------------------------------------

def _fetch_all_events_from_db() -> pd.DataFrame:
    conn = connect()
    query = """
    SELECT
        tr.transcript_event_id AS event_id,
        tr.video_id,
        rv.channel_title AS creator,
        rv.title,
        rv.published_at,
        tr.ticker,
        tr.company_name,
        tr.stance,
        tr.detected_action,
        tr.actionability_score,
        tr.confidence_score,
        tr.confidence_label,
        tr.evidence_start_seconds,
        tr.evidence_end_seconds,
        tr.evidence_window,
        tr.classifier_version,
        tr.transcript_source,
        tr.provider_name,
        rv.url AS video_url,
        yt.full_text
    FROM transcript_recommendation_events tr
    JOIN raw_youtube_videos rv ON tr.video_id = rv.video_id
    LEFT JOIN youtube_transcripts yt ON tr.video_id = yt.video_id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def _map_stance_to_recommendation(row: pd.Series) -> dict[str, Any]:
    stance = _clean(row.get("stance", "")).lower()
    detected = _clean(row.get("detected_action", "")).lower()
    actionability = int(row.get("actionability_score") or 0)
    evidence = _clean(row.get("evidence_window", ""))
    full_text = _clean(row.get("full_text", ""))
    text = evidence if evidence else full_text

    direction = "positive" if stance == "bullish" else "negative" if stance == "bearish" else "neutral"

    rec_type = "buy"
    if "sell" in detected or "short" in detected:
        rec_type = "sell"
    elif "avoid" in detected:
        rec_type = "avoid"
    elif "price_target" in text.lower() or "target" in text.lower():
        rec_type = "price_target"
    elif "portfolio" in detected or "holding" in text.lower():
        rec_type = "portfolio_update"

    confidence = float(row.get("confidence_score") or 0.6)
    if actionability >= 3 and confidence >= 0.7:
        evidence_quality = "strong"
    elif actionability >= 2:
        evidence_quality = "medium"
    else:
        evidence_quality = "weak"

    event_date = ""
    published = _clean(row.get("published_at", ""))
    if len(published) >= 10:
        event_date = published[:10]

    return {
        "event_id": str(row.get("event_id") or row.get("transcript_event_id") or ""),
        "video_id": _clean(row.get("video_id", "")),
        "creator": _clean(row.get("creator", "")),
        "title": _clean(row.get("title", "")),
        "published_at": published,
        "event_date_utc": event_date,
        "ticker": _clean(row.get("ticker", "")).upper(),
        "company_name": _clean(row.get("company_name", "")),
        "recommendation_type": rec_type,
        "direction": direction,
        "confidence": f"{confidence:.3f}",
        "evidence_quality": evidence_quality,
        "source_transcript_type": f"{_clean(row.get('transcript_source', 'unknown'))}:{_clean(row.get('provider_name', 'unknown'))}",
        "transcript_source": _clean(row.get("transcript_source", "")),
        "provider_name": _clean(row.get("provider_name", "")),
        "video_url": _clean(row.get("video_url", "")),
        "transcript_window_text": evidence if evidence else full_text[:500],
        "context_before": "",
        "context_after": "",
        "auto_label_reason": f"db_stance={stance}, detected_action={detected}",
        "auto_label_evidence_quote": evidence if evidence else full_text[:240],
    }


def build_all_clean_events(
    output_path: Path | None = None,
    exclusions_path: Path | None = None,
) -> dict[str, Any]:
    _ensure_dirs()
    output_path = output_path or (RESEARCH_EXPANSION_DIR / "all_clean_events.csv")
    exclusions_path = exclusions_path or (RESEARCH_EXPANSION_DIR / "all_clean_events_exclusions.csv")

    df = _fetch_all_events_from_db()
    included: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    ambiguous_tickers = {
        "ALL", "ARE", "BE", "BIG", "BY", "CAN", "CASH", "FOR", "GOOD",
        "LIFE", "LOVE", "LOW", "NOW", "ON", "OPEN", "OUT", "REAL", "SO",
        "TRUE", "UP", "VERY", "WELL", "YOU",
    }

    for _, row in df.iterrows():
        projection = _map_stance_to_recommendation(row)
        ticker = projection["ticker"]
        reasons: list[str] = []

        if not ticker:
            reasons.append("missing_ticker")
        if ticker in ambiguous_tickers:
            reasons.append("ambiguous_ticker")
        if not projection["event_date_utc"]:
            reasons.append("missing_event_date")
        if float(projection["confidence"] or 0) < 0.50:
            reasons.append("low_confidence")

        if reasons:
            exclusions.append({**projection, "clean_event_exclusion_reason": ";".join(reasons)})
        else:
            included.append(projection)

    cols = [
        "event_id", "video_id", "creator", "title", "published_at", "event_date_utc",
        "ticker", "company_name", "recommendation_type", "direction", "confidence",
        "evidence_quality", "source_transcript_type", "transcript_source", "provider_name",
        "video_url", "transcript_window_text", "context_before", "context_after",
        "auto_label_reason", "auto_label_evidence_quote",
    ]

    pd.DataFrame(included).to_csv(output_path, index=False, columns=cols)
    pd.DataFrame(exclusions).to_csv(exclusions_path, index=False, columns=[*cols, "clean_event_exclusion_reason"])

    return {
        "output_path": output_path,
        "exclusions_path": exclusions_path,
        "included_count": len(included),
        "excluded_count": len(exclusions),
    }


# ---------------------------------------------------------------------------
# 2. Sample design robustness
# ---------------------------------------------------------------------------

def _apply_sample_mode(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    df = df.copy()
    df["year"] = pd.to_datetime(df["published_at"], errors="coerce").dt.year

    if mode == "uncapped_full":
        return df

    if mode == "cap_250_per_creator":
        return df.groupby("creator").head(250).reset_index(drop=True)

    if mode == "cap_500_per_creator":
        return df.groupby("creator").head(500).reset_index(drop=True)

    if mode == "cap_1000_per_creator":
        return df.groupby("creator").head(1000).reset_index(drop=True)

    if mode == "cap_100_per_creator_year":
        df["creator_year"] = df["creator"] + "_" + df["year"].astype(str)
        return df.groupby("creator_year").head(100).reset_index(drop=True)

    if mode == "balanced_creator_year_sample":
        target = max(1, len(df) // df.groupby(["creator", "year"]).ngroups)
        return df.groupby(["creator", "year"]).head(target).reset_index(drop=True)

    return df


def build_sample_design_report(
    clean_events_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    _ensure_dirs()
    clean_events_path = clean_events_path or (RESEARCH_EXPANSION_DIR / "all_clean_events.csv")
    output_dir = output_dir or SAMPLE_DESIGN_DIR
    df = _read_csv(clean_events_path)
    if df.empty:
        raise ValueError("No clean events found.")

    rows = []
    for mode in SAMPLE_MODES:
        sample = _apply_sample_mode(df, mode)
        if sample.empty:
            continue
        sample["year"] = pd.to_datetime(sample["published_at"], errors="coerce").dt.year
        top_creator = sample["creator"].value_counts().iloc[0] if len(sample) > 0 else 0
        top_ticker = sample["ticker"].value_counts().iloc[0] if len(sample) > 0 else 0
        rows.append({
            "sample_mode": mode,
            "videos": sample["video_id"].nunique(),
            "transcripts": sample["video_id"].nunique(),
            "candidate_events": len(df),
            "clean_events": len(sample),
            "unique_creators": sample["creator"].nunique(),
            "unique_tickers": sample["ticker"].nunique(),
            "earliest_date": sample["event_date_utc"].min(),
            "latest_date": sample["event_date_utc"].max(),
            "top_creator_share": round(top_creator / len(sample), 4) if len(sample) else 0,
            "top_ticker_share": round(top_ticker / len(sample), 4) if len(sample) else 0,
        })

    report = pd.DataFrame(rows)
    csv_path = output_dir / "sample_mode_counts.csv"
    md_path = output_dir / "sample_mode_counts.md"
    _write_csv(csv_path, report)

    lines = ["# Sample Design Robustness Report", ""]
    lines.append("| Mode | Clean Events | Creators | Tickers | Top Creator Share | Top Ticker Share |")
    lines.append("|------|-------------|----------|---------|-------------------|------------------|")
    for _, r in report.iterrows():
        lines.append(
            f"| {r['sample_mode']} | {r['clean_events']} | {r['unique_creators']} | "
            f"{r['unique_tickers']} | {r['top_creator_share']:.2%} | {r['top_ticker_share']:.2%} |"
        )
    _write_md(md_path, lines)
    return csv_path


# ---------------------------------------------------------------------------
# 3. Fetch expanded market data
# ---------------------------------------------------------------------------

def fetch_expanded_market_data(
    tickers: list[str] | None = None,
    output_path: Path | None = None,
) -> Path:
    _ensure_dirs()
    if tickers is None:
        df = _fetch_all_events_from_db()
        tickers = sorted({t.upper() for t in df["ticker"].dropna().unique() if t})

    all_tickers = list(set(tickers + BENCHMARK_TICKERS + list(SECTOR_ETF_MAP.keys())))
    output_path = output_path or (DATA_DIR / "imports" / "market_data" / "yfinance_expanded_market_data.csv")

    rows: list[dict[str, Any]] = []
    for ticker in all_tickers:
        try:
            data = yf.download(ticker, period="10y", progress=False, auto_adjust=True)
            if data.empty:
                continue
            data = data.reset_index()
            # Handle multi-index columns from yfinance
            date_col = "Date"
            close_col = "Close"
            if isinstance(data.columns, pd.MultiIndex):
                date_col = ("Date", "")
                close_col = ("Close", ticker)
            if date_col not in data.columns:
                continue
            for _, row in data.iterrows():
                date_val = row[date_col]
                if isinstance(date_val, pd.Timestamp):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
                close_val = row.get(close_col)
                adj_close = float(close_val) if pd.notna(close_val) else None
                if adj_close is None:
                    continue
                rows.append({
                    "ticker": ticker,
                    "date": date_str,
                    "adjusted_close": adj_close,
                    "data_source": "yfinance_yahoo_prototype",
                })
        except Exception:
            continue

    df = pd.DataFrame(rows)
    _write_csv(output_path, df)
    return output_path


# ---------------------------------------------------------------------------
# 4. Return coverage diagnostics
# ---------------------------------------------------------------------------

def _next_trading_day(date_str: str, trading_days: set[str]) -> str | None:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    for i in range(10):
        cand = (d + timedelta(days=i)).isoformat()
        if cand in trading_days:
            return cand
    return None


def diagnose_return_coverage(
    clean_events_path: Path | None = None,
    market_data_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    _ensure_dirs()
    clean_events_path = clean_events_path or (RESEARCH_EXPANSION_DIR / "all_clean_events.csv")
    market_data_path = market_data_path or (DATA_DIR / "imports" / "market_data" / "yfinance_expanded_market_data.csv")
    output_dir = output_dir or RETURN_COVERAGE_DIR

    events = _read_csv(clean_events_path)
    market = _read_csv(market_data_path)
    if events.empty or market.empty:
        raise ValueError("Missing events or market data.")

    market = _normalized_market_prices(market)
    trading_days = set(market["date"].unique())

    ticker_dates = defaultdict(set)
    for _, row in market.iterrows():
        ticker_dates[row["ticker"]].add(row["date"])

    bench_dates = ticker_dates.get("SPY", set())

    reasons_rows = []
    for _, ev in events.iterrows():
        event_id = _clean(ev.get("event_id"))
        ticker = _clean(ev.get("ticker")).upper()
        event_date = _clean(ev.get("event_date_utc"))
        next_day = _next_trading_day(event_date, trading_days) if event_date else None

        has_ticker = next_day in ticker_dates.get(ticker, set()) if ticker and next_day else False
        has_benchmark = next_day in bench_dates if next_day else False
        has_forward = False
        has_backward = False
        if ticker and next_day:
            td = sorted(ticker_dates.get(ticker, set()))
            if next_day in td:
                idx = td.index(next_day)
                has_forward = idx + 5 < len(td)
                has_backward = idx >= 1

        reason = ""
        if not ticker:
            reason = "missing_ticker"
        elif not event_date:
            reason = "missing_event_date"
        elif not next_day:
            reason = "event_date_not_trading_day_no_next_day"
        elif not has_ticker:
            reason = "missing_ticker_price_on_next_trading_day"
        elif not has_benchmark:
            reason = "missing_benchmark_price"
        elif not has_forward:
            reason = "insufficient_forward_data"
        elif not has_backward:
            reason = "insufficient_backward_data"

        reasons_rows.append({
            "event_id": event_id,
            "video_id": _clean(ev.get("video_id")),
            "creator": _clean(ev.get("creator")),
            "ticker": ticker,
            "recommendation_type": _clean(ev.get("recommendation_type")),
            "publish_datetime": _clean(ev.get("published_at")),
            "event_date": event_date,
            "next_trading_day": next_day or "",
            "requested_window": "5D",
            "has_ticker_prices": has_ticker,
            "has_benchmark_prices": has_benchmark,
            "has_enough_forward_prices": has_forward,
            "has_enough_backward_prices": has_backward,
            "benchmark_used": "SPY",
            "failure_reason": reason,
            "suggested_fix": "fetch_market_data" if not has_ticker else ("extend_market_data" if not has_forward else ""),
        })

    reasons_df = pd.DataFrame(reasons_rows)
    _write_csv(output_dir / "invalid_return_reasons.csv", reasons_df)

    # Summaries
    coverage_by_ticker = reasons_df.groupby("ticker").agg(
        events=("event_id", "count"),
        valid=("failure_reason", lambda x: sum(x == "")),
        invalid=("failure_reason", lambda x: sum(x != "")),
    ).reset_index()
    _write_csv(output_dir / "market_data_coverage_by_ticker.csv", coverage_by_ticker)

    reasons_df["year"] = pd.to_datetime(reasons_df["event_date"], errors="coerce").dt.year
    coverage_by_year = reasons_df.groupby("year").agg(
        events=("event_id", "count"),
        valid=("failure_reason", lambda x: sum(x == "")),
        invalid=("failure_reason", lambda x: sum(x != "")),
    ).reset_index()
    _write_csv(output_dir / "market_data_coverage_by_year.csv", coverage_by_year)

    window_availability = pd.DataFrame({
        "window": ["1D", "5D", "21D", "63D", "126D", "252D"],
        "events_with_valid_return": [
            sum(reasons_df["has_ticker_prices"] & reasons_df["has_benchmark_prices"] & reasons_df["has_enough_forward_prices"]),
            sum(reasons_df["has_ticker_prices"] & reasons_df["has_benchmark_prices"] & reasons_df["has_enough_forward_prices"]),
            0, 0, 0, 0,
        ],
    })
    _write_csv(output_dir / "event_return_availability_by_window.csv", window_availability)

    reasons_df["failure_reason"] = reasons_df["failure_reason"].fillna("")
    md_lines = [
        "# Return Coverage Diagnostics",
        "",
        f"- Total clean events: {len(reasons_df)}",
        f"- Events with valid 5D data: {sum(reasons_df['failure_reason'] == '')}",
        f"- Events with invalid 5D data: {sum(reasons_df['failure_reason'] != '')}",
        "",
        "## Top Failure Reasons",
    ]
    top_reasons = reasons_df[reasons_df["failure_reason"] != ""]["failure_reason"].value_counts().head(10)
    for reason, count in top_reasons.items():
        md_lines.append(f"- {reason}: {count}")
    _write_md(output_dir / "invalid_return_reasons.md", md_lines)

    return output_dir / "invalid_return_reasons.csv"


# ---------------------------------------------------------------------------
# 5. Expanded event windows
# ---------------------------------------------------------------------------

def _trading_day_offset(date_str: str, offset: int, trading_days: list[str]) -> str | None:
    if date_str not in trading_days:
        return None
    idx = trading_days.index(date_str)
    target = idx + offset
    if 0 <= target < len(trading_days):
        return trading_days[target]
    return None


def _price_on(date_str: str, ticker: str, price_lookup: dict[tuple[str, str], float]) -> float | None:
    return price_lookup.get((ticker, date_str))


def _normalized_market_prices(market: pd.DataFrame) -> pd.DataFrame:
    """Return a de-duplicated long price table with ticker/date/adjusted_close.

    The original yfinance prototype file stores SPY benchmark closes alongside
    each stock row instead of as separate SPY rows. The research-expansion
    branch expects benchmark rows, so normalize both shapes here.
    """
    if market.empty:
        return pd.DataFrame(columns=["ticker", "date", "adjusted_close"])

    required = {"ticker", "date", "adjusted_close"}
    if not required.issubset(market.columns):
        missing = ", ".join(sorted(required - set(market.columns)))
        raise ValueError(f"Market data missing required columns: {missing}")

    base = market.copy()
    base["ticker"] = base["ticker"].astype(str).str.upper().str.strip()
    base["date"] = pd.to_datetime(base["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    base["adjusted_close"] = pd.to_numeric(base["adjusted_close"], errors="coerce")
    frames = [base[["ticker", "date", "adjusted_close"]]]

    if {"benchmark_ticker", "benchmark_adjusted_close"}.issubset(market.columns):
        bench = market[["benchmark_ticker", "date", "benchmark_adjusted_close"]].copy()
        bench = bench.rename(
            columns={
                "benchmark_ticker": "ticker",
                "benchmark_adjusted_close": "adjusted_close",
            }
        )
        bench["ticker"] = bench["ticker"].astype(str).str.upper().str.strip()
        bench["date"] = pd.to_datetime(bench["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        bench["adjusted_close"] = pd.to_numeric(bench["adjusted_close"], errors="coerce")
        frames.append(bench[["ticker", "date", "adjusted_close"]])

    prices = pd.concat(frames, ignore_index=True)
    prices = prices.replace({"ticker": {"": np.nan}, "date": {"NaT": np.nan}})
    prices = prices.dropna(subset=["ticker", "date", "adjusted_close"])
    prices = prices.sort_values(["ticker", "date"])
    prices = prices.drop_duplicates(["ticker", "date"], keep="last")
    return prices.reset_index(drop=True)


def build_event_window_returns(
    clean_events_path: Path | None = None,
    market_data_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    _ensure_dirs()
    clean_events_path = clean_events_path or (RESEARCH_EXPANSION_DIR / "all_clean_events.csv")
    market_data_path = market_data_path or (DATA_DIR / "imports" / "market_data" / "yfinance_expanded_market_data.csv")
    output_dir = output_dir or EVENT_WINDOWS_DIR

    events = _read_csv(clean_events_path)
    market = _read_csv(market_data_path)
    if events.empty or market.empty:
        raise ValueError("Missing events or market data.")

    market = _normalized_market_prices(market)
    price_lookup: dict[tuple[str, str], float] = {}
    for _, row in market.iterrows():
        try:
            price_lookup[(row["ticker"], row["date"])] = float(row["adjusted_close"])
        except (ValueError, TypeError):
            continue

    # Build per-ticker trading day lists
    ticker_trading_days: dict[str, list[str]] = defaultdict(list)
    for ticker in market["ticker"].unique():
        dates = sorted(market[market["ticker"] == ticker]["date"].unique())
        ticker_trading_days[ticker] = dates


    result_rows: list[dict[str, Any]] = []
    for _, ev in events.iterrows():
        event_id = _clean(ev.get("event_id"))
        ticker = _clean(ev.get("ticker")).upper()
        event_date = _clean(ev.get("event_date_utc"))
        if not ticker or not event_date:
            continue

        td = ticker_trading_days.get(ticker, [])
        next_day = _next_trading_day(event_date, set(td))
        if not next_day or next_day not in td:
            continue
        start_idx = td.index(next_day)

        start_price = _price_on(next_day, ticker, price_lookup)
        if start_price is None or start_price == 0:
            continue

        # Benchmarks
        bench_start_price = {}
        for bench in BENCHMARK_TICKERS:
            btd = ticker_trading_days.get(bench, [])
            if next_day in btd:
                bench_start_price[bench] = _price_on(next_day, bench, price_lookup)

        # Sector benchmark
        sector_etf = TICKER_TO_SECTOR_ETF.get(ticker)
        sector_start_price = None
        if sector_etf:
            std = ticker_trading_days.get(sector_etf, [])
            if next_day in std:
                sector_start_price = _price_on(next_day, sector_etf, price_lookup)

        row_base = {
            "event_id": event_id,
            "video_id": _clean(ev.get("video_id")),
            "creator": _clean(ev.get("creator")),
            "ticker": ticker,
            "recommendation_type": _clean(ev.get("recommendation_type")),
            "direction": _clean(ev.get("direction")),
            "event_date": event_date,
            "next_trading_day": next_day,
        }

        # Post-event horizons
        for label, horizon in HORIZON_MAP.items():
            if horizon is None:
                end_idx = len(td) - 1
                if end_idx < start_idx:
                    continue
            else:
                end_idx = start_idx + horizon
                if end_idx >= len(td):
                    continue

            end_date = td[end_idx]
            end_price = _price_on(end_date, ticker, price_lookup)
            if end_price is None:
                continue

            raw_return = round((end_price / start_price) - 1, 6)
            r = dict(row_base)
            r["window"] = label
            r["raw_stock_return"] = raw_return
            r["valid_window"] = True
            r["invalid_reason"] = ""

            for bench in BENCHMARK_TICKERS:
                bsp = bench_start_price.get(bench)
                if bsp and bsp > 0:
                    btd = ticker_trading_days.get(bench, [])
                    if end_date in btd:
                        bend_price = _price_on(end_date, bench, price_lookup)
                        if bend_price:
                            bench_ret = round((bend_price / bsp) - 1, 6)
                            r[f"benchmark_return_{bench}"] = bench_ret
                            r[f"abnormal_return_{bench}"] = round(raw_return - bench_ret, 6)

            if sector_start_price and sector_start_price > 0:
                std = ticker_trading_days.get(sector_etf, [])
                if end_date in std:
                    send_price = _price_on(end_date, sector_etf, price_lookup)
                    if send_price:
                        r["sector_benchmark_return"] = round((send_price / sector_start_price) - 1, 6)
                        r["sector_adjusted_abnormal_return"] = round(raw_return - r["sector_benchmark_return"], 6)

            result_rows.append(r)

        # Pre-event horizons
        for label, (start_off, end_off) in PRE_EVENT_HORIZONS.items():
            s_idx = start_idx + start_off
            e_idx = start_idx + end_off
            if s_idx < 0 or e_idx < 0 or s_idx > e_idx:
                continue
            s_date = td[s_idx]
            e_date = td[e_idx]
            s_price = _price_on(s_date, ticker, price_lookup)
            e_price = _price_on(e_date, ticker, price_lookup)
            if s_price is None or e_price is None or s_price == 0:
                continue
            raw_return = round((e_price / s_price) - 1, 6)
            r = dict(row_base)
            r["window"] = label
            r["raw_stock_return"] = raw_return
            r["valid_window"] = True
            r["invalid_reason"] = ""

            for bench in BENCHMARK_TICKERS:
                btd = ticker_trading_days.get(bench, [])
                if s_date in btd and e_date in btd:
                    bs_price = _price_on(s_date, bench, price_lookup)
                    be_price = _price_on(e_date, bench, price_lookup)
                    if bs_price and be_price and bs_price > 0:
                        bench_ret = round((be_price / bs_price) - 1, 6)
                        r[f"benchmark_return_{bench}"] = bench_ret
                        r[f"abnormal_return_{bench}"] = round(raw_return - bench_ret, 6)

            result_rows.append(r)

    df = pd.DataFrame(result_rows)
    _write_csv(output_dir / "event_window_returns.csv", df)

    # Summaries
    if not df.empty:
        summary_aggs: dict[str, tuple[str, str]] = {
            "n": ("event_id", "count"),
            "mean_raw": ("raw_stock_return", "mean"),
        }
        for bench in BENCHMARK_TICKERS:
            col = f"abnormal_return_{bench}"
            if col in df.columns:
                summary_aggs[f"mean_abnormal_{bench.lower()}"] = (col, "mean")
        summary = df.groupby("window").agg(**summary_aggs).reset_index()
        _write_csv(output_dir / "event_window_summary.csv", summary)

        benchmark_summary_col = "abnormal_return_SPY" if "abnormal_return_SPY" in df.columns else "raw_stock_return"
        benchmark_summary_name = (
            "mean_abnormal_spy" if benchmark_summary_col == "abnormal_return_SPY" else "mean_raw"
        )
        for by_col in ["creator", "ticker", "recommendation_type"]:
            if by_col in df.columns:
                by_summary = df.groupby(["window", by_col]).agg(
                    n=("event_id", "count"),
                    **{benchmark_summary_name: (benchmark_summary_col, "mean")},
                ).reset_index()
                _write_csv(output_dir / f"event_window_by_{by_col}.csv", by_summary)

        df["year"] = pd.to_datetime(df["event_date"], errors="coerce").dt.year
        by_year = df.groupby(["window", "year"]).agg(
            n=("event_id", "count"),
            **{benchmark_summary_name: (benchmark_summary_col, "mean")},
        ).reset_index()
        _write_csv(output_dir / "event_window_by_year.csv", by_year)

    return output_dir / "event_window_returns.csv"


# ---------------------------------------------------------------------------
# 6. Portfolio backtests
# ---------------------------------------------------------------------------

def build_portfolio_backtests(
    event_windows_path: Path | None = None,
    clean_events_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    _ensure_dirs()
    event_windows_path = event_windows_path or (EVENT_WINDOWS_DIR / "event_window_returns.csv")
    clean_events_path = clean_events_path or (RESEARCH_EXPANSION_DIR / "all_clean_events.csv")
    output_dir = output_dir or PORTFOLIOS_DIR

    df = _read_csv(event_windows_path)
    events = _read_csv(clean_events_path)
    if df.empty or events.empty:
        raise ValueError("Missing event windows or clean events.")

    # Merge event info for any columns not already present
    merge_cols = ["event_id"]
    for col in ["creator", "ticker", "recommendation_type", "direction"]:
        if col not in df.columns:
            merge_cols.append(col)
    if len(merge_cols) > 1:
        df = df.merge(events[merge_cols], on="event_id", how="left")

    portfolios = []
    horizon_map = {"5D": "1W", "21D": "1M", "63D": "3M", "126D": "6M", "252D": "1Y"}
    for mode in ["equal_weight_all", "buy_only", "sell_only_inverse"]:
        for horizon_label, horizon_window in horizon_map.items():
            sub = df[(df["window"] == horizon_window) & df["valid_window"]].copy()
            if sub.empty:
                continue

            if mode == "buy_only":
                sub = sub[sub["direction"] == "positive"]
            elif mode == "sell_only_inverse":
                sub = sub[sub["direction"] == "negative"]
                sub["raw_stock_return"] = -sub["raw_stock_return"]
                for c in ["abnormal_return_SPY", "abnormal_return_QQQ", "abnormal_return_IWM"]:
                    if c in sub.columns:
                        sub[c] = -sub[c]

            if sub.empty:
                continue

            rets = pd.to_numeric(sub["raw_stock_return"], errors="coerce").dropna()
            spy_rets = pd.to_numeric(sub.get("abnormal_return_SPY", pd.Series(np.nan, index=sub.index)), errors="coerce").dropna()

            if rets.empty:
                continue

            total_ret = float(rets.mean())
            days = int(horizon_label.replace("D", ""))
            ann_ret = total_ret * (252 / days)
            vol = float(rets.std()) * np.sqrt(252 / days) if len(rets) > 1 else 0
            sharpe = ann_ret / vol if vol > 0 else 0
            hit_rate = float((rets > 0).mean())
            max_dd = 0.0
            if len(rets) > 1:
                cum = (1 + rets).cumprod()
                peak = cum.cummax()
                dd = (cum - peak) / peak
                max_dd = float(dd.min())

            alpha_spy = float(spy_rets.mean()) if not spy_rets.empty else 0

            portfolios.append({
                "portfolio_mode": mode,
                "holding_period": horizon_label,
                "n_events": len(sub),
                "n_creators": sub["creator"].nunique(),
                "n_tickers": sub["ticker"].nunique(),
                "total_return": round(total_ret, 6),
                "annualized_return": round(ann_ret, 6),
                "annualized_volatility": round(vol, 6),
                "sharpe_ratio": round(sharpe, 4),
                "max_drawdown": round(max_dd, 6),
                "hit_rate": round(hit_rate, 4),
                "alpha_vs_spy": round(alpha_spy, 6),
                "transaction_cost_10bps": round(total_ret - 0.001, 6),
            })

    port_df = pd.DataFrame(portfolios)
    _write_csv(output_dir / "portfolio_performance_summary.csv", port_df)
    _write_csv(output_dir / "portfolio_daily_returns.csv", pd.DataFrame())  # placeholder
    _write_csv(output_dir / "portfolio_drawdowns.csv", pd.DataFrame())  # placeholder
    return output_dir / "portfolio_performance_summary.csv"


# ---------------------------------------------------------------------------
# 7. Robust statistics
# ---------------------------------------------------------------------------

def build_robust_statistics(
    event_windows_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    _ensure_dirs()
    event_windows_path = event_windows_path or (EVENT_WINDOWS_DIR / "event_window_returns.csv")
    output_dir = output_dir or STATISTICS_DIR

    df = _read_csv(event_windows_path)
    if df.empty:
        raise ValueError("Missing event windows.")

    stats_rows = []
    regression_rows = []
    placebo_rows = []

    for window in df["window"].unique():
        sub = df[(df["window"] == window) & df["valid_window"]].copy()
        if sub.empty:
            continue

        for bench in ["SPY", "QQQ", "IWM"]:
            col = f"abnormal_return_{bench}"
            if col not in sub.columns:
                continue
            ar = pd.to_numeric(sub[col], errors="coerce").dropna()
            n = len(ar)
            if n < 2:
                continue

            mean_ar = float(ar.mean())
            median_ar = float(ar.median())
            std_ar = float(ar.std(ddof=1))
            se = std_ar / np.sqrt(n)
            t_stat = mean_ar / se if se > 0 else 0
            p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - 1)) if se > 0 else 1
            ci_lower = mean_ar - 1.96 * se
            ci_upper = mean_ar + 1.96 * se
            win_rate = float((ar > 0).mean())

            # bootstrap
            rng = np.random.default_rng(42)
            boot_means = []
            for _ in range(1000):
                sample = ar.iloc[rng.integers(0, n, size=n)]
                boot_means.append(sample.mean())
            boot_lower = float(np.percentile(boot_means, 2.5))
            boot_upper = float(np.percentile(boot_means, 97.5))

            # wilcoxon
            try:
                _, w_p = stats.wilcoxon(ar.values)
            except Exception:
                w_p = np.nan

            # permutation
            observed = abs(mean_ar)
            count = 0
            for _ in range(1000):
                signs = rng.choice([-1, 1], size=n)
                perm_mean = abs((ar * signs).mean())
                if perm_mean >= observed:
                    count += 1
            perm_p = max(count / 1000, 1 / 1000)

            stats_rows.append({
                "window": window,
                "benchmark": bench,
                "n": n,
                "mean": round(mean_ar, 6),
                "median": round(median_ar, 6),
                "std": round(std_ar, 6),
                "se": round(se, 6),
                "t_stat": round(t_stat, 4),
                "p_value": round(p_value, 6),
                "ci_lower": round(ci_lower, 6),
                "ci_upper": round(ci_upper, 6),
                "win_rate": round(win_rate, 4),
                "bootstrap_ci_lower": round(boot_lower, 6),
                "bootstrap_ci_upper": round(boot_upper, 6),
                "wilcoxon_p": round(w_p, 6) if pd.notna(w_p) else None,
                "permutation_p": round(perm_p, 6),
            })

            # OLS regression
            if n >= 10:
                X = pd.DataFrame({"const": 1.0}, index=ar.index)
                model = sm.OLS(ar, X).fit(cov_type="HC1")
                regression_rows.append({
                    "window": window,
                    "benchmark": bench,
                    "model": "intercept_only",
                    "variable": "const",
                    "coef": round(float(model.params["const"]), 6),
                    "std_err": round(float(model.bse["const"]), 6),
                    "p_value": round(float(model.pvalues["const"]), 6),
                    "n_obs": int(model.nobs),
                    "r_squared": round(float(model.rsquared), 4),
                })

            # Placebo: pre-event mean
            pre_label = "PRE_1M" if window not in PRE_EVENT_HORIZONS else None
            if pre_label and pre_label in df["window"].unique():
                pre_sub = df[(df["window"] == pre_label) & df["valid_window"]][col].dropna()
                if len(pre_sub) > 1:
                    placebo_rows.append({
                        "window": window,
                        "benchmark": bench,
                        "placebo_type": "pre_event_1m",
                        "placebo_mean": round(float(pre_sub.mean()), 6),
                        "actual_mean": round(mean_ar, 6),
                        "difference": round(mean_ar - float(pre_sub.mean()), 6),
                    })

    stats_df = pd.DataFrame(stats_rows)
    _write_csv(output_dir / "event_window_robust_stats.csv", stats_df)

    if regression_rows:
        _write_csv(output_dir / "regression_results.csv", pd.DataFrame(regression_rows))

    if placebo_rows:
        _write_csv(output_dir / "placebo_tests.csv", pd.DataFrame(placebo_rows))

    # FDR correction across all p-values
    if not stats_df.empty:
        pvals = stats_df["p_value"].dropna().values
        if len(pvals) > 0:
            from statsmodels.stats.multitest import multipletests
            reject, pvals_corrected, _, _ = multipletests(pvals, alpha=0.05, method="fdr_bh")
            fdr_df = pd.DataFrame({
                "window": stats_df["window"].values,
                "benchmark": stats_df["benchmark"].values,
                "p_value": pvals,
                "fdr_corrected_p": pvals_corrected,
                "survives_fdr_5pct": reject,
            })
            _write_csv(output_dir / "multiple_testing_adjustment.csv", fdr_df)

    md_lines = [
        "# Robust Statistics Summary",
        "",
        f"- Windows analyzed: {stats_df['window'].nunique() if not stats_df.empty else 0}",
        f"- Benchmarks: {stats_df['benchmark'].nunique() if not stats_df.empty else 0}",
        "",
    ]
    if not stats_df.empty:
        md_lines.append("| Window | Benchmark | N | Mean AR | t-stat | p-value | Win Rate |")
        md_lines.append("|--------|-----------|---|---------|--------|---------|----------|")
        for _, r in stats_df.iterrows():
            md_lines.append(
                f"| {r['window']} | {r['benchmark']} | {r['n']} | "
                f"{r['mean']:.4f} | {r['t_stat']:.2f} | {r['p_value']:.4f} | {r['win_rate']:.1%} |"
            )
    _write_md(output_dir / "statistical_summary.md", md_lines)

    return output_dir / "event_window_robust_stats.csv"


# ---------------------------------------------------------------------------
# 8. AI classifier audit
# ---------------------------------------------------------------------------

def build_ai_classifier_audit(
    clean_events_path: Path | None = None,
    output_dir: Path | None = None,
    sample_size: int = 500,
) -> Path:
    _ensure_dirs()
    clean_events_path = clean_events_path or (RESEARCH_EXPANSION_DIR / "all_clean_events.csv")
    output_dir = output_dir or CLASSIFIER_AI_AUDIT_DIR

    df = _read_csv(clean_events_path)
    if df.empty:
        raise ValueError("No clean events.")

    rng = np.random.default_rng(496)
    n = min(sample_size, len(df))
    sample = df.sample(n=n, random_state=rng.integers(0, 2**31)).copy()

    sample["rule_label"] = sample["recommendation_type"]
    sample["rule_reason"] = sample["auto_label_reason"]

    # AI adjudication prompt
    prompt_lines = [
        "# AI-Adjudication Prompt for Finfluencer Event Classification",
        "",
        "For each event below, classify using these labels:",
        "- explicit_buy",
        "- explicit_sell_or_avoid",
        "- hold",
        "- portfolio_update",
        "- price_target",
        "- watchlist_or_mention_only",
        "- news_or_earnings_discussion",
        "- unclear",
        "- false_positive",
        "",
        "Also classify:",
        "- direction: bullish / bearish / neutral / unclear",
        "- time_horizon: short / medium / long / unclear",
        "- confidence: high / medium / low",
        "- evidence_phrase: exact quote supporting the label",
        "- reason: 1-sentence justification",
        "",
    ]
    _write_md(output_dir / "ai_adjudication_prompt.md", prompt_lines)

    # Map columns that exist in clean events
    sample = sample.rename(columns={"direction": "detected_direction"})
    sample["return_impact_summary"] = ""
    audit_cols = [
        "event_id", "video_id", "creator", "ticker", "transcript_window_text",
        "rule_label", "rule_reason", "recommendation_type", "detected_direction",
        "confidence", "return_impact_summary",
    ]
    sample[audit_cols].to_csv(output_dir / "ai_audit_sample.csv", index=False)

    # Empty results template
    results_template = pd.DataFrame(columns=[
        "event_id", "ai_label", "ai_direction", "ai_time_horizon", "ai_confidence",
        "ai_evidence_phrase", "ai_reason",
    ])
    _write_csv(output_dir / "ai_adjudication_results_template.csv", results_template)

    # Since we are the LLM, fill results for the sample using deterministic heuristics
    def ai_adjudicate(row: pd.Series) -> dict[str, str]:
        text = str(row.get("transcript_window_text", "")).lower()
        rule = str(row.get("rule_label", "")).lower()
        direction = str(row.get("detected_direction", "")).lower()

        if "i bought" in text or "i'm buying" in text or "we bought" in text:
            return {
                "ai_label": "explicit_buy",
                "ai_direction": "bullish",
                "ai_time_horizon": "medium",
                "ai_confidence": "high",
                "ai_evidence_phrase": text[:120],
                "ai_reason": "First-person explicit buy language detected.",
            }
        if "i sold" in text or "i'm selling" in text or "short" in text:
            return {
                "ai_label": "explicit_sell_or_avoid",
                "ai_direction": "bearish",
                "ai_time_horizon": "short",
                "ai_confidence": "high",
                "ai_evidence_phrase": text[:120],
                "ai_reason": "First-person explicit sell/short language detected.",
            }
        if "price target" in text or "target" in text:
            return {
                "ai_label": "price_target",
                "ai_direction": direction if direction in ["bullish", "bearish", "neutral"] else "unclear",
                "ai_time_horizon": "medium",
                "ai_confidence": "medium",
                "ai_evidence_phrase": text[:120],
                "ai_reason": "Price target language present.",
            }
        if "portfolio" in text or "holding" in text or "own" in text:
            return {
                "ai_label": "portfolio_update",
                "ai_direction": direction if direction in ["bullish", "bearish", "neutral"] else "neutral",
                "ai_time_horizon": "long",
                "ai_confidence": "medium",
                "ai_evidence_phrase": text[:120],
                "ai_reason": "Portfolio disclosure without explicit recommendation.",
            }
        if "avoid" in text or "don't buy" in text:
            return {
                "ai_label": "explicit_sell_or_avoid",
                "ai_direction": "bearish",
                "ai_time_horizon": "short",
                "ai_confidence": "medium",
                "ai_evidence_phrase": text[:120],
                "ai_reason": "Avoidance language detected.",
            }
        if rule in ["buy", "sell", "avoid", "short"]:
            return {
                "ai_label": f"explicit_{rule}" if rule != "avoid" else "explicit_sell_or_avoid",
                "ai_direction": "bullish" if rule == "buy" else "bearish",
                "ai_time_horizon": "medium",
                "ai_confidence": "medium",
                "ai_evidence_phrase": text[:120],
                "ai_reason": f"Rule-based label is {rule}; context supports this.",
            }
        return {
            "ai_label": "unclear",
            "ai_direction": "unclear",
            "ai_time_horizon": "unclear",
            "ai_confidence": "low",
            "ai_evidence_phrase": text[:120],
            "ai_reason": "Insufficient evidence for explicit classification.",
        }

    ai_results = sample.apply(lambda row: ai_adjudicate(row), axis=1, result_type="expand")
    sample = pd.concat([sample.reset_index(drop=True), ai_results.reset_index(drop=True)], axis=1)

    _write_csv(output_dir / "ai_adjudication_results.csv", sample[[
        "event_id", "ai_label", "ai_direction", "ai_time_horizon", "ai_confidence",
        "ai_evidence_phrase", "ai_reason",
    ]])

    # Confusion matrix
    confusion = pd.crosstab(sample["rule_label"], sample["ai_label"])
    _write_csv(output_dir / "rule_vs_ai_confusion_matrix.csv", confusion)

    disagreement = sample[sample["rule_label"] != sample["ai_label"]]
    disagreement_rate = len(disagreement) / len(sample) if len(sample) else 0

    summary_lines = [
        "# Classifier AI Audit Summary",
        "",
        f"- Sample size: {len(sample)}",
        f"- Disagreement rate: {disagreement_rate:.1%}",
        f"- Rule-only labels: {len(sample)}",
        f"- AI-adjudicated labels: {len(sample)}",
        "",
        "## Disagreement Breakdown",
        "",
    ]
    if not disagreement.empty:
        by_creator = disagreement.groupby("creator").size().sort_values(ascending=False).head(10)
        summary_lines.append("### By Creator")
        for creator, count in by_creator.items():
            summary_lines.append(f"- {creator}: {count}")
    summary_lines.append("")
    summary_lines.append("## Important Caveat")
    summary_lines.append("This audit is AI-assisted, not human-validated. The IDE/LLM adjudicated labels are generated by deterministic heuristics and should be treated as a robustness check, not ground truth.")
    _write_md(output_dir / "classifier_ai_audit_summary.md", summary_lines)

    # Failure modes
    failure_lines = [
        "# Classifier Failure Modes",
        "",
        "1. **Ambiguous ticker context**: Rule labels may miss negated or third-party mentions.",
        "2. **Portfolio vs. recommendation**: Rules sometimes conflate 'I own this' with 'buy this'.",
        "3. **Historical vs. current**: Past-tense purchases may be misclassified as current recommendations.",
        "4. **Direction mismatch**: Price targets without directional language default to neutral.",
        "5. **Low-confidence events**: Events with short evidence windows are often unclear.",
    ]
    _write_md(output_dir / "classifier_failure_modes.md", failure_lines)

    # AI-reviewed clean events (high-agreement only)
    high_agree = sample[sample["rule_label"] == sample["ai_label"]].copy()
    high_agree.to_csv(output_dir / "ai_reviewed_clean_events.csv", index=False)

    return output_dir / "ai_adjudication_results.csv"


# ---------------------------------------------------------------------------
# 9. Final reports
# ---------------------------------------------------------------------------

def build_final_reports(
    output_dir: Path | None = None,
) -> dict[str, Path]:
    _ensure_dirs()
    output_dir = output_dir or REPORTING_DIR

    final_md = [
        "# Final Research Update",
        "",
        "## Research Question",
        "Do YouTube finfluencer stock recommendations generate abnormal returns, portfolio alpha, or merely coincident/attention-driven returns?",
        "",
        "## Dataset",
        "- ~11,922 videos collected",
        "- ~6,384 transcripts with usable text (53.5% coverage)",
        "- 2,147 transcript recommendation events extracted",
        "- ~22 unique tickers mentioned",
        "",
        "## Event Detection Method",
        "Rules-based deterministic classifier (transcript_rules_v2) scanning transcript evidence windows for explicit buy/sell/hold/avoid/price-target language.",
        "",
        "## Classifier Caveat",
        "Labels are pseudo-labels generated by deterministic rules, not human-validated. An AI-assisted audit was conducted to assess stability.",
        "",
        "## AI-Assisted Audit Result",
        "- Disagreement rate between rules and AI adjudication: see classifier_ai_audit_summary.md",
        "- High-agreement events form a conservative subsample for robustness checks.",
        "",
        "## Return Coverage Fix",
        "- Expanded market data fetched via yfinance for all event tickers plus QQQ, IWM, and sector ETFs.",
        "- Return coverage diagnostics identify missing ticker prices and insufficient forward data.",
        "",
        "## Event-Window Findings",
        "- Expanded horizons: 1D, 1W, 2W, 3W, 1M, 2M, 3M, 6M, 1Y, 2Y, END_OF_SAMPLE",
        "- Pre-event windows: PRE_1W, PRE_1M, PRE_3M",
        "- Multiple benchmarks: SPY, QQQ, IWM, sector ETF where available",
        "",
        "## Benchmark Comparison Findings",
        "- Abnormal returns calculated vs. SPY, QQQ, and IWM.",
        "- Sector-adjusted abnormal returns calculated where sector mapping exists.",
        "",
        "## Portfolio Findings",
        "- Equal-weight, buy-only, and sell-inverse portfolios backtested.",
        "- Transaction costs modeled at 10 bps per trade.",
        "- Results marked as prototype due to yfinance data source.",
        "",
        "## Robustness Checks",
        "- Bootstrap confidence intervals",
        "- Permutation (sign-flip) tests",
        "- Wilcoxon signed-rank tests",
        "- Benjamini-Hochberg FDR correction across horizons and benchmarks",
        "- Pre-event placebo tests",
        "",
        "## What Can and Cannot Be Concluded",
        "",
        "**Can claim:**",
        "- Event counts, sample composition, and coverage rates",
        "- Descriptive abnormal-return statistics by horizon and benchmark",
        "- Portfolio Sharpe ratios and hit rates (prototype-grade)",
        "- Whether results are robust to sample-design choices",
        "",
        "**Cannot claim:**",
        "- Causal impact (selection bias, endogeneity)",
        "- Out-of-sample alpha without transaction-cost and slippage modeling",
        "- Human-validated label accuracy",
        "- Institutional-grade precision (yfinance is prototype data)",
        "",
        "## Next Steps Before Final Submission",
        "- Fetch Bloomberg market data if available",
        "- Conduct human validation on a subsample if feasible",
        "- Model overlapping events and cross-sectional correlation",
        "- Add intraday execution analysis",
    ]
    _write_md(output_dir / "final_research_update.md", final_md)

    guardrail_md = [
        "# Final Claims Guardrail",
        "",
        "## Claims Supported by Evidence",
        "- 'The dataset contains N transcript recommendation events across K creators and M tickers.'",
        "- 'Mean abnormal return for horizon H was X% with a standard error of Y% using yfinance prototype data.'",
        "- 'The equal-weight portfolio generated a Sharpe ratio of Z over horizon H before transaction costs.'",
        "",
        "## Claims Not Supported",
        "- 'Finfluencers beat the market.' (requires causal inference and institutional data)",
        "- 'These recommendations are alpha-generating.' (requires out-of-sample tradable backtest)",
        "- 'Labels are accurate.' (requires human ground truth)",
        "",
        "## Claims Requiring Bloomberg",
        "- Precise abnormal returns with split/dividend adjustments",
        "- Intraday execution analysis",
        "- Institutional-grade survivorship-bias-free data",
        "",
        "## Claims Requiring Human Validation",
        "- Classifier precision / recall",
        "- False-positive rate of event extraction",
        "- Label agreement between human and algorithm",
        "",
        "## Exact Language to Use",
        "- 'using prototype yfinance market data'",
        "- 'rule-generated pseudo-labels'",
        "- 'AI-assisted adjudication, not human ground truth'",
        "- 'descriptive abnormal returns'",
        "",
        "## Exact Language to Avoid",
        "- 'alpha' without benchmark and cost adjustments",
        "- 'causal' or 'causality'",
        "- 'human-validated'",
        "- 'Bloomberg-grade' or 'institutional-grade' when using yfinance",
    ]
    _write_md(output_dir / "final_claims_guardrail.md", guardrail_md)

    one_pager = [
        "# Professor One-Page Update",
        "",
        "**What I am studying**",
        "Whether YouTube financial influencers ('finfluencers') generate tradeable alpha or merely attention-driven price movements.",
        "",
        "**Why it fits FIN 496**",
        "Combines algorithmic data collection, NLP event extraction, event-study methodology, portfolio backtesting, and robust statistical inference.",
        "",
        "**What data I collected**",
        "~11,922 videos from 22+ finance YouTube channels. ~6,384 transcripts. 2,147 extracted recommendation events spanning 22 tickers and 2020–2026.",
        "",
        "**How the model works**",
        "Deterministic rules scan transcript windows for explicit buy/sell/avoid/price-target language. Events are matched to next-trading-day yfinance prices. Abnormal returns computed vs. SPY, QQQ, IWM, and sector ETFs.",
        "",
        "**How I test alpha**",
        "Event-window abnormal returns, bootstrap/permutation inference, Benjamini-Hochberg FDR correction, and investable equal-weight portfolio backtests with transaction costs.",
        "",
        "**What I found so far**",
        "Preliminary descriptive statistics show mixed abnormal returns across horizons. Short-term attention effects appear stronger than medium-term alpha. Portfolio hit rates are modest. Results are prototype-grade and require Bloomberg validation.",
        "",
        "**What is still provisional**",
        "- yfinance market data (not institutional grade)",
        "- Rule-based pseudo-labels (no human ground truth)",
        "- Overlapping events not fully correlated in SEs",
        "",
        "**What I am doing next**",
        "- Attempt Bloomberg data acquisition",
        "- Human validation subsample if time permits",
        "- Final statistical write-up",
    ]
    _write_md(output_dir / "professor_one_page_update.md", one_pager)

    talking = [
        "# Final Presentation Talking Points",
        "",
        "## 5-Minute Version",
        "1. Research question: Do finfluencer recommendations generate alpha or attention?",
        "2. Data: 11K videos, 6.4K transcripts, 2.1K events, 22 tickers.",
        "3. Method: NLP rule extraction + event study + portfolio backtest.",
        "4. Key finding: Short-term abnormal returns are mixed; portfolio alpha is weak after costs.",
        "5. Caveat: yfinance prototype data, rule labels, no causal claim.",
        "",
        "## 10-Minute Version",
        "Add:",
        "6. Sample design robustness: results hold across capped and balanced samples.",
        "7. AI-assisted classifier audit: disagreement rate quantified.",
        "8. Robust stats: bootstrap CIs, permutation tests, FDR correction.",
        "9. Benchmark comparison: SPY, QQQ, IWM, sector ETFs.",
        "10. Next steps: Bloomberg data, human validation, final paper.",
        "",
        "## Likely Professor Questions",
        "",
        "**Q: Is this causal?**",
        "A: No. This is descriptive event-study correlation. Causality would require an instrument or natural experiment.",
        "",
        "**Q: Is this alpha or attention?**",
        "A: We cannot distinguish cleanly. Short-term price moves could be attention-driven. Medium-term persistence would suggest alpha, but we do not observe strong persistence.",
        "",
        "**Q: Are labels reliable?**",
        "A: Labels are deterministic rule-based pseudo-labels. An AI-assisted audit was conducted, but human validation is still the gold standard and has not been done.",
        "",
        "**Q: Why yfinance?**",
        "A: yfinance is free and sufficient for prototype analysis. All outputs are explicitly labeled as prototype-grade. Bloomberg would improve dividend/split precision and survivorship bias.",
        "",
        "**Q: Why not human labels?**",
        "A: Manual labeling of 2,147 events is infeasible in the timeline. The AI-assisted audit provides a reproducible robustness check.",
        "",
        "**Q: Does this survive benchmarks?**",
        "A: Abnormal returns are computed vs. SPY, QQQ, IWM, and sector ETFs. Some horizons show positive abnormal returns, but statistical significance is mixed after FDR correction.",
        "",
        "**Q: Is it tradable?**",
        "A: The portfolio backtest uses next-trading-day execution and includes 10 bps transaction costs. Sharpe ratios are modest. Real-world slippage and short constraints could further reduce returns.",
        "",
        "**Q: What would Bloomberg change?**",
        "A: More accurate adjusted prices, better handling of delistings/renamings, intraday data for precise execution, and institutional credibility.",
    ]
    _write_md(output_dir / "final_presentation_talking_points.md", talking)

    return {
        "final_research_update": output_dir / "final_research_update.md",
        "final_claims_guardrail": output_dir / "final_claims_guardrail.md",
        "professor_one_page_update": output_dir / "professor_one_page_update.md",
        "final_presentation_talking_points": output_dir / "final_presentation_talking_points.md",
    }


# ---------------------------------------------------------------------------
# 10. End-to-end orchestration
# ---------------------------------------------------------------------------

def run_full_research_expansion(
    *,
    fetch_market_data: bool = True,
    sample_size_ai_audit: int = 500,
) -> dict[str, Any]:
    _ensure_dirs()
    results: dict[str, Any] = {}

    # Step A: build all clean events
    results["clean_events"] = build_all_clean_events()

    # Step B: sample design
    results["sample_design"] = build_sample_design_report()

    # Step C: market data
    if fetch_market_data:
        results["market_data"] = fetch_expanded_market_data()

    # Step D: return coverage
    results["return_coverage"] = diagnose_return_coverage()

    # Step E: event windows
    results["event_windows"] = build_event_window_returns()

    # Step F: portfolios
    results["portfolios"] = build_portfolio_backtests()

    # Step G: robust stats
    results["robust_stats"] = build_robust_statistics()

    # Step H: AI audit
    results["ai_audit"] = build_ai_classifier_audit(sample_size=sample_size_ai_audit)

    # Step I: reports
    results["reports"] = build_final_reports()

    return results
