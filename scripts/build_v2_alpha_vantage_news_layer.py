from __future__ import annotations

import argparse
import json
import os
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

OUT_DIR = utils.OUT_DIR / "news_alpha_vantage"
RUNTIME_ENV = Path("/root/.config/fin496/alphavantage.env")
API_URL = "https://www.alphavantage.co/query"
WINDOWS = [1, 3, 5, 10]
FLAG_COLUMNS = [
    "earnings_news_flag",
    "analyst_news_flag",
    "product_news_flag",
    "legal_regulatory_news_flag",
    "macro_sector_news_flag",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-requests", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--target-mode",
        choices=["probe", "ticker_bulk", "event_windows", "all_available"],
        default="probe",
    )
    parser.add_argument("--sleep-seconds", type=float, default=12.5)
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--lookahead-days", type=int, default=5)
    parser.add_argument("--year-chunking", action="store_true", default=True)
    parser.add_argument("--priority-sample-size", type=int, default=80)
    return parser.parse_args()


def load_key() -> str | None:
    value = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    if value:
        return value
    if not RUNTIME_ENV.exists():
        return None
    for line in RUNTIME_ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("ALPHAVANTAGE_API_KEY="):
            value = line.split("=", 1)[1].strip()
            if value:
                os.environ["ALPHAVANTAGE_API_KEY"] = value
                return value
    return None


def trunc(value: Any, limit: int = 160) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ")[:limit]


def classify_text(title: str, summary: str = "") -> dict[str, bool]:
    text = f"{title} {summary}".lower()
    return {
        "earnings_news_flag": any(x in text for x in ["earnings", "revenue", "eps", "quarter"]),
        "analyst_news_flag": any(x in text for x in ["analyst", "upgrade", "downgrade", "price target"]),
        "product_news_flag": any(x in text for x in ["launch", "product", "chip", "ai", "ev", "iphone"]),
        "legal_regulatory_news_flag": any(
            x in text for x in ["sec", "lawsuit", "probe", "investigation", "regulator", "ftc"]
        ),
        "macro_sector_news_flag": any(x in text for x in ["fed", "inflation", "rates", "nasdaq"]),
    }


def load_events() -> pd.DataFrame:
    events = utils.event_manifest()
    events["event_date_dt"] = pd.to_datetime(events["event_date"], errors="coerce")
    return events


def ticker_plan(events: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker, group in events.groupby("ticker"):
        dates = group["event_date_dt"].dropna()
        if dates.empty:
            continue
        start = dates.min().date()
        end = dates.max().date()
        for year in range(start.year, end.year + 1):
            chunk_start = max(start, pd.Timestamp(year=year, month=1, day=1).date())
            chunk_end = min(end, pd.Timestamp(year=year, month=12, day=31).date())
            rows.append(
                {
                    "query_key": f"{ticker}_{chunk_start}_{chunk_end}",
                    "ticker": ticker,
                    "time_from": chunk_start.strftime("%Y%m%dT0000"),
                    "time_to": chunk_end.strftime("%Y%m%dT2359"),
                    "event_count": int(len(group)),
                    "query_status": "planned",
                }
            )
    return rows


def probe_plan(events: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    priority = []
    for ticker in ["NVDA", "TSLA", "AAPL"]:
        group = events[events["ticker"] == ticker]
        if not group.empty:
            priority.append(group.iloc[0])
    non_top = events[~events["ticker"].isin(utils.TOP5)]
    if not non_top.empty:
        priority.append(non_top.iloc[0])
    sample = events.sample(min(limit, len(events)), random_state=496)
    priority.extend(row for _, row in sample.iterrows())
    rows = []
    seen = set()
    for row in priority:
        if len(rows) >= limit:
            break
        key = f"event_{int(row.event_id)}_{row.ticker}"
        if key in seen or pd.isna(row.event_date_dt):
            continue
        seen.add(key)
        event_date = row.event_date_dt.date()
        rows.append(
            {
                "query_key": key,
                "ticker": row.ticker,
                "time_from": (event_date - timedelta(days=5)).strftime("%Y%m%dT0000"),
                "time_to": (event_date + timedelta(days=5)).strftime("%Y%m%dT2359"),
                "event_count": 1,
                "query_status": "planned",
            }
        )
    return rows


def request_news(key: str, row: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": row["ticker"],
        "time_from": row["time_from"],
        "time_to": row["time_to"],
        "sort": "EARLIEST",
        "limit": "1000",
        "apikey": key,
    }
    try:
        response = requests.get(API_URL, params=params, timeout=30)
    except Exception as exc:
        return "request_failed", [], trunc(type(exc).__name__)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"http_{response.status_code}_json_parse_failed", [], trunc(response.text)
    if "Information" in payload or "Note" in payload:
        return "rate_limited", [], trunc(payload.get("Information") or payload.get("Note"))
    if "Error Message" in payload:
        return "provider_error", [], trunc(payload.get("Error Message"))
    articles = []
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
                "ticker": row["ticker"],
                "article_key": utils.safe_hash(row["query_key"], idx, url, title),
                "time_published": item.get("time_published", ""),
                "source_domain": urlparse(url).netloc.replace("www.", ""),
                "title_truncated": title,
                "overall_sentiment_score": item.get("overall_sentiment_score", ""),
                "ticker_relevance_score": relevance,
                "ticker_sentiment_score": sentiment,
                **flags,
            }
        )
    return "ok", articles, ""


def existing_metadata() -> pd.DataFrame:
    path = OUT_DIR / "03_av_compact_article_metadata.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def map_events(events: pd.DataFrame, metadata: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    success_tickers = set(plan.loc[plan["query_status"].eq("ok"), "ticker"].astype(str))
    if not metadata.empty:
        metadata = metadata.copy()
        metadata["published_date"] = pd.to_datetime(
            metadata["time_published"].astype(str).str[:8], format="%Y%m%d", errors="coerce"
        ).dt.date
    rows = []
    for _, event in events.iterrows():
        event_date = pd.to_datetime(event.event_date).date()
        ticker_articles = metadata[metadata["ticker"].astype(str).eq(str(event.ticker))] if not metadata.empty else pd.DataFrame()
        provider_success = str(event.ticker) in success_tickers
        row = {
            "event_id": int(event.event_id),
            "ticker": event.ticker,
            "company_name": event.company_name,
            "event_date": event.event_date,
            "av_query_success": provider_success,
        }
        for days in WINDOWS:
            if provider_success and not ticker_articles.empty:
                start = event_date - timedelta(days=days)
                end = event_date + timedelta(days=days)
                subset = ticker_articles[
                    ticker_articles["published_date"].between(start, end)
                ]
            else:
                subset = pd.DataFrame()
            count = len(subset)
            row[f"window_pm{days}_article_count"] = count
            row[f"window_pm{days}_top_source_domains"] = ";".join(
                domain for domain, _ in Counter(subset.get("source_domain", pd.Series(dtype=str))).most_common(5)
            )
            for flag in FLAG_COLUMNS:
                row[f"window_pm{days}_{flag}"] = bool(
                    count and flag in subset.columns and subset[flag].astype(str).str.lower().eq("true").any()
                )
            major = count >= 3 or any(row[f"window_pm{days}_{flag}"] for flag in FLAG_COLUMNS)
            row[f"window_pm{days}_major_news_flag"] = major
        confounded = any(row[f"window_pm{days}_major_news_flag"] for days in WINDOWS)
        row["av_news_confounded_flag"] = confounded
        row["av_news_clean_flag"] = provider_success and not confounded
        row["av_news_unknown_flag"] = not provider_success
        row["reason_codes"] = (
            "provider_not_successfully_queried_for_ticker"
            if not provider_success
            else "real_news_overlap_detected"
            if confounded
            else "provider_queried_no_major_news_threshold"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def event_study(flags: pd.DataFrame, name: str, mask: pd.Series) -> list[dict[str, Any]]:
    panel = utils.forward_panel(["5D", "21D", "63D", "126D"])
    merged = panel.merge(flags[["event_id"] + [c for c in flags.columns if c.startswith("av_news_")]], on="event_id", how="left")
    selected = merged[mask.reindex(merged.index, fill_value=False)] if len(mask) == len(merged) else merged[mask]
    return utils.summarize_return_panel(selected, "spy_bhar", {name: pd.Series(True, index=selected.index)}, ["5D", "21D", "63D", "126D"])


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = load_events()
    key = load_key()
    plan_rows = probe_plan(events, min(max(args.max_requests, 3), args.priority_sample_size)) if args.target_mode == "probe" else ticker_plan(events)
    plan = pd.DataFrame(plan_rows)
    metadata = existing_metadata()
    old_keys = set(metadata.get("query_key", pd.Series(dtype=str)).astype(str))
    articles = metadata.to_dict("records") if not metadata.empty else []
    diagnostics = []
    attempted = 0
    if key is None:
        plan["query_status"] = "missing_runtime_key"
    elif args.dry_run:
        plan["query_status"] = "dry_run"
    else:
        updated = []
        for row in plan.to_dict("records"):
            if args.resume and row["query_key"] in old_keys:
                row["query_status"] = "resume_cached_compact_metadata"
                updated.append(row)
                continue
            if attempted >= args.max_requests:
                row["query_status"] = "not_queried_budget_exhausted"
                updated.append(row)
                continue
            status, new_articles, error = request_news(key, row)
            attempted += 1
            row["query_status"] = status
            row["article_rows_returned"] = len(new_articles)
            row["error_message_truncated"] = error
            articles.extend(new_articles)
            diagnostics.append(
                {
                    "provider": "Alpha_Vantage_NEWS_SENTIMENT",
                    "query_key": row["query_key"],
                    "ticker": row["ticker"],
                    "status": status,
                    "article_rows_returned": len(new_articles),
                    "error_message_truncated": error,
                }
            )
            updated.append(row)
            if status == "rate_limited":
                break
            time.sleep(args.sleep_seconds)
        plan = pd.DataFrame(updated + plan.to_dict("records")[len(updated):])
    if not diagnostics:
        diagnostics = [
            {
                "provider": "Alpha_Vantage_NEWS_SENTIMENT",
                "query_key": "runtime_key_status",
                "ticker": "",
                "status": "key_present" if key else "missing_runtime_key",
                "article_rows_returned": 0,
                "error_message_truncated": "",
            }
        ]
    metadata = pd.DataFrame(articles).drop_duplicates("article_key") if articles else pd.DataFrame()
    if metadata.empty:
        metadata = pd.DataFrame(columns=["query_key", "ticker", "article_key", "time_published", "source_domain", "title_truncated"] + FLAG_COLUMNS)
    flags = map_events(events, metadata, plan)
    utils.write_csv(OUT_DIR / "01_av_provider_diagnostics.csv", diagnostics)
    utils.write_md(OUT_DIR / "01_av_provider_diagnostics.md", "Alpha Vantage Provider Diagnostics", utils.md_table(diagnostics))
    utils.write_csv(OUT_DIR / "02_av_ticker_query_plan.csv", plan.to_dict("records"), list(plan.columns))
    utils.write_csv(OUT_DIR / "03_av_compact_article_metadata.csv", metadata.to_dict("records"), list(metadata.columns))
    utils.write_csv(OUT_DIR / "04_av_event_window_flags.csv", flags.to_dict("records"), list(flags.columns))
    clean = int(flags["av_news_clean_flag"].sum())
    confounded = int(flags["av_news_confounded_flag"].sum())
    unknown = int(flags["av_news_unknown_flag"].sum())
    success = int(plan["query_status"].eq("ok").sum()) if "query_status" in plan else 0
    summary = [
        {
            "provider": "Alpha_Vantage_NEWS_SENTIMENT",
            "target_mode": args.target_mode,
            "requests_attempted": attempted,
            "successful_requests": success,
            "article_metadata_rows": len(metadata),
            "tickers_covered": plan.loc[plan["query_status"].eq("ok"), "ticker"].nunique() if "query_status" in plan else 0,
            "events_mapped": len(flags),
            "clean_events": clean,
            "confounded_events": confounded,
            "unknown_events": unknown,
            "status": "usable_partial" if clean + confounded > 0 else "diagnostic_only_or_missing",
        }
    ]
    utils.table_pair(OUT_DIR / "05_av_news_coverage_summary", summary, "Alpha Vantage News Coverage")
    panel = utils.forward_panel(["5D", "21D", "63D", "126D"])
    merged = panel.merge(flags[["event_id", "av_news_clean_flag", "av_news_confounded_flag", "av_news_unknown_flag"]], on="event_id", how="left")
    studies = {
        "06_av_news_clean_event_study": merged[merged["av_news_clean_flag"].astype(str).str.lower().eq("true")],
        "07_av_news_confounded_event_study": merged[merged["av_news_confounded_flag"].astype(str).str.lower().eq("true")],
        "08_av_news_unknown_event_study": merged[merged["av_news_unknown_flag"].astype(str).str.lower().eq("true")],
    }
    for file_name, selected in studies.items():
        rows = utils.summarize_return_panel(
            selected,
            "spy_bhar",
            {file_name.replace("_event_study", ""): pd.Series(True, index=selected.index)},
            ["5D", "21D", "63D", "126D"],
        )
        utils.table_pair(OUT_DIR / file_name, rows, file_name.replace("_", " ").title())
    utils.write_md(
        OUT_DIR / "README.md",
        "Alpha Vantage News Layer",
        "Compact Alpha Vantage NEWS_SENTIMENT metadata only. No raw JSON, article bodies, summaries, or API keys are stored. Clean requires a successful provider query and no major-news threshold. Unknown is never clean.",
    )
    utils.write_md(
        OUT_DIR / "09_av_news_layer_interpretation.md",
        "Alpha Vantage Interpretation",
        f"Requests attempted: {attempted}. Successful requests: {success}. Clean/confounded/unknown events: {clean}/{confounded}/{unknown}. This layer is full-sample evidence only if provider coverage is broad; otherwise it is diagnostic.",
    )
    print(f"Alpha Vantage news layer complete: requests={attempted} success={success} clean={clean} confounded={confounded} unknown={unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
