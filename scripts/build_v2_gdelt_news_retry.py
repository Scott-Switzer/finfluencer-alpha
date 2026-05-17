from __future__ import annotations

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

OUT_DIR = utils.OUT_DIR / "news_gdelt_retry"
QUERY_MODES = ["company", "company_stock", "ticker_company", "company_earnings", "company_analyst", "company_sec"]
WINDOWS = [1, 3, 5]


def trunc(value: Any, limit: int = 180) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ")[:limit]


def query_text(row: pd.Series, mode: str) -> str:
    company = str(row.company_name or row.ticker).replace('"', "")
    ticker = str(row.ticker)
    if mode == "company":
        return f'"{company}"'
    if mode == "company_stock":
        return f'"{company}" stock'
    if mode == "ticker_company":
        return f'{ticker} "{company}"'
    if mode == "company_earnings":
        return f'"{company}" earnings'
    if mode == "company_analyst":
        return f'"{company}" analyst'
    return f'"{company}" SEC'


def stratified_events(limit: int = 50) -> pd.DataFrame:
    events = utils.event_manifest()
    panel = utils.forward_panel(["5D"])[["event_id", "spy_bhar", "top5_flag", "sec_clean_flag"]]
    events = events.merge(panel, on="event_id", how="left")
    parts = []
    top = events[events["top5_flag"].astype(str).str.lower().eq("true")].sort_values("spy_bhar", ascending=False)
    non = events[~events["top5_flag"].astype(str).str.lower().eq("true")].sort_values("spy_bhar")
    sec = events[events["sec_clean_flag"].astype(str).str.lower().eq("true")]
    parts.extend([top.head(10), non.head(10), sec.head(10)])
    parts.append(events.sample(min(20, len(events)), random_state=496))
    out = pd.concat(parts).drop_duplicates("event_id").head(limit)
    return out


def request_gdelt(row: pd.Series, mode: str, window: int) -> dict[str, Any]:
    event_date = pd.to_datetime(row.event_date).date()
    start = (event_date - timedelta(days=window)).strftime("%Y%m%d000000")
    end = (event_date + timedelta(days=window)).strftime("%Y%m%d235959")
    params = {
        "query": query_text(row, mode),
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
            timeout=20,
            headers={"User-Agent": "FIN496 academic compact metadata retry"},
        )
    except Exception as exc:
        return {"query_status": "request_failed", "status_code": "", "error_class": type(exc).__name__, "truncated_error": trunc(exc)}
    if response.status_code != 200:
        return {
            "query_status": f"http_{response.status_code}",
            "status_code": response.status_code,
            "error_class": "http_error",
            "truncated_error": trunc(response.text),
        }
    try:
        payload = response.json()
    except ValueError:
        return {"query_status": "json_parse_failed", "status_code": response.status_code, "error_class": "json", "truncated_error": trunc(response.text)}
    articles = payload.get("articles", []) or []
    domains = [urlparse(a.get("url", "")).netloc.replace("www.", "") for a in articles]
    titles = [trunc(a.get("title"), 90) for a in articles[:3]]
    return {
        "query_status": "ok",
        "status_code": response.status_code,
        "error_class": "",
        "truncated_error": "",
        "article_count": len(articles),
        "top_domains": ";".join(domain for domain, _ in Counter(domains).most_common(5) if domain),
        "top_titles_truncated": " || ".join(titles),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = stratified_events(50)
    diagnostics = []
    flags = []
    ok_events = 0
    for _, event in events.iterrows():
        event_ok = False
        event_count = 0
        last_status = "not_queried"
        for mode in QUERY_MODES[:2]:
            for window in WINDOWS[:1]:
                result = request_gdelt(event, mode, window)
                row = {
                    "provider": "GDELT_DOC_2",
                    "event_id": int(event.event_id),
                    "ticker": event.ticker,
                    "event_date": event.event_date,
                    "query_mode": mode,
                    "window": f"pm{window}",
                    "article_count": result.get("article_count", 0),
                    "coverage_status": "queried" if result.get("query_status") == "ok" else "failed",
                    **result,
                }
                diagnostics.append(row)
                last_status = str(result.get("query_status"))
                if result.get("query_status") == "ok":
                    event_ok = True
                    event_count = max(event_count, int(result.get("article_count", 0)))
                    break
                if str(result.get("query_status", "")).startswith("http_429"):
                    time.sleep(6.2)
                else:
                    time.sleep(5.2)
            if event_ok:
                break
        if event_ok:
            ok_events += 1
        flags.append(
            {
                "event_id": int(event.event_id),
                "ticker": event.ticker,
                "event_date": event.event_date,
                "gdelt_query_success": event_ok,
                "gdelt_article_count": event_count,
                "gdelt_major_news_flag": event_count >= 3,
                "gdelt_news_clean_flag": event_ok and event_count < 3,
                "gdelt_news_confounded_flag": event_ok and event_count >= 3,
                "gdelt_news_unknown_flag": not event_ok,
                "query_status": "ok" if event_ok else last_status,
            }
        )
    success_rate = ok_events / len(events) if len(events) else 0.0
    utils.write_csv(OUT_DIR / "01_gdelt_retry_diagnostics.csv", diagnostics)
    utils.write_md(OUT_DIR / "01_gdelt_retry_diagnostics.md", "GDELT Retry Diagnostics", utils.md_table(diagnostics))
    utils.write_csv(OUT_DIR / "02_gdelt_probe_flags.csv", flags)
    utils.write_md(
        OUT_DIR / "03_gdelt_retry_interpretation.md",
        "GDELT Retry Interpretation",
        f"Probe events: {len(events)}. Successful events: {ok_events}. Success rate: {success_rate:.3f}. GDELT is {'usable for limited diagnostics' if success_rate >= 0.5 else 'not usable for main robustness'} in this run. No raw article bodies were stored.",
    )
    print(f"GDELT retry complete: events={len(events)} success_rate={success_rate:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
