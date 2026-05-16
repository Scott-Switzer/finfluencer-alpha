from __future__ import annotations

import os
import random
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
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
NEWS_DIR = OUT_DIR / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)
RNG = random.Random(496)


def truncate(text: Any, limit: int = 200) -> str:
    return str(text or "").replace("\n", " ").replace("\r", " ")[:limit]


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:100], columns)
    )


def query_terms(event: base.EventRecord, mode: str) -> str:
    company = (event.company_name or "").strip()[:60]
    ticker = event.ticker
    if mode == "ticker":
        return ticker
    if mode == "company_phrase" and company:
        return f'"{company}"'
    if mode == "ticker_company" and company:
        return f'{ticker} OR "{company}"'
    if mode == "company_stock" and company:
        return f'"{company}" stock'
    if mode == "company_earnings" and company:
        return f'"{company}" earnings'
    if mode == "company_analyst" and company:
        return f'"{company}" analyst'
    if mode == "company_sec" and company:
        return f'"{company}" SEC'
    keyword = {
        "NVDA": "chip OR AI",
        "AMD": "chip OR AI",
        "TSLA": "EV OR vehicle",
        "AAPL": "iPhone OR product",
        "AMZN": "AWS OR cloud",
        "GOOGL": "AI OR search",
        "MSFT": "AI OR cloud",
    }.get(ticker, "stock")
    return f"{ticker} {keyword}"


def classify_titles(titles: list[str]) -> dict[str, bool]:
    joined = " ".join(titles).lower()
    return {
        "earnings_news_flag": any(x in joined for x in ["earnings", "quarter", "revenue", "eps"]),
        "analyst_news_flag": any(
            x in joined for x in ["analyst", "upgrade", "downgrade", "price target"]
        ),
        "product_news_flag": any(
            x in joined for x in ["launch", "product", "chip", "ai", "ev", "iphone"]
        ),
        "legal_regulatory_news_flag": any(
            x in joined for x in ["sec", "lawsuit", "probe", "investigation", "regulator"]
        ),
        "macro_sector_news_flag": any(
            x in joined for x in ["fed", "rates", "inflation", "sector", "nasdaq"]
        ),
    }


def parse_articles(payload: dict[str, Any]) -> tuple[int, str, str, str, str, dict[str, bool]]:
    articles = payload.get("articles", []) or []
    domains = []
    titles = []
    dates = []
    for article in articles[:10]:
        url = article.get("url") or ""
        domain = urlparse(url).netloc.replace("www.", "")
        if domain:
            domains.append(domain)
        title = truncate(article.get("title"), 90)
        if title:
            titles.append(title)
        seen = article.get("seendate") or article.get("datetime")
        if seen:
            dates.append(str(seen))
    flags = classify_titles(titles)
    return (
        len(articles),
        ";".join(domain for domain, _count in Counter(domains).most_common(5)),
        " || ".join(titles[:3]),
        min(dates) if dates else "",
        max(dates) if dates else "",
        flags,
    )


def gdelt_request(event: base.EventRecord, mode: str, window_days: int) -> dict[str, Any]:
    if event.event_date is None:
        return {"query_status": "missing_event_date", "provider_error_class": "missing_event_date"}
    start = (event.event_date - timedelta(days=window_days)).strftime("%Y%m%d000000")
    end = (event.event_date + timedelta(days=window_days)).strftime("%Y%m%d235959")
    params = {
        "query": query_terms(event, mode),
        "mode": "artlist",
        "format": "json",
        "maxrecords": 10,
        "sort": "hybridrel",
        "startdatetime": start,
        "enddatetime": end,
    }
    try:
        response = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params=params,
            timeout=12,
            headers={"User-Agent": "FIN496 academic compact news metadata probe"},
        )
    except Exception as exc:
        return {
            "query_status": "request_failed",
            "provider_error_class": type(exc).__name__,
            "provider_error_message_truncated": truncate(exc),
        }
    if response.status_code != 200:
        return {
            "query_status": f"http_{response.status_code}",
            "status_code": response.status_code,
            "provider_error_class": "http_error",
            "provider_error_message_truncated": truncate(response.text, 200),
        }
    try:
        payload = response.json()
    except ValueError as exc:
        return {
            "query_status": "json_parse_failed",
            "status_code": response.status_code,
            "provider_error_class": type(exc).__name__,
            "provider_error_message_truncated": truncate(response.text, 200),
        }
    count, domains, titles, earliest, latest, flags = parse_articles(payload)
    major = count >= 3 or any(flags.values())
    return {
        "query_status": "ok",
        "status_code": response.status_code,
        "article_count": count,
        "top_domains": domains,
        "top_titles_truncated": titles,
        "earliest_published_at": earliest,
        "latest_published_at": latest,
        "major_news_flag": major,
        **flags,
        "provider_error_class": "",
        "provider_error_message_truncated": "",
    }


def optional_provider_diagnostic(provider: str, key_name: str) -> dict[str, Any]:
    key = os.getenv(key_name)
    if not key:
        return {
            "provider": provider,
            "query_type": "key_presence_only",
            "status_code": "",
            "response_parse_status": "not_queried",
            "article_count": 0,
            "error_class": "no_key_in_process_environment",
            "error_message_truncated": "",
            "query_status": "not_available",
        }
    return {
        "provider": provider,
        "query_type": "key_presence_only",
        "status_code": "",
        "response_parse_status": "not_queried_to_avoid_unvetted_keyed_call",
        "article_count": 0,
        "error_class": "key_present",
        "error_message_truncated": "",
        "query_status": "available_but_not_used_in_full_layer",
    }


def provider_diagnostics(events: list[base.EventRecord]) -> list[dict[str, Any]]:
    candidates = [
        next((e for e in events if e.ticker in base.TOP5_TICKERS), events[0]),
        next((e for e in events if e.ticker not in base.TOP5_TICKERS), events[0]),
        RNG.choice(events),
    ]
    rows = []
    for idx, event in enumerate(candidates, start=1):
        result = gdelt_request(event, "ticker_company", 3)
        rows.append(
            {
                "provider": "GDELT_DOC_2",
                "query_type": f"diagnostic_{idx}_{event.ticker}",
                "status_code": result.get("status_code", ""),
                "response_parse_status": "parsed"
                if result.get("query_status") == "ok"
                else "not_parsed",
                "article_count": result.get("article_count", 0),
                "error_class": result.get("provider_error_class", ""),
                "error_message_truncated": result.get("provider_error_message_truncated", ""),
                "query_status": result.get("query_status", ""),
            }
        )
        time.sleep(5.1)
    rows.append(
        optional_provider_diagnostic("Alpha_Vantage_NEWS_SENTIMENT", "ALPHA_VANTAGE_API_KEY")
    )
    rows.append(optional_provider_diagnostic("Financial_Modeling_Prep_News", "FMP_API_KEY"))
    rows.append(optional_provider_diagnostic("NewsAPI", "NEWSAPI_KEY"))
    return rows


def select_probe_events(
    events: list[base.EventRecord], max_events: int = 100
) -> list[base.EventRecord]:
    buckets = [
        [
            e
            for e in events
            if e.ticker in base.TOP5_TICKERS and e.ar_5d is not None and e.ar_5d > 0
        ],
        [
            e
            for e in events
            if e.ticker not in base.TOP5_TICKERS and e.ar_5d is not None and e.ar_5d < 0
        ],
        sorted(
            [e for e in events if e.ar_5d is not None], key=lambda e: e.ar_5d or 0, reverse=True
        )[:100],
        sorted([e for e in events if e.ar_5d is not None], key=lambda e: e.ar_5d or 0)[:100],
        [e for e in events if e.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS],
        [e for e in base.first_per_cluster(events)],
        [e for e in events if e.event_id in lh_sec_clean_ids()],
        events[:],
    ]
    selected: dict[int, base.EventRecord] = {}
    per_bucket = max(1, max_events // len(buckets))
    for bucket in buckets:
        if len(bucket) > per_bucket:
            bucket = RNG.sample(bucket, per_bucket)
        for event in bucket:
            selected[event.event_id] = event
    remaining = [event for event in events if event.event_id not in selected]
    while len(selected) < max_events and remaining:
        event = RNG.choice(remaining)
        selected[event.event_id] = event
        remaining = [item for item in remaining if item.event_id != event.event_id]
    return list(selected.values())[:max_events]


def lh_sec_clean_ids() -> set[int]:
    path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    if not path.exists():
        return set()
    sec = pd.read_csv(path)
    return set(sec.loc[sec["sec_clean_flag"].astype(bool), "event_id"].astype(int))


def best_gdelt_result(event: base.EventRecord) -> dict[str, Any]:
    # GDELT currently enforces a practical one-request-per-five-seconds limit.
    # The full repaired query grid is therefore documented but not exhausted in
    # this capped run; failed or unqueried events remain unknown, not clean.
    modes = ["ticker_company"]
    windows = [5]
    failures = []
    for window in windows:
        for mode in modes:
            result = gdelt_request(event, mode, window)
            status = result.get("query_status", "")
            if status == "ok":
                return {"window": f"+/-{window}", "query_mode": mode, **result}
            failures.append(status)
            if status == "http_429":
                time.sleep(5.5)
                retry = gdelt_request(event, mode, window)
                if retry.get("query_status") == "ok":
                    return {"window": f"+/-{window}", "query_mode": mode, **retry}
                failures.append(retry.get("query_status", "retry_failed"))
            else:
                time.sleep(5.1)
    return {
        "window": "",
        "query_mode": "",
        "article_count": 0,
        "top_domains": "",
        "top_titles_truncated": "",
        "earliest_published_at": "",
        "latest_published_at": "",
        "major_news_flag": False,
        "earnings_news_flag": False,
        "analyst_news_flag": False,
        "product_news_flag": False,
        "legal_regulatory_news_flag": False,
        "macro_sector_news_flag": False,
        "query_status": "all_query_modes_failed",
        "provider_error_class": "|".join(sorted(set(str(x) for x in failures if x))[:5]),
        "provider_error_message_truncated": "",
    }


def event_flags(events: list[base.EventRecord], full_run: bool = False) -> list[dict[str, Any]]:
    rows = []
    sec_clean = lh_sec_clean_ids()
    for event in events:
        result = best_gdelt_result(event)
        queried = result.get("query_status") == "ok"
        major = bool(result.get("major_news_flag"))
        sec_confounded = event.event_id not in sec_clean
        if not queried:
            status = "unknown_provider_failed"
        elif major or sec_confounded:
            status = "confounded"
        else:
            status = "clean"
        rows.append(
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "company_name": event.company_name,
                "event_date": event.event_date.isoformat() if event.event_date else "",
                "provider": "GDELT_DOC_2",
                "window": result.get("window", ""),
                "query_mode": result.get("query_mode", ""),
                "article_count": result.get("article_count", 0),
                "top_domains": result.get("top_domains", ""),
                "top_titles_truncated": result.get("top_titles_truncated", ""),
                "earliest_published_at": result.get("earliest_published_at", ""),
                "latest_published_at": result.get("latest_published_at", ""),
                "major_news_flag": result.get("major_news_flag", False),
                "earnings_news_flag": result.get("earnings_news_flag", False),
                "analyst_news_flag": result.get("analyst_news_flag", False),
                "product_news_flag": result.get("product_news_flag", False),
                "legal_regulatory_news_flag": result.get("legal_regulatory_news_flag", False),
                "macro_sector_news_flag": result.get("macro_sector_news_flag", False),
                "query_status": result.get("query_status", ""),
                "provider_error_class": result.get("provider_error_class", ""),
                "provider_coverage_status": "full" if full_run else "probe",
                "reason_codes": status,
            }
        )
    return rows


def event_study_from_news(
    flags: pd.DataFrame, events: list[base.EventRecord], status: str
) -> list[dict[str, Any]]:
    ids = set(flags.loc[flags["reason_codes"].eq(status), "event_id"].astype(int))
    selected = [event for event in events if event.event_id in ids]
    return [base.spec_row(f"real_news_{status}", selected, "real provider queried where available")]


def main() -> int:
    events = base.fetch_events(base.load_market_data())
    diagnostics = provider_diagnostics(events)
    write_table(NEWS_DIR / "01_provider_diagnostics", diagnostics, "Real News Provider Diagnostics")
    probe_events = select_probe_events(events, 40)
    probe_rows = event_flags(probe_events, full_run=False)
    write_table(
        NEWS_DIR / "02_real_news_probe_event_flags", probe_rows, "Real News Probe Event Flags"
    )
    probe_df = pd.DataFrame(probe_rows)
    ok_rate = float(probe_df["query_status"].eq("ok").mean()) if not probe_df.empty else 0.0
    if ok_rate >= 0.5:
        full_rows = event_flags(events, full_run=True)
    else:
        full_rows = [
            {
                "status": "not_run",
                "reason": f"probe_success_rate_below_threshold_{ok_rate:.3f}",
            }
        ]
    write_table(NEWS_DIR / "03_real_news_full_event_flags", full_rows, "Real News Full Event Flags")
    summary_rows = [
        {
            "provider": "GDELT_DOC_2",
            "scope": "probe_40_runtime_limited",
            "events": len(probe_df),
            "successful_queries": int(probe_df["query_status"].eq("ok").sum())
            if not probe_df.empty
            else 0,
            "success_rate": f"{ok_rate:.3f}",
            "clean_events": int(probe_df["reason_codes"].eq("clean").sum())
            if not probe_df.empty
            else 0,
            "confounded_events": int(probe_df["reason_codes"].eq("confounded").sum())
            if not probe_df.empty
            else 0,
            "unknown_events": int(probe_df["reason_codes"].str.contains("unknown", na=False).sum())
            if not probe_df.empty
            else 0,
            "status": "usable_full_layer"
            if ok_rate >= 0.5
            else "diagnostic_only_provider_unreliable",
        }
    ]
    write_table(NEWS_DIR / "04_news_coverage_summary", summary_rows, "News Coverage Summary")
    clean_rows = event_study_from_news(probe_df, events, "clean") if not probe_df.empty else []
    confounded_rows = (
        event_study_from_news(probe_df, events, "confounded") if not probe_df.empty else []
    )
    write_table(NEWS_DIR / "05_news_clean_event_study", clean_rows, "News-Clean Event Study")
    write_table(
        NEWS_DIR / "06_news_confounded_event_study", confounded_rows, "News-Confounded Event Study"
    )
    interpretation = f"""# Real News Layer Interpretation

The news layer ran provider diagnostics and a stratified real GDELT probe. It
does not simulate news. It stores compact metadata only: counts, domains,
truncated titles, dates, query status, and reason codes.

- Probe events: `{len(probe_df)}`
- Successful GDELT queries: `{int(probe_df["query_status"].eq("ok").sum()) if not probe_df.empty else 0}`
- Probe success rate: `{ok_rate:.3f}`
- Full 2,341-event run status: `{"run" if ok_rate >= 0.5 else "not run because probe success was below 50%"}`

Do not cite the news-clean event study as full-sample evidence unless the full
provider layer succeeds. Failed providers imply `unknown`, not `clean`.
"""
    base.write_md(NEWS_DIR / "07_news_interpretation.md", interpretation)
    print(f"V2 real news layer complete: probe_events={len(probe_df)} success_rate={ok_rate:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
