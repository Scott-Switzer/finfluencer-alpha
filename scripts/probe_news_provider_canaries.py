"""Minimal provider canaries (auth, date filter, parsing). No secret printing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import news_provider_utils as npu  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "news_confound_master" / "provider_canaries"
TICKERS = ("AAPL", "TSLA", "NVDA")
RECENT_START, RECENT_END = "2024-01-02", "2024-01-10"
HIST_START, HIST_END = "2020-03-02", "2020-03-10"


def truthy_key(name: str) -> bool:
    val, _src = npu.load_credential(name)
    return bool(val and str(val).strip())


def row(
    provider: str,
    window: str,
    ticker: str,
    *,
    auth_ok: bool,
    historical_ok: str,
    date_filter_ok: str,
    ticker_filter_ok: str,
    parsing_ok: str,
    quota_perm: str,
    proceed: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "window": window,
        "ticker": ticker,
        "auth_ok": auth_ok,
        "historical_depth_status": historical_ok,
        "date_filter_status": date_filter_ok,
        "ticker_filter_status": ticker_filter_ok,
        "parsing_status": parsing_ok,
        "quota_permission_status": quota_perm,
        "proceed": proceed,
        "detail_safe": detail[:240],
    }


def canary_marketaux(ticker: str, window: str, start: str, end: str, key: str | None) -> dict[str, Any]:
    if not key:
        return row("marketaux", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_key", proceed="skip", detail="no key")
    auth_name = "api_" + "token"
    params = {
        "symbols": ticker,
        "published_after": f"{start}T00:00",
        "published_before": f"{end}T23:59",
        "limit": 3,
        auth_name: key,
    }
    status, payload, err = npu.query_json_no_retry("https://api.marketaux.com/v1/news/all", params)
    items = npu.payload_items(payload, ("data",))
    ok_parse = isinstance(payload, (dict, list)) or status == "ok"
    auth = status == "ok" or ("http_401" not in status and "http_403" not in status)
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "marketaux",
        window,
        ticker,
        auth_ok=auth and status == "ok",
        historical_ok="recent_ok" if window == "recent" else "historical_ok" if status == "ok" else "unknown",
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok" if ok_parse else "parse_issue",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} items={len(items)} err={err[:80]}",
    )


def canary_polygon(ticker: str, window: str, start: str, end: str, key: str | None) -> dict[str, Any]:
    if not key:
        return row("massive_polygon", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_key", proceed="skip", detail="no key")
    base = "https://api.polygon.io/v2/reference/news"
    params = {"ticker": ticker, "published_utc.gte": start, "published_utc.lte": end, "limit": 5, "apiKey": key}
    status, payload, err = npu.query_json_no_retry(base, params)
    items = npu.payload_items(payload, ("results",))
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "massive_polygon",
        window,
        ticker,
        auth_ok=status == "ok",
        historical_ok="ok" if status == "ok" else status,
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok" if isinstance(payload, dict) or status != "ok" else "issue",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def canary_newsapi(ticker: str, window: str, start: str, end: str, key: str | None) -> dict[str, Any]:
    if not key:
        return row("newsapi", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_key", proceed="skip", detail="no key")
    params = {"q": ticker, "from": start, "to": end, "pageSize": 3, "sortBy": "publishedAt", "apiKey": key}
    status, payload, err = npu.query_json_no_retry("https://newsapi.org/v2/everything", params)
    items = npu.payload_items(payload, ("articles",))
    q, p = npu.provider_quota_or_permission(status)
    hist = "developer_plan_limited" if window == "historical" else "recent"
    return row(
        "newsapi",
        window,
        ticker,
        auth_ok=status == "ok",
        historical_ok=hist,
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" and window == "recent" else "skip_if_historical",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def canary_fmp(ticker: str, window: str, start: str, end: str, key: str | None) -> dict[str, Any]:
    if not key:
        return row("fmp_stock_news", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_key", proceed="skip", detail="no key")
    params = {"tickers": ticker, "from": start, "to": end, "limit": 5, "apikey": key}
    status, payload, err = npu.query_json_no_retry("https://financialmodelingprep.com/api/v3/stock_news", params)
    items = npu.payload_items(payload, ())
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "fmp_stock_news",
        window,
        ticker,
        auth_ok=status == "ok",
        historical_ok="ok" if status == "ok" else status,
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def canary_finnhub(ticker: str, window: str, start: str, end: str, key: str | None) -> dict[str, Any]:
    if not key:
        return row("finnhub", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_key", proceed="skip", detail="no key")
    auth = "token"
    params = {"symbol": ticker, "from": start, "to": end, auth: key}
    status, payload, err = npu.query_json_no_retry("https://finnhub.io/api/v1/company-news", params)
    items = npu.payload_items(payload, ())
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "finnhub",
        window,
        ticker,
        auth_ok=status == "ok",
        historical_ok="ok" if status == "ok" else status,
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def canary_eodhd(ticker: str, window: str, start: str, end: str, key: str | None) -> dict[str, Any]:
    if not key:
        return row("eodhd", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_key", proceed="skip", detail="no key")
    auth = "api_token"
    params = {"s": f"{ticker}.US", "from": start, "to": end, "limit": 5, auth: key, "fmt": "json"}
    status, payload, err = npu.query_json_no_retry("https://eodhd.com/api/news", params)
    items = npu.payload_items(payload, ())
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "eodhd",
        window,
        ticker,
        auth_ok=status == "ok",
        historical_ok="ok" if status == "ok" else status,
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def canary_alpaca(ticker: str, window: str, start: str, end: str, key_id: str | None, secret: str | None) -> dict[str, Any]:
    if not key_id or not secret:
        return row("alpaca_news", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_secret" if key_id and not secret else "missing_key", proceed="skip", detail="alpaca requires id+secret")
    url = "https://data.alpaca.markets/v1beta1/news"
    params = {"symbols": ticker, "start": start + "T00:00:00Z", "end": end + "T23:59:59Z", "limit": 5}
    headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}
    status, payload, err = npu.query_json_no_retry(url, params, headers=headers)
    items = npu.payload_items(payload, ("news", "items"))
    if not items and isinstance(payload, dict) and isinstance(payload.get("news"), list):
        items = [x for x in payload["news"] if isinstance(x, dict)]
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "alpaca_news",
        window,
        ticker,
        auth_ok=status == "ok",
        historical_ok="ok" if status == "ok" else status,
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def canary_alpha_vantage(ticker: str, window: str, key: str | None) -> dict[str, Any]:
    if not key:
        return row("alpha_vantage_news_sentiment", window, ticker, auth_ok=False, historical_ok="skip", date_filter_ok="skip", ticker_filter_ok="skip", parsing_ok="skip", quota_perm="missing_key", proceed="skip", detail="no key")
    params = {"function": "NEWS_SENTIMENT", "tickers": ticker, "apikey": key, "limit": 5}
    status, payload, err = npu.query_json_no_retry("https://www.alphavantage.co/query", params)
    feed = payload.get("feed", []) if isinstance(payload, dict) else []
    items = [x for x in feed if isinstance(x, dict)]
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "alpha_vantage_news_sentiment",
        window,
        ticker,
        auth_ok=status == "ok",
        historical_ok="endpoint_dependent",
        date_filter_ok="ok" if status == "ok" else status,
        ticker_filter_ok="ok" if status == "ok" else status,
        parsing_ok="ok",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def canary_gdelt() -> dict[str, Any]:
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query": "AAPL", "mode": "artlist", "maxrecords": 3, "format": "json"}
    status, payload, err = npu.query_json_no_retry(url, params, timeout=45)
    items = npu.payload_items(payload, ("articles",))
    q, p = npu.provider_quota_or_permission(status)
    return row(
        "gdelt_doc_api",
        "connectivity",
        "AAPL",
        auth_ok=status == "ok",
        historical_ok="unknown_single_shot",
        date_filter_ok="not_exercised",
        ticker_filter_ok="query_only",
        parsing_ok="ok" if isinstance(payload, (dict, list)) or status != "ok" else "issue",
        quota_perm=("quota" if q else "permission" if p else "ok"),
        proceed="yes" if status == "ok" else "skip",
        detail=f"status={status} n={len(items)} err={err[:80]}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

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

    rows: list[dict[str, Any]] = []
    counts: list[dict[str, Any]] = []

    if args.no_network:
        frame = pd.DataFrame([{"note": "no_network_flag"}])
        frame.to_csv(OUT / "provider_canary_status.csv", index=False)
        (OUT / "provider_canary_summary.md").write_text("# Canary run skipped\n\n`--no-network` set.\n", encoding="utf-8")
        pd.DataFrame(counts).to_csv(OUT / "provider_canary_sample_counts.csv", index=False)
        return 0

    rows.append(canary_gdelt())

    for t in TICKERS:
        rows.append(canary_alpha_vantage(t, "recent", keys["av"]))
        for window, start, end in (("recent", RECENT_START, RECENT_END), ("historical", HIST_START, HIST_END)):
            rows.append(canary_marketaux(t, window, start, end, keys["marketaux"]))
            rows.append(canary_polygon(t, window, start, end, keys["polygon"]))
            rows.append(canary_fmp(t, window, start, end, keys["fmp"]))
            rows.append(canary_finnhub(t, window, start, end, keys["finnhub"]))
            rows.append(canary_eodhd(t, window, start, end, keys["eodhd"]))
            rows.append(canary_alpaca(t, window, start, end, keys["alpaca_id"], keys["alpaca_secret"]))
            if window == "recent":
                rows.append(canary_newsapi(t, window, start, end, keys["newsapi"]))
            else:
                rows.append(
                    row(
                        "newsapi",
                        "historical",
                        t,
                        auth_ok=bool(keys["newsapi"]),
                        historical_ok="skipped_free_tier",
                        date_filter_ok="skipped",
                        ticker_filter_ok="skipped",
                        parsing_ok="skipped",
                        quota_perm="plan_limited",
                        proceed="skip",
                        detail="NewsAPI developer tier is recent-oriented; historical not probed here.",
                    )
                )

    status = pd.DataFrame(rows)
    status.to_csv(OUT / "provider_canary_status.csv", index=False)

    for provider in status["provider"].unique():
        sub = status[status["provider"] == provider]
        counts.append({"provider": provider, "rows": len(sub), "proceed_yes": int(sub["proceed"].eq("yes").sum())})
    pd.DataFrame(counts).to_csv(OUT / "provider_canary_sample_counts.csv", index=False)

    body = """# Provider canaries

Minimal calls per provider. Authentication is **not** logged. See `provider_canary_status.csv`.

## Interpretation

- `proceed=yes` means the canary returned HTTP OK for at least one ticker/window.
- `403/429` must be treated as provider-limited in downstream layers, not as clean no-news.
"""
    (OUT / "provider_canary_summary.md").write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
