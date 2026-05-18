"""Execute budgeted provider calls; compact cache only."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import news_provider_utils as npu  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

PLAN = utils.OUT_DIR / "news_confound_master" / "query_plan" / "budgeted_news_query_plan.csv"
OUT_DIR = utils.OUT_DIR / "news_confound_master" / "provider_compact_cache"
CACHE_ART = OUT_DIR / "compact_news_articles.csv"
STATUS_CSV = OUT_DIR / "provider_fetch_status.csv"


def fp_key(provider: str, event_id: int, title: str, pub: str) -> str:
    h = hashlib.sha256(f"{provider}|{event_id}|{pub}|{title}".encode("utf-8", errors="replace")).hexdigest()[:20]
    return h


def load_done_keys() -> set[tuple[str, int]]:
    if not CACHE_ART.exists():
        return set()
    frame = pd.read_csv(CACHE_ART, usecols=lambda c: c in {"provider", "event_id_anchor"})
    return { (str(r.provider), int(r.event_id_anchor)) for r in frame.itertuples(index=False) }


def dispatch_marketaux(ticker: str, start: str, end: str, key: str) -> tuple[str, list[dict[str, Any]], str]:
    auth = "api_token"
    params = {"symbols": ticker, "published_after": f"{start}T00:00", "published_before": f"{end}T23:59", "limit": 25, auth: key}
    status, payload, err = npu.query_json_no_retry("https://api.marketaux.com/v1/news/all", params)
    return status, npu.payload_items(payload, ("data",)), err


def dispatch_polygon(ticker: str, start: str, end: str, key: str) -> tuple[str, list[dict[str, Any]], str]:
    params = {"ticker": ticker, "published_utc.gte": start, "published_utc.lte": end, "limit": 25, "apiKey": key}
    status, payload, err = npu.query_json_no_retry("https://api.polygon.io/v2/reference/news", params)
    return status, npu.payload_items(payload, ("results",)), err


def dispatch_newsapi(ticker: str, start: str, end: str, key: str) -> tuple[str, list[dict[str, Any]], str]:
    params = {"q": ticker, "from": start, "to": end, "pageSize": 25, "sortBy": "publishedAt", "apiKey": key}
    status, payload, err = npu.query_json_no_retry("https://newsapi.org/v2/everything", params)
    return status, npu.payload_items(payload, ("articles",)), err


def dispatch_fmp(ticker: str, start: str, end: str, key: str) -> tuple[str, list[dict[str, Any]], str]:
    status, items, err = npu.query_fmp_stock_news(ticker, start, end, key, limit=25)
    return status, items, err


def dispatch_finnhub(ticker: str, start: str, end: str, key: str) -> tuple[str, list[dict[str, Any]], str]:
    params = {"symbol": ticker, "from": start, "to": end, "token": key}
    status, payload, err = npu.query_json_no_retry("https://finnhub.io/api/v1/company-news", params)
    return status, npu.payload_items(payload, ()), err


def dispatch_eodhd(ticker: str, start: str, end: str, key: str) -> tuple[str, list[dict[str, Any]], str]:
    params = {"s": f"{ticker}.US", "from": start, "to": end, "limit": 25, "api_token": key, "fmt": "json"}
    status, payload, err = npu.query_json_no_retry("https://eodhd.com/api/news", params)
    return status, npu.payload_items(payload, ()), err


def dispatch_alpaca(ticker: str, start: str, end: str, key_id: str, secret: str) -> tuple[str, list[dict[str, Any]], str]:
    params = {"symbols": ticker, "start": start + "T00:00:00Z", "end": end + "T23:59:59Z", "limit": 25}
    headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}
    status, payload, err = npu.query_json_no_retry("https://data.alpaca.markets/v1beta1/news", params, headers=headers)
    items = npu.payload_items(payload, ("news", "items"))
    if not items and isinstance(payload, dict) and isinstance(payload.get("news"), list):
        items = [x for x in payload["news"] if isinstance(x, dict)]
    return status, items, err


def dispatch_av(ticker: str, key: str) -> tuple[str, list[dict[str, Any]], str]:
    params = {"function": "NEWS_SENTIMENT", "tickers": ticker, "apikey": key, "limit": 25}
    status, payload, err = npu.query_json_no_retry("https://www.alphavantage.co/query", params)
    feed = payload.get("feed", []) if isinstance(payload, dict) else []
    items = [x for x in feed if isinstance(x, dict)]
    return status, items, err


def dispatch_gdelt(ticker: str, start: str, end: str) -> tuple[str, list[dict[str, Any]], str]:
    q = f"{ticker} sourcetype:news"
    params = {"query": q, "mode": "artlist", "maxrecords": 25, "format": "json", "startdatetime": start, "enddatetime": end}
    status, payload, err = npu.query_json_no_retry("https://api.gdeltproject.org/api/v2/doc/doc", params, timeout=45)
    return status, npu.payload_items(payload, ("articles",)), err


def select_dispatch(row: pd.Series, keys: dict[str, str | None]) -> tuple[str, list[dict[str, Any]], str]:
    provider = str(row["provider"])
    ticker = str(row["ticker"])
    manifest = utils.event_manifest()
    ev = manifest[manifest["event_id"] == int(row["event_id_anchor"])].head(1)
    if ev.empty:
        return "missing_event", [], "event_id not in manifest"
    event_date = npu.parse_date(ev.iloc[0]["event_date"])
    if event_date is None:
        return "bad_date", [], "bad event date"
    start, end = npu.window_bounds(event_date, 7)
    if provider == "marketaux":
        k = keys.get("marketaux")
        return dispatch_marketaux(ticker, start, end, k) if k else ("missing_key", [], "")
    if provider == "massive_polygon":
        k = keys.get("polygon")
        return dispatch_polygon(ticker, start, end, k) if k else ("missing_key", [], "")
    if provider == "newsapi":
        k = keys.get("newsapi")
        return dispatch_newsapi(ticker, start, end, k) if k else ("missing_key", [], "")
    if provider == "fmp_stock_news":
        k = keys.get("fmp")
        return dispatch_fmp(ticker, start, end, k) if k else ("missing_key", [], "")
    if provider == "finnhub":
        k = keys.get("finnhub")
        return dispatch_finnhub(ticker, start, end, k) if k else ("missing_key", [], "")
    if provider == "eodhd":
        k = keys.get("eodhd")
        return dispatch_eodhd(ticker, start, end, k) if k else ("missing_key", [], "")
    if provider == "alpaca_news":
        if keys.get("alpaca_id") and keys.get("alpaca_secret"):
            return dispatch_alpaca(ticker, start, end, str(keys["alpaca_id"]), str(keys["alpaca_secret"]))
        return ("missing_secret", [], "")
    if provider == "alpha_vantage_news_sentiment":
        k = keys.get("av")
        return dispatch_av(ticker, k) if k else ("missing_key", [], "")
    if provider == "gdelt_doc_api":
        return dispatch_gdelt(ticker, start, end)
    return ("unknown_provider", [], provider)


def compact_rows(
    provider: str,
    event_id: int,
    ticker: str,
    items: list[dict[str, Any]],
    company_name: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = npu.title_text(item)
        pub = str(npu.first_item_date(item) or "")
        if not npu.relevant_item(item, ticker, company_name):
            continue
        k = fp_key(provider, event_id, title, pub)
        if k in seen:
            continue
        seen.add(k)
        out.append(
            {
                "provider": provider,
                "event_id_anchor": event_id,
                "ticker": ticker,
                "title_fingerprint": k,
                "published_date": pub,
                "relevant_hit": True,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-total-calls", type=int, default=500)
    parser.add_argument("--provider", type=str, default="")
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not PLAN.exists():
        print("Missing plan; run plan_budgeted_news_queries.py")
        return 1
    plan = pd.read_csv(PLAN)
    if args.provider:
        plan = plan[plan["provider"].astype(str) == args.provider]
    if args.priority_only:
        plan = plan.sort_values("priority_score").head(min(len(plan), args.max_total_calls))

    if args.dry_run:
        print(plan.groupby("provider").size().to_string())
        print(f"total planned rows {len(plan)}")
        return 0

    if not args.execute:
        print("Specify --execute or use --dry-run")
        return 1

    if args.no_network:
        print("no-network set; refusing execute")
        return 1

    keys = {
        "marketaux": npu.load_credential("MARKETAUX_API_KEY")[0],
        "polygon": npu.load_credential("MASSIVE_API_KEY")[0],
        "newsapi": npu.load_credential("NEWSAPI_API_KEY")[0],
        "fmp": npu.load_credential("FMP_API_KEY")[0],
        "finnhub": npu.load_credential("FINNHUB_API_KEY")[0],
        "eodhd": npu.load_credential("EODHD_API_KEY")[0],
        "av": npu.load_credential("ALPHAVANTAGE_API_KEY")[0],
        "alpaca_id": npu.load_credential("ALPACA_API_KEY")[0],
        "alpaca_secret": npu.load_credential("ALPACA_SECRET_KEY")[0],
    }

    manifest = utils.event_manifest()
    done = load_done_keys() if args.resume else set()
    articles: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    calls = 0

    plan = plan.sort_values("priority_score")
    for _, row in plan.iterrows():
        prov = str(row["provider"])
        eid = int(row["event_id_anchor"])
        if args.resume and (prov, eid) in done:
            continue
        if calls >= args.max_total_calls:
            break
        ev = manifest[manifest["event_id"] == eid].head(1)
        company = str(ev.iloc[0]["company_name"]) if not ev.empty else ""
        status, items, err = select_dispatch(row, keys)
        calls += 1
        is_quota, is_perm = npu.provider_quota_or_permission(status)
        hits = len([i for i in items if npu.relevant_item(i, str(row["ticker"]), company)])
        status_rows.append(
            {
                "provider": prov,
                "event_id_anchor": eid,
                "query_status": status,
                "items_returned": len(items),
                "relevant_hits": hits,
                "quota_limited": is_quota,
                "permission_limited": is_perm,
                "detail_safe": err[:120],
            }
        )
        for crow in compact_rows(prov, eid, str(row["ticker"]), items, company):
            articles.append(crow)

    if CACHE_ART.exists() and articles:
        old = pd.read_csv(CACHE_ART)
        articles = pd.concat([old, pd.DataFrame(articles)], ignore_index=True).drop_duplicates(
            subset=["provider", "event_id_anchor", "title_fingerprint"]
        )
        articles.to_csv(CACHE_ART, index=False)
    elif articles:
        pd.DataFrame(articles).to_csv(CACHE_ART, index=False)

    if STATUS_CSV.exists() and status_rows:
        pd.concat([pd.read_csv(STATUS_CSV), pd.DataFrame(status_rows)], ignore_index=True).to_csv(STATUS_CSV, index=False)
    elif status_rows:
        pd.DataFrame(status_rows).to_csv(STATUS_CSV, index=False)

    summary = f"""# Provider fetch summary

Executed calls (this run): **{calls}**
Articles cache rows: **{len(pd.read_csv(CACHE_ART)) if CACHE_ART.exists() else 0}**

403/429 and missing keys are **provider-limited** — not clean no-news.
"""
    (OUT_DIR / "provider_fetch_summary.md").write_text(summary, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
