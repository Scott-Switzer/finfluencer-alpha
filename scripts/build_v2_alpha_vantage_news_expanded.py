"""Expanded Alpha Vantage NEWS_SENTIMENT layer for full event universe.

Runs on RunPod with key in /root/.config/fin496/alphavantage.env (never logged).
Stores compact metadata only; windows use YYYYMMDDTHHMM bounds; panel uses ±5/±21/±63
calendar-day slices. Prioritizes non-top tickers, then unknown SEC/GDELT confounds, then top-5.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402
from build_v2_alpha_vantage_news_layer import (  # noqa: E402
    classify_text,
    load_key,
    trunc,
)

OUT_DIR = utils.OUT_DIR / "news_alpha_vantage_expanded"
LEGACY_META = utils.OUT_DIR / "news_alpha_vantage" / "03_av_compact_article_metadata.csv"
LEGACY_PLAN = utils.OUT_DIR / "news_alpha_vantage" / "02_av_ticker_query_plan.csv"
API_URL = "https://www.alphavantage.co/query"
OK_STATUSES = {"ok", "resume_cached_ok", "resume_cached_legacy"}
# Calendar-day windows aligned to 5D / 21D / 63D interpretation for news density.
WINDOW_CAL_DAYS = [5, 21, 63]
FLAG_COLUMNS = [
    "earnings_news_flag",
    "analyst_news_flag",
    "product_news_flag",
    "legal_regulatory_news_flag",
    "macro_sector_news_flag",
]
CACHE_ARTICLES = "av_expanded_article_metadata_cache.csv"
CACHE_PLAN = "av_expanded_query_plan_progress.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpha Vantage NEWS_SENTIMENT expanded universe.")
    parser.add_argument("--max-requests", type=int, default=24)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=12.5)
    parser.add_argument(
        "--query-mode",
        choices=["ticker_chunk", "per_event"],
        default="ticker_chunk",
        help="ticker_chunk: one query per ticker-year (fits AV daily limits); per_event: one query per event.",
    )
    parser.add_argument(
        "--no-import-legacy-metadata",
        dest="import_legacy_metadata",
        action="store_false",
        help="Do not seed article metadata from prior news_alpha_vantage bulk layer.",
    )
    parser.set_defaults(import_legacy_metadata=True)
    parser.add_argument(
        "--query-span-days",
        type=int,
        default=63,
        help="Half-width in calendar days for per_event API queries (time_from/time_to).",
    )
    return parser.parse_args()


def sanitize_provider_error(msg: str) -> str:
    """Strip provider messages that may echo API keys."""
    text = trunc(msg, 200)
    text = re.sub(
        r"detected your API key as [A-Z0-9]+",
        "detected your API key as [REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"apikey=[A-Za-z0-9]+", "apikey=[REDACTED]", text, flags=re.IGNORECASE)
    return text


def event_time_bounds(event_date, span: int) -> tuple[str, str]:
    """Return (time_from, time_to) in YYYYMMDDTHHMM format (start of day / end of day)."""
    start = event_date - timedelta(days=span)
    end = event_date + timedelta(days=span)
    return start.strftime("%Y%m%dT0000"), end.strftime("%Y%m%dT2359")


def load_unknown_priority_map(events: pd.DataFrame) -> pd.Series:
    """True if event should be prioritized after non-top (SEC or GDELT unknown)."""
    sec_unknown = pd.Series(False, index=events.index)
    gd_unknown = pd.Series(False, index=events.index)
    sec_path = utils.OUT_DIR / "sec_earnings_confounds" / "01_sec_event_flags_expanded.csv"
    if sec_path.exists():
        sec = pd.read_csv(sec_path)
        if "event_id" in sec.columns and "sec_unknown_flag" in sec.columns:
            sm = sec.set_index("event_id")["sec_unknown_flag"].astype(str).str.lower().eq("true")
            sec_unknown = events["event_id"].map(lambda e: bool(sm.get(int(e), False)))
    gd_path = utils.OUT_DIR / "news_gdelt_retry" / "02_gdelt_probe_flags.csv"
    if gd_path.exists():
        gd = pd.read_csv(gd_path)
        if "event_id" in gd.columns and "gdelt_news_unknown_flag" in gd.columns:
            gm = gd.set_index("event_id")["gdelt_news_unknown_flag"].astype(str).str.lower().eq("true")
            gd_unknown = events["event_id"].map(lambda e: bool(gm.get(int(e), False)))
    return sec_unknown | gd_unknown


def build_prioritized_plan(events: pd.DataFrame, span: int) -> list[dict[str, Any]]:
    ev = events.copy()
    ev["event_date_dt"] = pd.to_datetime(ev["event_date"], errors="coerce")
    ev = ev.dropna(subset=["event_date_dt"])
    prio = load_unknown_priority_map(ev)
    ev["_unknown_hint"] = prio.reindex(ev.index, fill_value=False).astype(bool)
    ev["_top5"] = ev["ticker"].astype(str).isin({t.upper() for t in utils.TOP5})
    ev = ev.sort_values(by=["_top5", "_unknown_hint"], ascending=[True, False]).reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    for _, row in ev.iterrows():
        ed = row["event_date_dt"].date()
        t_from, t_to = event_time_bounds(ed, span)
        rows.append(
            {
                "query_key": f"evt_{int(row.event_id)}_{row.ticker}",
                "event_id": int(row.event_id),
                "ticker": str(row.ticker),
                "time_from": t_from,
                "time_to": t_to,
                "query_status": "planned",
                "priority_non_top_first": not bool(row["_top5"]),
                "priority_unknown_confound_hint": bool(row["_unknown_hint"]),
            }
        )
    return rows


def build_prioritized_ticker_plan(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Ticker-year chunks; non-top tickers first to maximize defensible non-top news coverage."""
    ev = events.copy()
    ev["event_date_dt"] = pd.to_datetime(ev["event_date"], errors="coerce")
    ev = ev.dropna(subset=["event_date_dt"])
    prio = load_unknown_priority_map(ev)
    ev["_unknown_hint"] = prio.reindex(ev.index, fill_value=False).astype(bool)
    ev["_top5"] = ev["ticker"].astype(str).isin({t.upper() for t in utils.TOP5})
    ticker_order = (
        ev.groupby("ticker", as_index=False)
        .agg(_top5=("_top5", "max"), _unknown_hint=("_unknown_hint", "max"), n_events=("event_id", "count"))
        .sort_values(by=["_top5", "_unknown_hint"], ascending=[True, False])
    )
    rows: list[dict[str, Any]] = []
    for _, trow in ticker_order.iterrows():
        ticker = str(trow["ticker"])
        group = ev[ev["ticker"].astype(str).eq(ticker)]
        dates = group["event_date_dt"]
        start = dates.min().date()
        end = dates.max().date()
        for year in range(start.year, end.year + 1):
            chunk_start = max(start, pd.Timestamp(year=year, month=1, day=1).date())
            chunk_end = min(end, pd.Timestamp(year=year, month=12, day=31).date())
            rows.append(
                {
                    "query_key": f"{ticker}_{chunk_start}_{chunk_end}",
                    "event_id": "",
                    "ticker": ticker,
                    "time_from": chunk_start.strftime("%Y%m%dT0000"),
                    "time_to": chunk_end.strftime("%Y%m%dT2359"),
                    "query_status": "planned",
                    "priority_non_top_first": not bool(trow["_top5"]),
                    "priority_unknown_confound_hint": bool(trow["_unknown_hint"]),
                    "event_count": int(trow["n_events"]),
                }
            )
    return rows


def legacy_ok_tickers() -> set[str]:
    if not LEGACY_PLAN.exists():
        return set()
    plan = pd.read_csv(LEGACY_PLAN)
    if "query_status" not in plan.columns or "ticker" not in plan.columns:
        return set()
    ok = plan["query_status"].astype(str).isin(["ok", "resume_cached_compact_metadata"])
    return set(plan.loc[ok, "ticker"].astype(str))


def load_legacy_metadata() -> pd.DataFrame:
    if not LEGACY_META.exists():
        return pd.DataFrame()
    meta = pd.read_csv(LEGACY_META)
    if "event_id" not in meta.columns:
        meta["event_id"] = ""
    return meta


def request_news_safe(
    api_key: str, row: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], str]:
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": row["ticker"],
        "time_from": row["time_from"],
        "time_to": row["time_to"],
        "sort": "EARLIEST",
        "limit": "1000",
        "apikey": api_key,
    }
    try:
        response = requests.get(API_URL, params=params, timeout=45)
    except Exception as exc:
        return "request_failed", [], trunc(type(exc).__name__)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"http_{response.status_code}_json_parse_failed", [], trunc(response.text)
    if "Information" in payload or "Note" in payload:
        return "rate_limited", [], sanitize_provider_error(str(payload.get("Information") or payload.get("Note")))
    if "Error Message" in payload:
        return "provider_error", [], sanitize_provider_error(str(payload.get("Error Message")))
    articles: list[dict[str, Any]] = []
    for idx, item in enumerate(payload.get("feed", []) or []):
        title = trunc(item.get("title"), 180)
        summary = trunc(item.get("summary"), 220)
        flags = classify_text(title, summary)
        relevance = ""
        sentiment = ""
        for ticker_sentiment in item.get("ticker_sentiment", []) or []:
            if str(ticker_sentiment.get("ticker", "")).upper() == str(row["ticker"]).upper():
                relevance = ticker_sentiment.get("relevance_score", "")
                sentiment = ticker_sentiment.get("ticker_sentiment_score", "")
                break
        url = item.get("url", "")
        articles.append(
            {
                "query_key": row["query_key"],
                "event_id": row["event_id"],
                "ticker": row["ticker"],
                "article_key": utils.safe_hash(row["query_key"], idx, url, title),
                "time_published": item.get("time_published", ""),
                "source_domain": urlparse(str(url)).netloc.replace("www.", ""),
                "title_truncated": title,
                "overall_sentiment_score": item.get("overall_sentiment_score", ""),
                "ticker_relevance_score": relevance,
                "ticker_sentiment_score": sentiment,
                **flags,
            }
        )
    return "ok", articles, ""


def map_events_to_panel(
    events: pd.DataFrame, metadata: pd.DataFrame, plan: pd.DataFrame, *, ticker_chunk_mode: bool
) -> pd.DataFrame:
    ok_status = plan["query_status"].astype(str).isin(OK_STATUSES)
    ok_keys = set(plan.loc[ok_status, "query_key"].astype(str))
    ok_tickers = set(plan.loc[ok_status, "ticker"].astype(str))
    if not metadata.empty:
        meta = metadata.copy()
        meta["published_date"] = pd.to_datetime(
            meta["time_published"].astype(str).str[:8], format="%Y%m%d", errors="coerce"
        ).dt.date
    else:
        meta = pd.DataFrame()
    rows = []
    for _, event in events.iterrows():
        eid = int(event.event_id)
        ticker = str(event.ticker)
        qkey = f"evt_{eid}_{ticker}"
        event_date = pd.to_datetime(event.event_date, errors="coerce").date()
        if ticker_chunk_mode:
            success = ticker in ok_tickers
        else:
            success = qkey in ok_keys
        if not meta.empty:
            by_ticker = meta[meta["ticker"].astype(str).eq(ticker)]
            if "event_id" in meta.columns and meta["event_id"].notna().any():
                per_event = by_ticker[by_ticker["event_id"].astype(str).isin([str(eid), ""])]
                t_rows = per_event if not per_event.empty else by_ticker
            else:
                t_rows = by_ticker
        else:
            t_rows = pd.DataFrame()
        base = {
            "event_id": eid,
            "ticker": ticker,
            "company_name": event.get("company_name", ""),
            "event_date": event.event_date,
            "av_expanded_query_success": success,
        }
        for days in WINDOW_CAL_DAYS:
            if success and not t_rows.empty and event_date is not None:
                start = event_date - timedelta(days=days)
                end = event_date + timedelta(days=days)
                subset = t_rows[t_rows["published_date"].between(start, end)]
            else:
                subset = pd.DataFrame()
            count = len(subset)
            base[f"window_pm{days}_article_count"] = count
            base[f"window_pm{days}_top_source_domains"] = ";".join(
                d for d, _ in Counter(subset.get("source_domain", pd.Series(dtype=str))).most_common(5)
            )
            for flag in FLAG_COLUMNS:
                col = flag
                if count and col in subset.columns:
                    ser = subset[col]
                    truthy = ser.astype(str).str.lower().isin(["true", "1"]).any()
                    truthy = truthy or (ser.dtype == bool and bool(ser.any()))
                    base[f"window_pm{days}_{col}"] = bool(truthy)
                else:
                    base[f"window_pm{days}_{col}"] = False
            major = count >= 3 or any(base[f"window_pm{days}_{f}"] for f in FLAG_COLUMNS)
            base[f"window_pm{days}_major_news_flag"] = major
        confounded = any(base[f"window_pm{d}_major_news_flag"] for d in WINDOW_CAL_DAYS)
        base["av_expanded_news_confounded_flag"] = confounded
        base["av_expanded_news_clean_flag"] = success and not confounded
        base["av_expanded_news_unknown_flag"] = not success
        if not success:
            base["reason_codes"] = "provider_not_successfully_queried_for_event"
        elif confounded:
            base["reason_codes"] = "real_news_overlap_detected"
        else:
            base["reason_codes"] = "provider_queried_no_major_news_threshold"
        rows.append(base)
    return pd.DataFrame(rows)


def safe_log_row(row: dict[str, Any], status: str, n_art: int, err: str) -> dict[str, Any]:
    return {
        "provider": "Alpha_Vantage_NEWS_SENTIMENT",
        "query_key": row["query_key"],
        "event_id": row["event_id"],
        "ticker": row["ticker"],
        "time_from": row["time_from"],
        "time_to": row["time_to"],
        "status": status,
        "article_rows_returned": n_art,
        "error_message_truncated": err,
    }


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = utils.event_manifest()
    key = load_key()
    ticker_chunk_mode = args.query_mode == "ticker_chunk"
    plan_rows = (
        build_prioritized_ticker_plan(events)
        if ticker_chunk_mode
        else build_prioritized_plan(events, args.query_span_days)
    )
    plan_path = OUT_DIR / CACHE_PLAN
    art_path = OUT_DIR / CACHE_ARTICLES

    if args.resume and plan_path.exists():
        old_plan = pd.read_csv(plan_path)
        if ticker_chunk_mode and "event_count" not in old_plan.columns:
            pass
        else:
            status_map = dict(
                zip(old_plan["query_key"].astype(str), old_plan["query_status"].astype(str), strict=False)
            )
            for r in plan_rows:
                prev = status_map.get(r["query_key"], "")
                if prev in OK_STATUSES:
                    r["query_status"] = "resume_cached_ok"

    legacy_tickers = legacy_ok_tickers() if args.import_legacy_metadata else set()
    if legacy_tickers:
        for r in plan_rows:
            if str(r["ticker"]) in legacy_tickers:
                r["query_status"] = "resume_cached_legacy"

    metadata = load_legacy_metadata() if args.import_legacy_metadata else pd.DataFrame()
    if art_path.exists():
        cached = pd.read_csv(art_path)
        metadata = pd.concat([metadata, cached], ignore_index=True) if not metadata.empty else cached
    articles: list[dict[str, Any]] = metadata.to_dict("records") if not metadata.empty else []
    safe_logs: list[dict[str, Any]] = []
    attempted = 0
    updated_plan = list(plan_rows)

    if key is None:
        for r in updated_plan:
            r["query_status"] = "missing_runtime_key"
        safe_logs.append(
            {
                "provider": "Alpha_Vantage_NEWS_SENTIMENT",
                "query_key": "runtime_key_status",
                "event_id": "",
                "ticker": "",
                "time_from": "",
                "time_to": "",
                "status": "missing_runtime_key",
                "article_rows_returned": 0,
                "error_message_truncated": "",
            }
        )
    elif args.dry_run:
        for r in updated_plan:
            r["query_status"] = "dry_run"
        if updated_plan:
            safe_logs.append(safe_log_row(updated_plan[0], "dry_run", 0, ""))
    else:
        for i, r in enumerate(updated_plan):
            if r["query_status"] in OK_STATUSES:
                continue
            if attempted >= args.max_requests:
                r["query_status"] = "not_queried_budget_exhausted"
                continue
            row_api = dict(r)
            status, new_articles, err = request_news_safe(key, row_api)
            attempted += 1
            r["query_status"] = "ok" if status == "ok" else status
            r["article_rows_returned"] = len(new_articles)
            r["error_message_truncated"] = sanitize_provider_error(err)
            articles.extend(new_articles)
            safe_logs.append(safe_log_row(r, status, len(new_articles), sanitize_provider_error(err)))
            if status == "rate_limited":
                break
            time.sleep(args.sleep_seconds)
            if (i + 1) % 25 == 0:
                adf = pd.DataFrame(articles)
                if "article_key" in adf.columns:
                    adf = adf.drop_duplicates(subset=["article_key"])
                adf.to_csv(art_path, index=False)
                pd.DataFrame(updated_plan).to_csv(plan_path, index=False)

    plan_df = pd.DataFrame(updated_plan)
    meta_df = pd.DataFrame(articles) if articles else pd.DataFrame()
    if not meta_df.empty and "article_key" in meta_df.columns:
        meta_df = meta_df.drop_duplicates(subset=["article_key"])
    plan_df.to_csv(plan_path, index=False)
    if not meta_df.empty:
        meta_df.to_csv(art_path, index=False)

    panel = map_events_to_panel(events, meta_df, plan_df, ticker_chunk_mode=ticker_chunk_mode)
    utils.write_csv(
        OUT_DIR / "av_expanded_event_news_panel.csv",
        panel.to_dict("records"),
        list(panel.columns),
    )

    cov = (
        plan_df.groupby("ticker")
        .agg(
            n_planned=("query_key", "count"),
            n_ok=("query_status", lambda s: int(s.isin(list(OK_STATUSES)).sum())),
            n_failed=(
                "query_status",
                lambda s: int((~s.isin(list(OK_STATUSES) + ["planned", "not_queried_budget_exhausted"])).sum()),
            ),
        )
        .reset_index()
    )
    utils.write_csv(OUT_DIR / "av_expanded_ticker_coverage.csv", cov.to_dict("records"), list(cov.columns))

    utils.write_csv(OUT_DIR / "av_expanded_request_log_safe.csv", safe_logs, list(safe_logs[0]) if safe_logs else ["provider", "status"])

    clean = int(panel["av_expanded_news_clean_flag"].sum())
    confounded = int(panel["av_expanded_news_confounded_flag"].sum())
    unknown = int(panel["av_expanded_news_unknown_flag"].sum())
    ok_queries = int(plan_df["query_status"].isin(list(OK_STATUSES)).sum())
    tickers_ok = int(plan_df.loc[plan_df["query_status"].isin(list(OK_STATUSES)), "ticker"].nunique())
    rate_limited = int((plan_df["query_status"] == "rate_limited").sum())
    summary_md = f"""# Alpha Vantage expanded NEWS_SENTIMENT summary

- Events: {len(panel)}
- Query mode: `{args.query_mode}`
- Plan rows OK (or resumed/legacy): {ok_queries}
- Tickers with successful coverage: {tickers_ok}
- Requests attempted this run: {attempted}
- Rate-limited plan rows: {rate_limited}
- Clean / confounded / unknown (unknown is **not** clean): {clean} / {confounded} / {unknown}
- Window calendar days: {WINDOW_CAL_DAYS}
- Time bounds format: `YYYYMMDDTHHMM` (see `time_from` / `time_to` in request log).
- Legacy bulk metadata imported: {args.import_legacy_metadata}
- No API keys or raw article bodies are written to exports; only truncated titles and counts.

**Interpretation:** Partial public-news control. Unknown coverage must not be coded as clean.
Standard AV free tier is ~25 requests/day; ticker_chunk mode prioritizes non-top names within that budget.
"""
    utils.write_md(OUT_DIR / "av_expanded_summary.md", "AV Expanded Summary", summary_md)
    print(
        f"AV expanded complete: attempted={attempted} ok_queries={ok_queries} tickers_ok={tickers_ok} "
        f"clean={clean} confounded={confounded} unknown={unknown}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
