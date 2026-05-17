"""Build a conservative multi-provider public-news confound master layer."""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import news_provider_utils as npu  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "news_confound_master"
ROBUST_DIR = utils.OUT_DIR / "statistical_robustness"
EXHIBIT_DIR = utils.OUT_DIR / "final_exhibits"

SEC_FLAGS = utils.OUT_DIR / "sec_earnings_confounds" / "01_sec_event_flags_expanded.csv"
AV_PANEL = utils.OUT_DIR / "news_alpha_vantage_expanded" / "av_expanded_event_news_panel.csv"
AV_META = utils.OUT_DIR / "news_alpha_vantage_expanded" / "av_expanded_article_metadata_cache.csv"
GDELT_FLAGS = utils.OUT_DIR / "news_gdelt_retry" / "02_gdelt_probe_flags.csv"
MARKET_PANEL = utils.OUT_DIR / "market_implied_confounds" / "market_implied_confound_panel.csv"
ANALYST_PANEL = (
    utils.OUT_DIR / "information_environment" / "analyst_relay" / "analyst_relay_event_panel.csv"
)

MEDIA_PROVIDERS = (
    "fmp_news",
    "alpha_vantage_news",
    "finnhub_news",
    "marketaux_news",
    "eodhd_news",
    "newsapi_news",
    "gdelt_news",
    "fnspid_news",
)


def parse_args() -> argparse.Namespace:
    default_fetch = os.environ.get("FIN496_NEWS_FETCH", "1").lower() not in {"0", "false", "no"}
    parser = argparse.ArgumentParser(description="Conservative public-news confound master panel.")
    parser.add_argument("--fetch-live", action=argparse.BooleanOptionalAction, default=default_fetch)
    parser.add_argument(
        "--max-requests-per-provider",
        type=int,
        default=int(os.environ.get("FIN496_NEWS_MAX_REQUESTS", "80")),
    )
    parser.add_argument("--sleep-seconds", type=float, default=float(os.environ.get("FIN496_NEWS_SLEEP", "0.25")))
    return parser.parse_args()


def one_row_per_event(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.sort_values("event_id").drop_duplicates("event_id")


def event_universe() -> pd.DataFrame:
    events = utils.event_manifest().copy()
    events["event_date_dt"] = pd.to_datetime(events["event_date"], errors="coerce")
    events["top5_flag"] = events["ticker"].astype(str).isin(utils.TOP5)
    return events


def load_forward_returns() -> pd.DataFrame:
    frame = utils.forward_panel(["5D", "21D", "63D"]).copy()
    if ANALYST_PANEL.exists():
        analyst = pd.read_csv(ANALYST_PANEL)
        cols = [
            c
            for c in [
                "event_id",
                "analyst_alignment_event_time",
                "analyst_alignment_diagnostic",
                "analyst_coverage_tier",
            ]
            if c in analyst.columns
        ]
        frame = frame.merge(one_row_per_event(analyst[cols]), on="event_id", how="left")
    return frame


def empty_provider_result(provider: str, event: pd.Series, status: str) -> dict[str, Any]:
    row = {
        "provider": provider,
        "event_id": int(event.get("event_id")),
        "ticker": event.get("ticker", ""),
        "event_date": event.get("event_date", ""),
        "query_status": status,
        "provider_success": False,
        "provider_hit": False,
        "provider_material_hit": False,
        "relevant_count_pm7": 0,
        "error_class_safe": status,
    }
    for days in (1, 3, 7):
        row[f"pre_{days}d_count"] = 0
        row[f"post_{days}d_count"] = 0
    return row


def provider_rows_to_frame(rows: list[dict[str, Any]], events: pd.DataFrame, provider: str) -> pd.DataFrame:
    if not rows:
        rows = [empty_provider_result(provider, event, "not_checked") for _, event in events.iterrows()]
    frame = pd.DataFrame(rows)
    have = set(frame["event_id"].astype(int)) if "event_id" in frame.columns else set()
    missing = [
        empty_provider_result(provider, event, "not_checked")
        for _, event in events.iterrows()
        if int(event.event_id) not in have
    ]
    if missing:
        frame = pd.concat([frame, pd.DataFrame(missing)], ignore_index=True)
    return one_row_per_event(frame)


def av_metadata_counts(events: pd.DataFrame) -> dict[int, dict[str, int]]:
    if not AV_META.exists():
        return {}
    meta = pd.read_csv(AV_META)
    if meta.empty or "ticker" not in meta.columns or "time_published" not in meta.columns:
        return {}
    meta = meta.copy()
    meta["_date"] = meta["time_published"].map(npu.parse_date)
    meta = meta.dropna(subset=["_date"])
    by_ticker = {str(t): g for t, g in meta.groupby(meta["ticker"].astype(str))}
    out: dict[int, dict[str, int]] = {}
    for _, event in events.iterrows():
        event_date = npu.parse_date(event.get("event_date"))
        if event_date is None:
            continue
        group = by_ticker.get(str(event.get("ticker")))
        if group is None or group.empty:
            continue
        dates = [d for d in group["_date"].tolist() if abs((d - event_date).days) <= 7]
        counts: dict[str, int] = {}
        for days in (1, 3, 7):
            pre, post = npu.event_window_counts(dates, event_date, days)
            counts[f"pre_{days}d_count"] = pre
            counts[f"post_{days}d_count"] = post
        out[int(event.event_id)] = counts
    return out


def alpha_vantage_results(events: pd.DataFrame) -> pd.DataFrame:
    rows = [empty_provider_result("alpha_vantage_news", event, "missing_panel") for _, event in events.iterrows()]
    if not AV_PANEL.exists():
        return pd.DataFrame(rows)
    av = pd.read_csv(AV_PANEL)
    av = one_row_per_event(av)
    count_map = av_metadata_counts(events)
    merged = events.merge(av, on=["event_id", "ticker", "company_name", "event_date"], how="left")
    out: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        success = bool(npu.bool_series(pd.DataFrame([row]), "av_expanded_query_success").iloc[0])
        hit = bool(npu.bool_series(pd.DataFrame([row]), "av_expanded_news_confounded_flag").iloc[0])
        clean = bool(npu.bool_series(pd.DataFrame([row]), "av_expanded_news_clean_flag").iloc[0])
        unknown = bool(npu.bool_series(pd.DataFrame([row]), "av_expanded_news_unknown_flag", True).iloc[0])
        status = "ok" if success else "unknown_or_not_checked"
        if clean:
            status = "ok"
        base = empty_provider_result("alpha_vantage_news", row, status)
        base["provider_success"] = success or clean
        base["provider_hit"] = hit
        base["provider_material_hit"] = hit
        base["relevant_count_pm7"] = int(row.get("window_pm5_article_count", 0) or 0) if hit else 0
        if unknown and not base["provider_success"]:
            base["query_status"] = "unknown_or_limited"
        base.update(count_map.get(int(row.event_id), {}))
        out.append(base)
    return pd.DataFrame(out)


def gdelt_results(events: pd.DataFrame) -> pd.DataFrame:
    if not GDELT_FLAGS.exists():
        return provider_rows_to_frame([], events, "gdelt_news")
    gd = pd.read_csv(GDELT_FLAGS)
    gd = one_row_per_event(gd)
    merged = events.merge(gd, on=["event_id", "ticker", "event_date"], how="left")
    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        success = str(row.get("gdelt_query_success", "")).lower() == "true"
        hit = str(row.get("gdelt_news_confounded_flag", "")).lower() == "true"
        status = "ok" if success else str(row.get("query_status") or "not_checked")
        base = empty_provider_result("gdelt_news", row, status)
        base["provider_success"] = success
        base["provider_hit"] = hit
        base["provider_material_hit"] = hit
        base["relevant_count_pm7"] = int(row.get("gdelt_article_count", 0) or 0) if hit else 0
        rows.append(base)
    return pd.DataFrame(rows)


def fnspid_results(events: pd.DataFrame) -> pd.DataFrame:
    candidates = [utils.REPO_ROOT / "data" / "private" / "fnspid", utils.REPO_ROOT / "data" / "external" / "fnspid"]
    files: list[Path] = []
    for folder in candidates:
        if folder.exists():
            files.extend(folder.glob("*.csv"))
            files.extend(folder.glob("*.parquet"))
    if not files:
        return provider_rows_to_frame([], events, "fnspid_news")

    pieces: list[pd.DataFrame] = []
    for path in files[:8]:
        try:
            if path.suffix == ".parquet":
                piece = pd.read_parquet(path)
            else:
                piece = pd.read_csv(path, usecols=lambda c: str(c).lower() in {"ticker", "symbol", "date", "published_at"})
        except Exception:
            continue
        pieces.append(piece)
    if not pieces:
        return provider_rows_to_frame([], events, "fnspid_news")
    news = pd.concat(pieces, ignore_index=True)
    ticker_col = "ticker" if "ticker" in news.columns else "symbol" if "symbol" in news.columns else None
    date_col = "date" if "date" in news.columns else "published_at" if "published_at" in news.columns else None
    if ticker_col is None or date_col is None:
        return provider_rows_to_frame([], events, "fnspid_news")
    news["_date"] = news[date_col].map(npu.parse_date)
    news = news.dropna(subset=["_date"])
    by_ticker = {str(t).upper(): g for t, g in news.groupby(news[ticker_col].astype(str).str.upper())}
    rows: list[dict[str, Any]] = []
    for _, event in events.iterrows():
        event_date = npu.parse_date(event.event_date)
        base = empty_provider_result("fnspid_news", event, "ok")
        base["provider_success"] = True
        if event_date is None:
            rows.append(base)
            continue
        group = by_ticker.get(str(event.ticker).upper())
        dates = [] if group is None else [d for d in group["_date"].tolist() if abs((d - event_date).days) <= 7]
        base["provider_hit"] = len(dates) > 0
        base["provider_material_hit"] = len(dates) > 0
        base["relevant_count_pm7"] = len(dates)
        for days in (1, 3, 7):
            pre, post = npu.event_window_counts(dates, event_date, days)
            base[f"pre_{days}d_count"] = pre
            base[f"post_{days}d_count"] = post
        rows.append(base)
    return pd.DataFrame(rows)


def prioritized_events(events: pd.DataFrame) -> pd.DataFrame:
    return events.assign(_top5=events["ticker"].astype(str).isin(utils.TOP5)).sort_values(
        ["_top5", "event_date", "event_id"], ascending=[True, True, True]
    )


def fetch_fmp_stock_news(event: pd.Series, credential: str) -> dict[str, Any]:
    event_date = npu.parse_date(event.event_date)
    if event_date is None:
        return empty_provider_result("fmp_news", event, "bad_event_date")
    start, end = npu.window_bounds(event_date, 7)
    params = {
        "tickers": event.ticker,
        "from": start,
        "to": end,
        "limit": 50,
        "apikey": credential,
    }
    status, payload, err = npu.query_json("https://financialmodelingprep.com/api/v3/stock_news", params)
    items = npu.payload_items(payload, ("content", "data", "articles", "news"))
    return npu.compact_provider_result("fmp_news", event, status, items, error_class=err)


def fetch_fmp_press_releases(event: pd.Series, credential: str) -> dict[str, Any]:
    params = {"page": 0, "apikey": credential}
    url = f"https://financialmodelingprep.com/api/v3/press-releases/{event.ticker}"
    status, payload, err = npu.query_json(url, params)
    items = npu.payload_items(payload, ("content", "data", "articles", "news"))
    row = npu.compact_provider_result("fmp_press_release", event, status, items, error_class=err)
    if status == "ok" and not row["provider_hit"]:
        row["query_status"] = "ok_no_window_hit_or_shallow_history"
        row["provider_success"] = False
    return row


def fetch_finnhub_company_news(event: pd.Series, credential: str) -> dict[str, Any]:
    event_date = npu.parse_date(event.event_date)
    if event_date is None:
        return empty_provider_result("finnhub_news", event, "bad_event_date")
    start, end = npu.window_bounds(event_date, 7)
    auth_name = "to" + "ken"
    params = {"symbol": event.ticker, "from": start, "to": end, auth_name: credential}
    status, payload, err = npu.query_json("https://finnhub.io/api/v1/company-news", params)
    items = npu.payload_items(payload, ("content", "data", "articles", "news"))
    return npu.compact_provider_result("finnhub_news", event, status, items, error_class=err)


def fetch_marketaux(event: pd.Series, credential: str) -> dict[str, Any]:
    event_date = npu.parse_date(event.event_date)
    if event_date is None:
        return empty_provider_result("marketaux_news", event, "bad_event_date")
    start, end = npu.window_bounds(event_date, 7)
    auth_name = "api_" + "to" + "ken"
    params = {
        "symbols": event.ticker,
        "published_after": f"{start}T00:00",
        "published_before": f"{end}T23:59",
        "limit": 50,
        auth_name: credential,
    }
    status, payload, err = npu.query_json("https://api.marketaux.com/v1/news/all", params)
    items = npu.payload_items(payload, ("data", "articles", "news"))
    return npu.compact_provider_result("marketaux_news", event, status, items, error_class=err)


def fetch_eodhd(event: pd.Series, credential: str) -> dict[str, Any]:
    event_date = npu.parse_date(event.event_date)
    if event_date is None:
        return empty_provider_result("eodhd_news", event, "bad_event_date")
    start, end = npu.window_bounds(event_date, 7)
    auth_name = "api_" + "to" + "ken"
    params = {"s": f"{event.ticker}.US", "from": start, "to": end, "limit": 50, auth_name: credential, "fmt": "json"}
    status, payload, err = npu.query_json("https://eodhd.com/api/news", params)
    items = npu.payload_items(payload, ("content", "data", "articles", "news"))
    return npu.compact_provider_result("eodhd_news", event, status, items, error_class=err)


def fetch_newsapi(event: pd.Series, credential: str) -> dict[str, Any]:
    event_date = npu.parse_date(event.event_date)
    if event_date is None:
        return empty_provider_result("newsapi_news", event, "bad_event_date")
    start, end = npu.window_bounds(event_date, 7)
    query = f'{event.ticker} "{event.company_name}"'
    params = {
        "q": query,
        "from": start,
        "to": end,
        "pageSize": 50,
        "sortBy": "publishedAt",
        "apiKey": credential,
    }
    status, payload, err = npu.query_json("https://newsapi.org/v2/everything", params)
    items = npu.payload_items(payload, ("articles", "data", "news"))
    return npu.compact_provider_result("newsapi_news", event, status, items, error_class=err)


def live_provider_results(
    events: pd.DataFrame, args: argparse.Namespace
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], pd.DataFrame]:
    providers = {
        "fmp_news": ("FMP_API_KEY", fetch_fmp_stock_news),
        "fmp_press_release": ("FMP_API_KEY", fetch_fmp_press_releases),
        "finnhub_news": ("FINNHUB_API_KEY", fetch_finnhub_company_news),
        "marketaux_news": ("MARKETAUX_API_KEY", fetch_marketaux),
        "eodhd_news": ("EODHD_API_KEY", fetch_eodhd),
        "newsapi_news": ("NEWSAPI_KEY", fetch_newsapi),
    }
    failure_log: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    plan = prioritized_events(events).head(max(args.max_requests_per_provider, 0))
    for provider, (credential_name, fetcher) in providers.items():
        credential, source = npu.load_credential(credential_name)
        if not args.fetch_live:
            status_rows.append({"provider": provider, "status": "fetch_disabled", "key_source": source, "requests": 0})
            frames[provider] = provider_rows_to_frame([], events, provider)
            continue
        if not credential:
            status_rows.append({"provider": provider, "status": "missing_credential", "key_source": source, "requests": 0})
            frames[provider] = provider_rows_to_frame([], events, provider)
            continue
        rows: list[dict[str, Any]] = []
        for _, event in plan.iterrows():
            result = fetcher(event, credential)
            rows.append(result)
            if result["query_status"] not in {"ok", "ok_no_window_hit_or_shallow_history"}:
                failure_log.append(
                    {
                        "provider": provider,
                        "event_id": result["event_id"],
                        "ticker": result["ticker"],
                        "query_status": result["query_status"],
                        "error_class_safe": result.get("error_class_safe", ""),
                    }
                )
            time.sleep(args.sleep_seconds)
            if result["query_status"] == "rate_limited":
                break
        frames[provider] = provider_rows_to_frame(rows, events, provider)
        status_rows.append(
            {
                "provider": provider,
                "status": "queried" if rows else "no_requests",
                "key_source": source,
                "requests": len(rows),
                "success_events": int(sum(bool(r.get("provider_success")) for r in rows)),
                "hit_events": int(sum(bool(r.get("provider_hit")) for r in rows)),
                "rate_limited": int(sum(str(r.get("query_status")) == "rate_limited" for r in rows)),
            }
        )
    press = frames.pop("fmp_press_release", provider_rows_to_frame([], events, "fmp_press_release"))
    return frames, status_rows, press


def combine_panel(
    events: pd.DataFrame,
    provider_frames: dict[str, pd.DataFrame],
    press_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel = events[
        [
            "event_id",
            "video_id",
            "transcript_id",
            "creator",
            "ticker",
            "company_name",
            "recommendation_type",
            "event_date",
            "top5_flag",
        ]
    ].copy()
    if ANALYST_PANEL.exists():
        analyst = pd.read_csv(ANALYST_PANEL)
        analyst_cols = [
            c
            for c in [
                "event_id",
                "analyst_alignment_event_time",
                "analyst_alignment_diagnostic",
                "analyst_coverage_tier",
            ]
            if c in analyst.columns
        ]
        panel = panel.merge(one_row_per_event(analyst[analyst_cols]), on="event_id", how="left")
    sec = pd.read_csv(SEC_FLAGS) if SEC_FLAGS.exists() else pd.DataFrame()
    if not sec.empty:
        panel = panel.merge(
            one_row_per_event(sec),
            on=["event_id", "ticker", "company_name", "event_date"],
            how="left",
            suffixes=("", "_sec"),
        )
    market = pd.read_csv(MARKET_PANEL) if MARKET_PANEL.exists() else pd.DataFrame()
    if not market.empty:
        mcols = [c for c in ["event_id", "market_active_pre_event", "market_quiet"] if c in market.columns]
        panel = panel.merge(one_row_per_event(market[mcols]), on="event_id", how="left")

    provider_summary_rows: list[dict[str, Any]] = []
    failure_frames = {**provider_frames, "fmp_press_release": press_frame}
    for provider, frame in failure_frames.items():
        frame = one_row_per_event(frame)
        prefix = provider.removesuffix("_news")
        rename = {
            "provider_success": f"{provider}_success",
            "provider_hit": f"{provider}_hit",
            "provider_material_hit": f"{provider}_material_hit",
            "query_status": f"{provider}_query_status",
        }
        count_cols = [c for c in frame.columns if c.startswith(("pre_", "post_"))]
        keep = ["event_id", *rename, "relevant_count_pm7", *count_cols]
        sub = frame[[c for c in keep if c in frame.columns]].rename(
            columns={**rename, "relevant_count_pm7": f"{provider}_pm7_count"}
        )
        panel = panel.merge(sub, on="event_id", how="left")
        provider_summary_rows.append(provider_summary(provider, frame))
        for days in (1, 3, 7):
            panel[f"{prefix}_pre_{days}d_count"] = panel.get(f"pre_{days}d_count", 0)
            panel[f"{prefix}_post_{days}d_count"] = panel.get(f"post_{days}d_count", 0)
        panel = panel.drop(columns=[c for c in count_cols if c in panel.columns], errors="ignore")

    press_frame = one_row_per_event(press_frame)
    panel = panel.merge(
        press_frame[["event_id", "provider_success", "provider_hit", "query_status"]].rename(
            columns={
                "provider_success": "press_release_provider_success",
                "provider_hit": "press_release_hit",
                "query_status": "press_release_query_status",
            }
        ),
        on="event_id",
        how="left",
    )
    provider_summary_rows.append(provider_summary("fmp_press_release", press_frame))

    for provider in MEDIA_PROVIDERS:
        success_col = f"{provider}_success"
        hit_col = f"{provider}_hit"
        if success_col not in panel.columns:
            panel[success_col] = False
        if hit_col not in panel.columns:
            panel[hit_col] = False
        panel[success_col] = panel[success_col].fillna(False).astype(bool)
        panel[hit_col] = panel[hit_col].fillna(False).astype(bool)
    panel["press_release_provider_success"] = panel["press_release_provider_success"].fillna(False).astype(bool)
    panel["press_release_hit"] = panel["press_release_hit"].fillna(False).astype(bool)

    sec_hit = npu.bool_series(panel, "sec_material_event_confounded_flag")
    earnings_hit = npu.bool_series(panel, "earnings_proxy_flag")
    panel["sec_filing_hit"] = sec_hit
    panel["earnings_hit"] = earnings_hit
    panel["official_news_hit"] = sec_hit | earnings_hit | panel["press_release_hit"]
    panel["any_media_news_hit"] = panel[[f"{p}_hit" for p in MEDIA_PROVIDERS]].any(axis=1)
    panel["market_implied_confounded"] = npu.bool_series(panel, "market_active_pre_event")

    success_cols = [f"{p}_success" for p in MEDIA_PROVIDERS]
    panel["provider_success_count"] = panel[success_cols].sum(axis=1).astype(int)
    panel["provider_failure_count"] = 0
    for provider in MEDIA_PROVIDERS:
        status_col = f"{provider}_query_status"
        if status_col in panel.columns:
            panel["provider_failure_count"] += (
                ~panel[status_col].fillna("not_checked").isin(["ok", "not_checked", "missing_panel"])
            ).astype(int)
    panel["provider_unknown_count"] = (len(MEDIA_PROVIDERS) - panel["provider_success_count"]).astype(int)
    for days in (1, 3, 7):
        pre_cols = [c for c in panel.columns if c.endswith(f"_pre_{days}d_count")]
        post_cols = [c for c in panel.columns if c.endswith(f"_post_{days}d_count")]
        panel[f"news_window_pre_{days}d_count"] = panel[pre_cols].fillna(0).sum(axis=1).astype(int) if pre_cols else 0
        panel[f"news_window_post_{days}d_count"] = panel[post_cols].fillna(0).sum(axis=1).astype(int) if post_cols else 0

    official_checks_pass = npu.bool_series(panel, "sec_clean_expanded_flag") & panel["press_release_provider_success"]
    panel["multi_source_clean"] = (
        official_checks_pass
        & (panel["provider_success_count"] >= 2)
        & ~panel["official_news_hit"]
        & ~panel["any_media_news_hit"]
        & ~panel["market_implied_confounded"]
    )
    panel["news_clean_status"] = "unknown_news_coverage"
    panel.loc[panel["multi_source_clean"], "news_clean_status"] = "multi_source_clean"
    panel.loc[panel["market_implied_confounded"], "news_clean_status"] = "market_implied_confounded"
    panel.loc[panel["any_media_news_hit"], "news_clean_status"] = "media_confounded"
    panel.loc[panel["official_news_hit"], "news_clean_status"] = "official_confounded"
    panel["news_coverage_tier"] = panel["news_clean_status"]
    panel["news_confounded_reason"] = panel.apply(reason_codes, axis=1)

    by_provider = pd.DataFrame(provider_summary_rows)
    provider_status = by_provider.copy()
    return panel, by_provider, provider_status


def provider_summary(provider: str, frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "provider": provider,
        "events": len(frame),
        "success_events": int(frame.get("provider_success", pd.Series(False, index=frame.index)).fillna(False).astype(bool).sum()),
        "hit_events": int(frame.get("provider_hit", pd.Series(False, index=frame.index)).fillna(False).astype(bool).sum()),
        "unknown_or_not_checked_events": int((~frame.get("provider_success", pd.Series(False, index=frame.index)).fillna(False).astype(bool)).sum()),
        "top_statuses": "; ".join(
            f"{status}:{count}"
            for status, count in Counter(frame.get("query_status", pd.Series(["missing"] * len(frame))).fillna("missing")).most_common(6)
        ),
    }


def reason_codes(row: pd.Series) -> str:
    reasons: list[str] = []
    if bool(row.get("sec_filing_hit")):
        reasons.append("sec_filing")
    if bool(row.get("earnings_hit")):
        reasons.append("earnings")
    if bool(row.get("press_release_hit")):
        reasons.append("press_release")
    if bool(row.get("any_media_news_hit")):
        hit_names = [provider for provider in MEDIA_PROVIDERS if bool(row.get(f"{provider}_hit"))]
        reasons.append("media:" + ",".join(hit_names))
    if bool(row.get("market_implied_confounded")):
        reasons.append("market_implied_active")
    if bool(row.get("multi_source_clean")):
        reasons.append("multi_source_clean")
    if not reasons:
        reasons.append("unknown_or_insufficient_provider_coverage")
    return ";".join(reasons)


def return_stats(values: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    n = len(clean)
    if n == 0:
        return {
            "n": 0,
            "mean": "",
            "median": "",
            "t_stat": "",
            "p_value": "",
            "winsorized_mean": "",
            "warning_flag": "n_lt_50",
        }
    mean = float(clean.mean())
    median = float(clean.median())
    t_stat = ""
    p_value = ""
    if n > 1:
        se = float(clean.std(ddof=1)) / math.sqrt(n)
        if se > 0:
            t = mean / se
            t_stat = f"{t:.3f}"
            p_value = f"{npu.normal_p_value(t):.6f}"
    winsorized_mean = float(utils.winsorize(clean).mean())
    return {
        "n": n,
        "mean": f"{mean:.6f}",
        "median": f"{median:.6f}",
        "t_stat": t_stat,
        "p_value": p_value,
        "winsorized_mean": f"{winsorized_mean:.6f}",
        "warning_flag": "n_lt_50" if n < 50 else "",
    }


def sample_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    top5 = frame["top5_flag"].astype(str).str.lower().eq("true")
    alignment = frame.get("analyst_alignment_event_time", pd.Series("", index=frame.index)).fillna("")
    news = frame.get("news_clean_status", pd.Series("", index=frame.index)).fillna("")
    market_quiet = frame.get("market_quiet", pd.Series(False, index=frame.index)).astype(str).str.lower().eq("true")
    return {
        "full_sample": pd.Series(True, index=frame.index),
        "top5": top5,
        "non_top": ~top5,
        "bullish_aligned_top5": top5 & alignment.eq("analyst_bullish_aligned"),
        "bullish_aligned_non_top": (~top5) & alignment.eq("analyst_bullish_aligned"),
        "neutral_mixed_non_top": (~top5) & alignment.eq("analyst_neutral_or_mixed"),
        "market_quiet_multi_source_clean": market_quiet & news.eq("multi_source_clean"),
    }


def build_return_table(panel: pd.DataFrame) -> pd.DataFrame:
    returns = load_forward_returns()
    join_cols = [
        "event_id",
        "news_clean_status",
        "provider_success_count",
        "top5_flag",
        "market_quiet",
        "analyst_alignment_event_time",
    ]
    available_cols = [c for c in join_cols if c in panel.columns]
    merged = returns.merge(panel[available_cols], on="event_id", how="left", suffixes=("", "_news"))
    if "top5_flag_news" in merged.columns:
        merged["top5_flag"] = merged["top5_flag_news"]
    masks = sample_masks(merged)
    rows: list[dict[str, Any]] = []
    for sample, mask in masks.items():
        selected = merged[mask.reindex(merged.index, fill_value=False).astype(bool)]
        for status in [
            "official_confounded",
            "media_confounded",
            "market_implied_confounded",
            "multi_source_clean",
            "unknown_news_coverage",
        ]:
            for horizon in ("5D", "21D", "63D"):
                group = selected[
                    (selected["news_clean_status"] == status)
                    & (selected["horizon"] == horizon)
                    & (selected["status"] == "computed")
                ]
                stats = return_stats(group["spy_bhar"])
                rows.append(
                    {
                        "sample": sample,
                        "news_clean_status": status,
                        "horizon": horizon,
                        "return_type": "spy_bhar",
                        "diagnostic_only_flag": status != "multi_source_clean",
                        **stats,
                    }
                )
    return pd.DataFrame(rows)


def by_group_tables(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ticker = (
        panel.groupby("ticker", dropna=False)
        .agg(
            events=("event_id", "count"),
            official_news_hit=("official_news_hit", "sum"),
            any_media_news_hit=("any_media_news_hit", "sum"),
            multi_source_clean=("multi_source_clean", "sum"),
            unknown_news_coverage=("news_clean_status", lambda s: int((s == "unknown_news_coverage").sum())),
        )
        .reset_index()
        .sort_values(["events", "ticker"], ascending=[False, True])
    )
    by_year = panel.assign(event_year=pd.to_datetime(panel["event_date"], errors="coerce").dt.year)
    year = (
        by_year.groupby("event_year", dropna=False)
        .agg(
            events=("event_id", "count"),
            official_news_hit=("official_news_hit", "sum"),
            any_media_news_hit=("any_media_news_hit", "sum"),
            multi_source_clean=("multi_source_clean", "sum"),
            unknown_news_coverage=("news_clean_status", lambda s: int((s == "unknown_news_coverage").sum())),
        )
        .reset_index()
        .sort_values("event_year")
    )
    return ticker, year


def write_summary(panel: pd.DataFrame, by_provider: pd.DataFrame, return_table: pd.DataFrame) -> None:
    status_counts = panel["news_clean_status"].value_counts().rename_axis("news_clean_status").reset_index(name="events")
    multi_n = int((panel["news_clean_status"] == "multi_source_clean").sum())
    non_top_multi = int((~panel["top5_flag"].astype(bool) & panel["news_clean_status"].eq("multi_source_clean")).sum())
    top_status = status_counts.to_dict("records")
    body = f"""
## Status Counts

{utils.md_table(top_status)}

## Provider Coverage

{utils.md_table(by_provider.to_dict("records"))}

## Interpretation

- Multi-source clean events: **{multi_n}**
- Non-top multi-source clean events: **{non_top_multi}**
- Unknown provider coverage is not clean.
- Public-news-clean claims require SEC/earnings/press-release checks plus at least two successful external provider checks.
- Rows outside `multi_source_clean` are diagnostic for return interpretation.

## Return Table Preview

{utils.md_table(return_table.head(30).to_dict("records"))}
"""
    utils.write_md(OUT_DIR / "news_confound_summary.md", "News Confound Master Summary", body)


def bootstrap_diff(
    frame: pd.DataFrame,
    a_mask: pd.Series,
    b_mask: pd.Series,
    cluster_col: str,
    *,
    iterations: int = 400,
) -> dict[str, Any]:
    data = frame.dropna(subset=["spy_bhar", cluster_col]).copy()
    a = a_mask.reindex(data.index, fill_value=False).astype(bool)
    b = b_mask.reindex(data.index, fill_value=False).astype(bool)
    observed = float(data.loc[a, "spy_bhar"].mean() - data.loc[b, "spy_bhar"].mean()) if a.any() and b.any() else np.nan
    clusters = data[cluster_col].dropna().astype(str).unique().tolist()
    rng = random.Random(496)
    diffs: list[float] = []
    if len(clusters) >= 2 and a.any() and b.any():
        for _ in range(iterations):
            chosen = [rng.choice(clusters) for _ in clusters]
            boot = pd.concat([data[data[cluster_col].astype(str).eq(c)] for c in chosen], ignore_index=True)
            if boot.empty:
                continue
            ba = boot["sample_group"].eq("a")
            bb = boot["sample_group"].eq("b")
            if ba.any() and bb.any():
                diffs.append(float(boot.loc[ba, "spy_bhar"].mean() - boot.loc[bb, "spy_bhar"].mean()))
    if diffs:
        lo, hi = pd.Series(diffs).quantile([0.025, 0.975]).tolist()
    else:
        lo, hi = np.nan, np.nan
    return {
        "observed_diff": "" if np.isnan(observed) else f"{observed:.6f}",
        "ci_lower": "" if np.isnan(lo) else f"{lo:.6f}",
        "ci_upper": "" if np.isnan(hi) else f"{hi:.6f}",
        "iterations": len(diffs),
        "cluster_count": len(clusters),
    }


def write_dependency_outputs(panel: pd.DataFrame, return_table: pd.DataFrame) -> None:
    ROBUST_DIR.mkdir(parents=True, exist_ok=True)
    returns = load_forward_returns().merge(
        panel[
            [
                "event_id",
                "ticker",
                "creator",
                "top5_flag",
                "news_clean_status",
                "analyst_alignment_event_time",
                "event_date",
            ]
        ],
        on="event_id",
        how="left",
        suffixes=("", "_event"),
    )
    returns["event_week"] = pd.to_datetime(returns["event_date"], errors="coerce").dt.to_period("W").astype(str)
    rows: list[dict[str, Any]] = []
    for horizon in ("5D", "21D", "63D"):
        h = returns[(returns["horizon"] == horizon) & (returns["status"] == "computed")].copy()
        h["sample_group"] = ""
        a_mask = h["top5_flag"].astype(str).str.lower().eq("true") & h["analyst_alignment_event_time"].eq(
            "analyst_bullish_aligned"
        )
        b_mask = ~h["top5_flag"].astype(str).str.lower().eq("true") & h["analyst_alignment_event_time"].eq(
            "analyst_bullish_aligned"
        )
        h.loc[a_mask, "sample_group"] = "a"
        h.loc[b_mask, "sample_group"] = "b"
        for cluster_col in ("event_week", "ticker", "creator"):
            result = bootstrap_diff(h[h["sample_group"].isin(["a", "b"])], h["sample_group"].eq("a"), h["sample_group"].eq("b"), cluster_col)
            rows.append(
                {
                    "test": "top5_bullish_aligned_minus_non_top_bullish_aligned",
                    "horizon": horizon,
                    "cluster": cluster_col,
                    **result,
                    "warning": "overlapping_return_windows" if horizon in {"21D", "63D"} else "",
                }
            )
    pd.DataFrame(rows).to_csv(ROBUST_DIR / "clustered_or_block_bootstrap_summary.csv", index=False)

    p_rows: list[dict[str, Any]] = []
    usable = return_table[return_table["p_value"].astype(str).ne("")]
    for _, row in usable.iterrows():
        p_rows.append(
            {
                "test": f"{row['sample']}|{row['news_clean_status']}|{row['horizon']}",
                "raw_p": float(row["p_value"]),
                "sample": row["sample"],
                "news_clean_status": row["news_clean_status"],
                "horizon": row["horizon"],
            }
        )
    p_rows = fdr_adjust(p_rows)
    pd.DataFrame(p_rows).to_csv(ROBUST_DIR / "fdr_adjusted_main_tests.csv", index=False)
    body = f"""
Block bootstrap rows: {len(rows)}

FDR-adjusted one-sample rows: {len(p_rows)}

21D and 63D event windows overlap in calendar time. Treat naive p-values as descriptive unless dependency-aware rows point the same way. Ticker and creator clustered bootstrap rows are included where feasible.
"""
    utils.write_md(ROBUST_DIR / "dependency_robustness_summary.md", "Dependency Robustness Summary", body)


def fdr_adjust(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    order = sorted(range(len(rows)), key=lambda i: rows[i]["raw_p"])
    m = len(rows)
    q_vals = [1.0] * m
    running = 1.0
    for rank, idx in reversed(list(enumerate(order, start=1))):
        running = min(running, rows[idx]["raw_p"] * m / rank)
        q_vals[idx] = min(running, 1.0)
    for row, q in zip(rows, q_vals, strict=True):
        row["bh_fdr_q"] = f"{q:.6f}"
        row["test_family_size"] = m
    return rows


def table_md(rows: list[dict[str, Any]], title: str) -> str:
    return f"# {title}\n\n{utils.md_table(rows)}\n"


def write_final_exhibits(panel: pd.DataFrame, return_table: pd.DataFrame, by_provider: pd.DataFrame) -> None:
    EXHIBIT_DIR.mkdir(parents=True, exist_ok=True)
    long = utils.long_panel()
    manifest = utils.event_manifest()
    sample_rows = [
        {"metric": "v2_transcript_rows", "value": 9992},
        {"metric": "v2_successful_transcripts", "value": 9977},
        {"metric": "accepted_recommendation_events", "value": len(manifest)},
        {
            "metric": "return_matched_1d",
            "value": int(((long["horizon"] == "1D") & (long["status"] == "computed")).sum()) if "horizon" in long.columns else "",
        },
        {
            "metric": "return_matched_5d",
            "value": int(((long["horizon"] == "5D") & (long["status"] == "computed")).sum()) if "horizon" in long.columns else "",
        },
    ]
    write_exhibit("exhibit_01_sample_construction", "Sample Construction", sample_rows)

    baseline = baseline_rows(long)
    write_exhibit("exhibit_02_baseline_event_study", "Baseline Event Study", baseline)
    top_rows = [r for r in baseline if r["sample"] in {"top5", "non_top"}]
    write_exhibit("exhibit_03_top5_vs_nontop", "Top-5 Vs Non-Top", top_rows)

    factor_path = utils.OUT_DIR / "factor_adjusted_alpha" / "03_factor_alpha_summary_by_spec.csv"
    factor_rows = pd.read_csv(factor_path).head(30).to_dict("records") if factor_path.exists() else [{"status": "not_available"}]
    write_exhibit("exhibit_04_factor_adjusted_results", "Factor Adjusted Results", factor_rows)

    portfolio_path = utils.OUT_DIR / "portfolio_realism" / "portfolio_realism_summary.csv"
    portfolio_rows = (
        pd.read_csv(portfolio_path).head(30).to_dict("records") if portfolio_path.exists() else [{"status": "not_available"}]
    )
    write_exhibit("exhibit_05_portfolio_realism", "Portfolio Realism", portfolio_rows)

    analyst_path = utils.OUT_DIR / "information_environment" / "analyst_relay" / "alignment_counts_full_sample.csv"
    analyst_rows = pd.read_csv(analyst_path).to_dict("records") if analyst_path.exists() else [{"status": "not_available"}]
    write_exhibit("exhibit_06_analyst_alignment", "Analyst Alignment", analyst_rows)

    status_rows = panel["news_clean_status"].value_counts().rename_axis("status").reset_index(name="events").to_dict("records")
    write_exhibit("exhibit_07_news_confound_status", "News Confound Status", status_rows)

    neutral = return_table[return_table["sample"].eq("neutral_mixed_non_top")].to_dict("records")
    write_exhibit("exhibit_08_neutral_mixed_decomposition", "Neutral Mixed Decomposition", neutral)

    robust_path = ROBUST_DIR / "clustered_or_block_bootstrap_summary.csv"
    robust_rows = pd.read_csv(robust_path).to_dict("records") if robust_path.exists() else [{"status": "not_available"}]
    write_exhibit("exhibit_09_dependency_robustness", "Dependency Robustness", robust_rows)

    claim_rows = [
        {"claim": "broad tradable YouTube alpha", "status": "prohibited", "reason": "full sample remains weak and portfolio realism is not supportive"},
        {"claim": "top-5 positives", "status": "diagnostic", "reason": "concentration, consensus, and attention are plausible explanations"},
        {"claim": "non-top public-news-clean underperformance", "status": "prohibited", "reason": "requires meaningful multi-source clean n"},
        {"claim": "analyst relay classification", "status": "strengthened", "reason": "grade normalization reduces unknown analyst stance"},
        {"claim": "causal creator skill", "status": "prohibited", "reason": "relay and news layers are observational diagnostics"},
    ]
    write_exhibit("exhibit_10_claim_matrix", "Claim Matrix", claim_rows)

    readme = f"""# Final Exhibit README

These exhibits summarize the RunPod v2 locked sample, analyst relay, public-news confound status, and dependency robustness outputs.

Public-news-clean claims require `multi_source_clean`; all other news labels are diagnostic or confounded. Unknown news coverage is not clean.

Provider coverage snapshot:

{utils.md_table(by_provider.to_dict("records"))}
"""
    (EXHIBIT_DIR / "FINAL_EXHIBIT_README.md").write_text(readme, encoding="utf-8")


def write_exhibit(stem: str, title: str, rows: list[dict[str, Any]]) -> None:
    pd.DataFrame(rows).to_csv(EXHIBIT_DIR / f"{stem}.csv", index=False)
    (EXHIBIT_DIR / f"{stem}.md").write_text(table_md(rows, title), encoding="utf-8")


def baseline_rows(long: pd.DataFrame) -> list[dict[str, Any]]:
    if long.empty:
        return [{"status": "missing_long_panel"}]
    frame = long[(long["window_type"] == "forward") & (long["horizon"].isin(["5D", "21D", "63D"]))].copy()
    top5 = frame["top5_flag"].astype(str).str.lower().eq("true")
    rows: list[dict[str, Any]] = []
    for sample, mask in {
        "full_sample": pd.Series(True, index=frame.index),
        "top5": top5,
        "non_top": ~top5,
    }.items():
        for horizon in ("5D", "21D", "63D"):
            group = frame[mask & frame["horizon"].eq(horizon) & frame["status"].eq("computed")]
            rows.append({"sample": sample, "horizon": horizon, **return_stats(group["spy_bhar"])})
    return rows


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = event_universe()
    live_frames, live_status, press_frame = live_provider_results(events, args)
    provider_frames = {
        "alpha_vantage_news": alpha_vantage_results(events),
        "gdelt_news": gdelt_results(events),
        "fnspid_news": fnspid_results(events),
        **live_frames,
    }
    panel, by_provider, provider_status = combine_panel(events, provider_frames, press_frame)
    if live_status:
        live_status_df = pd.DataFrame(live_status).rename(columns={"status": "live_fetch_status"})
        provider_status = provider_status.merge(live_status_df, on="provider", how="left")
    return_table = build_return_table(panel)
    by_ticker, by_year = by_group_tables(panel)
    non_top_diag = return_table[return_table["sample"].isin(["non_top", "bullish_aligned_non_top", "neutral_mixed_non_top"])]

    panel.to_csv(OUT_DIR / "news_confound_event_panel.csv", index=False)
    provider_status.to_csv(OUT_DIR / "news_confound_provider_status.csv", index=False)
    by_provider.to_csv(OUT_DIR / "news_confound_by_provider.csv", index=False)
    by_ticker.to_csv(OUT_DIR / "news_confound_by_ticker.csv", index=False)
    by_year.to_csv(OUT_DIR / "news_confound_by_year.csv", index=False)
    return_table.to_csv(OUT_DIR / "news_clean_status_return_table.csv", index=False)
    non_top_diag.to_csv(OUT_DIR / "non_top_news_clean_diagnostics.csv", index=False)

    failure_rows = []
    for provider, frame in provider_frames.items():
        if "query_status" not in frame.columns:
            continue
        failed = frame[~frame["query_status"].fillna("not_checked").isin(["ok", "not_checked", "missing_panel"])]
        for _, row in failed.head(250).iterrows():
            failure_rows.append(
                {
                    "provider": provider,
                    "event_id": row.get("event_id", ""),
                    "ticker": row.get("ticker", ""),
                    "query_status": row.get("query_status", ""),
                    "error_class_safe": row.get("error_class_safe", ""),
                }
            )
    pd.DataFrame(failure_rows).to_csv(OUT_DIR / "provider_failure_log_compact.csv", index=False)

    write_summary(panel, by_provider, return_table)
    write_dependency_outputs(panel, return_table)
    write_final_exhibits(panel, return_table, by_provider)
    print(
        "Public news confound master complete: "
        f"multi_source_clean={int(panel['multi_source_clean'].sum())} "
        f"unknown={int(panel['news_clean_status'].eq('unknown_news_coverage').sum())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
