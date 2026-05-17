"""Event-time analyst relay: FMP → Finnhub → yfinance diagnostic fallback."""

from __future__ import annotations

import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_long_horizon_returns as lh  # noqa: E402
import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = ie.info_dir("analyst_relay")
REQUEST_LOG = OUT / "analyst_relay_provider_request_log_safe.csv"
REVISION_DAYS = 90
BROADER_DAYS = 180
FMP_PAUSE = 0.5
FMP_RETRY_PAUSE = 5.0


def http_json_retry(url: str) -> tuple[Any | None, str]:
    data, status = ie.http_json(url)
    if status in {"http_429", "http_403", "http_402"}:
        time.sleep(FMP_RETRY_PAUSE)
        data, status = ie.http_json(url)
    return data, status
FH_PAUSE = 0.25
YF_PAUSE = 0.15
UPSIDE_BULL = 0.05
UPSIDE_BEAR = -0.05

BUY_RECS = {"buy", "strong_buy", "accumulate", "long", "bullish", "outperform"}
SELL_RECS = {"sell", "short", "avoid", "bearish", "underperform", "trim"}


def finfluencer_direction(rec_type: Any) -> str:
    r = str(rec_type or "").lower().replace(" ", "_")
    if r in BUY_RECS or "buy" in r:
        return "bullish"
    if r in SELL_RECS or "sell" in r or "short" in r:
        return "bearish"
    return "neutral"


def analyst_stance_from_counts(buy: int, sell: int, hold: int) -> str:
    total = buy + sell + hold
    if total == 0:
        return "unknown"
    if buy >= max(sell, hold) and buy >= sell * 2:
        return "bullish"
    if sell >= max(buy, hold) and sell >= buy * 2:
        return "bearish"
    return "neutral"


def analyst_stance_from_rating(score: float | None, upside: float | None) -> str:
    if upside is not None:
        if upside >= UPSIDE_BULL:
            return "bullish"
        if upside <= UPSIDE_BEAR:
            return "bearish"
    if score is not None:
        if score >= 4:
            return "bullish"
        if score <= 2:
            return "bearish"
    return "neutral"


def log_request(rows: list[dict[str, Any]], ticker: str, provider: str, endpoint: str, status: str, err: str = "") -> None:
    rows.append(
        {
            "ticker": ticker,
            "provider": provider,
            "endpoint": endpoint,
            "status": status,
            "error_class_safe": (err or "")[:80],
            "ts_utc": pd.Timestamp.now("UTC").isoformat(),
        }
    )


def fetch_fmp_ticker(ticker: str, key: str, log: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    hist: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "fmp_provider_status": "skipped",
        "fmp_has_event_time_data": False,
        "fmp_latest_only": False,
        "fmp_error_class_safe": "",
    }
    endpoints = [
        ("ratings-historical", "ratings-historical"),
        ("grades", "grades"),
        ("upgrades-downgrades", "upgrades-downgrades"),
        ("price-target-summary", "price-target-summary"),
    ]
    any_ok = False
    snapshot_targets: list[dict[str, Any]] = []
    for name, path in endpoints:
        q = urllib.parse.urlencode({"symbol": ticker, "apikey": key})
        url = f"https://financialmodelingprep.com/stable/{path}?{q}"
        data, status = http_json_retry(url)
        log_request(log, ticker, "FMP", name, status, status if status != "ok" else "")
        if status != "ok":
            meta["fmp_error_class_safe"] = status
            time.sleep(FMP_PAUSE)
            continue
        any_ok = True
        if name in {"historical-rating", "ratings-historical"} and isinstance(data, list):
            for item in data:
                d = ie.parse_iso_date(item.get("date"))
                if not d:
                    continue
                hist.append(
                    {
                        "ticker": ticker,
                        "record_date": d.isoformat(),
                        "source": "fmp_historical_rating",
                        "rating_score": item.get("ratingScore"),
                        "buy_count": 0,
                        "sell_count": 0,
                        "hold_count": 0,
                        "rating_bucket": str(item.get("rating", ""))[:40],
                    }
                )
        elif name in {"grade", "grades"} and isinstance(data, list):
            for item in data:
                d = ie.parse_iso_date(item.get("date"))
                if not d:
                    continue
                act = str(item.get("action", "")).lower()
                ng = str(item.get("newGrade", "")).lower()
                hist.append(
                    {
                        "ticker": ticker,
                        "record_date": d.isoformat(),
                        "source": "fmp_grade",
                        "grade_action": f"{item.get('newGrade','')} ({item.get('action','')})"[:80],
                        "rating_bucket": str(item.get("newGrade", ""))[:40],
                        "buy_count": int(
                            act == "upgrade" or any(x in ng for x in ["buy", "outperform", "overweight", "strong buy"])
                        ),
                        "sell_count": int(
                            act == "downgrade"
                            or any(x in ng for x in ["sell", "underperform", "underweight", "strong sell"])
                        ),
                        "hold_count": int("hold" in ng or "neutral" in ng or act in {"maintain", "hold"}),
                        "recent_upgrade": act == "upgrade",
                        "recent_downgrade": act == "downgrade",
                    }
                )
        elif name == "upgrades-downgrades" and isinstance(data, list):
            for item in data:
                d = ie.parse_iso_date(item.get("publishedDate") or item.get("date"))
                if not d:
                    continue
                grade = str(item.get("newGrade", "")).lower()
                hist.append(
                    {
                        "ticker": ticker,
                        "record_date": d.isoformat(),
                        "source": "fmp_upgrades_downgrades",
                        "buy_count": 1 if "buy" in grade or "outperform" in grade else 0,
                        "sell_count": 1 if "sell" in grade or "under" in grade else 0,
                        "hold_count": 1 if "hold" in grade or "neutral" in grade else 0,
                        "rating_bucket": str(item.get("newGrade", ""))[:40],
                    }
                )
        elif name == "price-target-summary" and isinstance(data, list) and data:
            row = data[0]
            snapshot_targets.append(
                {
                    "target_mean": row.get("lastMonthAvgPriceTarget") or row.get("allTimeAvgPriceTarget"),
                    "target_median": row.get("lastMonthAvgPriceTarget"),
                    "target_high": row.get("lastMonthHighPriceTarget"),
                    "target_low": row.get("lastMonthLowPriceTarget"),
                    "as_of": row.get("publishDate") or row.get("lastUpdated"),
                }
            )
        time.sleep(FMP_PAUSE)

    q = urllib.parse.urlencode({"symbol": ticker, "apikey": key})
    url = f"https://financialmodelingprep.com/stable/price-target-consensus?{q}"
    data, status = http_json_retry(url)
    log_request(log, ticker, "FMP", "price-target-consensus", status, status if status != "ok" else "")
    if status == "ok":
        any_ok = True
        row = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else {}
        snapshot_targets.append(
            {
                "target_mean": row.get("targetConsensus"),
                "target_median": row.get("targetMedian"),
                "target_high": row.get("targetHigh"),
                "target_low": row.get("targetLow"),
            }
        )
    time.sleep(FMP_PAUSE)

    meta["fmp_provider_status"] = "ok" if any_ok else meta.get("fmp_provider_status", "no_data")
    if hist:
        meta["fmp_has_event_time_data"] = True
    if snapshot_targets and not hist:
        meta["fmp_latest_only"] = True
    meta["fmp_snapshots"] = snapshot_targets
    return hist, meta


def fetch_finnhub_ticker(ticker: str, key: str, log: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    hist: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "finnhub_provider_status": "skipped",
        "finnhub_has_event_time_data": False,
        "finnhub_latest_only": False,
        "finnhub_error_class_safe": "",
    }
    q = urllib.parse.urlencode({"symbol": ticker, "token": key})
    url = f"https://finnhub.io/api/v1/stock/recommendation?{q}"
    data, status = ie.http_json(url)
    log_request(log, ticker, "Finnhub", "stock/recommendation", status, status if status != "ok" else "")
    if status == "ok" and isinstance(data, list):
        meta["finnhub_provider_status"] = "ok"
        for item in data:
            d = ie.parse_iso_date(item.get("period"))
            if not d:
                continue
            sb = int(item.get("strongBuy", 0) or 0)
            b = int(item.get("buy", 0) or 0)
            h = int(item.get("hold", 0) or 0)
            s = int(item.get("sell", 0) or 0)
            ss = int(item.get("strongSell", 0) or 0)
            hist.append(
                {
                    "ticker": ticker,
                    "record_date": d.isoformat(),
                    "source": "finnhub_recommendation",
                    "buy_count": sb + b,
                    "sell_count": ss + s,
                    "hold_count": h,
                    "strong_buy": sb,
                    "strong_sell": ss,
                }
            )
        meta["finnhub_has_event_time_data"] = bool(hist)
    else:
        meta["finnhub_error_class_safe"] = status
    time.sleep(FH_PAUSE)

    url2 = f"https://finnhub.io/api/v1/stock/price-target?{q}"
    data2, status2 = ie.http_json(url2)
    log_request(log, ticker, "Finnhub", "stock/price-target", status2, status2 if status2 != "ok" else "")
    if status2 == "ok" and isinstance(data2, dict):
        meta["finnhub_price_target"] = {
            "target_high": data2.get("targetHigh"),
            "target_low": data2.get("targetLow"),
            "target_mean": data2.get("targetMean"),
            "target_median": data2.get("targetMedian"),
            "last_updated": data2.get("lastUpdated"),
        }
        if not hist:
            meta["finnhub_latest_only"] = True
    time.sleep(FH_PAUSE)
    return hist, meta


def fetch_yfinance_ticker(ticker: str, log: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    hist: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "yfinance_provider_status": "skipped",
        "yfinance_has_data": False,
        "yfinance_latest_only": True,
        "diagnostic_yfinance_fallback": True,
        "yf_error_class_safe": "",
        "yf_has_event_time_data": False,
    }
    try:
        import yfinance as yf
    except ImportError:
        meta["yfinance_provider_status"] = "missing_package"
        meta["yf_error_class_safe"] = "import_error"
        log_request(log, ticker, "yfinance", "import", "missing_package", "import_error")
        return hist, meta

    try:
        t = yf.Ticker(ticker)
        info = getattr(t, "fast_info", None) or {}
        if not info:
            info = {}
        try:
            full_info = t.info or {}
        except Exception:
            full_info = {}
        meta["yfinance_provider_status"] = "ok"
        meta["yfinance_has_data"] = True
        meta["yf_recommendation_key"] = str(full_info.get("recommendationKey", ""))[:40]
        meta["yf_recommendation_mean"] = full_info.get("recommendationMean")
        meta["yf_number_of_analysts"] = full_info.get("numberOfAnalystOpinions")
        meta["yf_target_mean"] = full_info.get("targetMeanPrice")
        meta["yf_target_median"] = full_info.get("targetMedianPrice")
        meta["yf_target_high"] = full_info.get("targetHighPrice")
        meta["yf_target_low"] = full_info.get("targetLowPrice")
        meta["yf_reference_price"] = full_info.get("currentPrice") or full_info.get("regularMarketPrice")
        log_request(log, ticker, "yfinance", "info", "ok", "")

        for attr in ("recommendations", "upgrades_downgrades"):
            try:
                frame = getattr(t, attr, None)
                if frame is None or (hasattr(frame, "empty") and frame.empty):
                    continue
                df = frame.reset_index() if hasattr(frame, "reset_index") else pd.DataFrame(frame)
                date_col = next((c for c in df.columns if "date" in str(c).lower()), df.columns[0])
                for _, row in df.iterrows():
                    d = ie.parse_iso_date(row.get(date_col))
                    if not d:
                        continue
                rowd = {str(k).lower(): v for k, v in row.items()}
                to_grade = str(rowd.get("to grade", rowd.get("grade", ""))).lower()
                hist.append(
                    {
                        "ticker": ticker,
                        "record_date": d.isoformat(),
                        "source": f"yfinance_{attr}",
                        "rating_bucket": to_grade[:80],
                        "buy_count": int(any(x in to_grade for x in ["buy", "outperform", "overweight"])),
                        "sell_count": int(any(x in to_grade for x in ["sell", "underperform", "underweight"])),
                        "hold_count": int("hold" in to_grade or "neutral" in to_grade),
                    }
                )
                meta["yf_has_event_time_data"] = bool(hist)
                if hist:
                    meta["yfinance_latest_only"] = False
            except Exception as exc:
                log_request(log, ticker, "yfinance", attr, "error", type(exc).__name__)
        log_request(log, ticker, "yfinance", "ticker", "ok", "")
    except Exception as exc:
        meta["yfinance_provider_status"] = "error"
        meta["yf_error_class_safe"] = type(exc).__name__
        log_request(log, ticker, "yfinance", "ticker", "error", type(exc).__name__)
    time.sleep(YF_PAUSE)
    return hist, meta


def pre_event_price(ticker: str, event_date: Any, frames: dict) -> float | None:
    ed = ie.parse_iso_date(event_date)
    frame = frames.get(ticker)
    if ed is None or frame is None:
        return None
    idx = lh.first_idx(frame, ed)
    if idx is None:
        return None
    return lh.clean_float(frame.iloc[idx].get("adjusted_close"))


def enrich_history(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for i, row in out.iterrows():
        src = str(row.get("source", ""))
        if src == "fmp_grade":
            g = str(row.get("grade_action", row.get("rating_bucket", ""))).lower()
            if int(row.get("buy_count", 0) or 0) == 0 and int(row.get("sell_count", 0) or 0) == 0:
                out.at[i, "buy_count"] = int(
                    row.get("recent_upgrade") or any(x in g for x in ["buy", "outperform", "overweight", "strong buy"])
                )
                out.at[i, "sell_count"] = int(
                    row.get("recent_downgrade")
                    or any(x in g for x in ["sell", "underperform", "underweight", "strong sell"])
                )
        if "yfinance" in src:
            g = str(row.get("rating_bucket", "")).lower()
            if int(row.get("buy_count", 0) or 0) == 0 and int(row.get("sell_count", 0) or 0) == 0:
                out.at[i, "buy_count"] = int(any(x in g for x in ["strong buy", " buy", "outperform", "overweight"]))
                out.at[i, "sell_count"] = int(any(x in g for x in ["strong sell", " sell", "underperform", "underweight"]))
    return out


def pick_event_time_row(hist: pd.DataFrame, event_date: date) -> tuple[pd.Series | None, bool, bool]:
    """Return latest row on or before event_date; flags upgrade/downgrade in revision window."""
    if hist.empty:
        return None, False, False
    h = hist.copy()
    h["record_date_dt"] = pd.to_datetime(h["record_date"], errors="coerce").dt.date
    pre = h[h["record_date_dt"] <= event_date].sort_values("record_date_dt")
    if pre.empty:
        return None, False, False
    latest = None
    if "source" not in pre.columns:
        latest = pre.iloc[-1]
    else:
        for prefix in ("finnhub", "fmp", "yfinance"):
            sub = pre[pre["source"].astype(str).str.startswith(prefix)]
            if sub.empty:
                continue
            scored = sub[(sub["buy_count"].fillna(0) + sub["sell_count"].fillna(0) + sub["hold_count"].fillna(0)) > 0]
            latest = scored.iloc[-1] if not scored.empty else sub.iloc[-1]
            break
    if latest is None:
        latest = pre.iloc[-1]
    rev_start = event_date - timedelta(days=REVISION_DAYS)
    broad_start = event_date - timedelta(days=BROADER_DAYS)
    window = pre[pre["record_date_dt"] >= rev_start]
    broad = pre[pre["record_date_dt"] >= broad_start]
    up = bool(window.get("recent_upgrade", pd.Series(dtype=bool)).any() or (window.get("buy_count", 0) > 0).any())
    down = bool(
        window.get("recent_downgrade", pd.Series(dtype=bool)).any() or (window.get("sell_count", 0) > 0).any()
    )
    _ = broad  # broader window reserved for future use
    return latest, up, down


def build_event_classification(
    ev: pd.Series,
    hist: pd.DataFrame,
    fmp_meta: dict[str, Any],
    fh_meta: dict[str, Any],
    yf_meta: dict[str, Any],
    pre_price: float | None,
) -> dict[str, Any]:
    ed = ie.parse_iso_date(ev.get("event_date"))
    fin_dir = finfluencer_direction(ev.get("recommendation_type"))
    out: dict[str, Any] = {
        "finfluencer_direction": fin_dir,
        "fmp_provider_status": fmp_meta.get("fmp_provider_status", "skipped"),
        "fmp_has_event_time_data": bool(fmp_meta.get("fmp_has_event_time_data")),
        "fmp_latest_only": bool(fmp_meta.get("fmp_latest_only")),
        "fmp_error_class_safe": fmp_meta.get("fmp_error_class_safe", ""),
        "finnhub_provider_status": fh_meta.get("finnhub_provider_status", "skipped"),
        "finnhub_has_event_time_data": bool(fh_meta.get("finnhub_has_event_time_data")),
        "finnhub_latest_only": bool(fh_meta.get("finnhub_latest_only")),
        "finnhub_error_class_safe": fh_meta.get("finnhub_error_class_safe", ""),
        "yfinance_provider_status": yf_meta.get("yfinance_provider_status", "skipped"),
        "yfinance_has_data": bool(yf_meta.get("yfinance_has_data")),
        "yfinance_latest_only": bool(yf_meta.get("yfinance_latest_only", True)),
        "diagnostic_yfinance_fallback": False,
        "yf_error_class_safe": yf_meta.get("yf_error_class_safe", ""),
        "yf_has_event_time_data": bool(yf_meta.get("yf_has_event_time_data")),
        "analyst_bullish_aligned": False,
        "analyst_bearish_aligned": False,
        "analyst_neutral_or_mixed": False,
        "finfluencer_contrarian_to_analyst": False,
        "recent_analyst_upgrade_relay": False,
        "recent_analyst_downgrade_relay": False,
        "analyst_relay_likely": False,
        "analyst_unknown": True,
        "analyst_event_time_usable": False,
        "diagnostic_current_only": False,
        "analyst_alignment": "analyst_unknown",
        "analyst_data_mode": "analyst_unknown",
        "primary_analyst_source": "",
    }

    for k in (
        "yf_recommendation_key",
        "yf_recommendation_mean",
        "yf_number_of_analysts",
        "yf_target_mean",
        "yf_target_median",
        "yf_target_high",
        "yf_target_low",
    ):
        if k in yf_meta:
            out[k] = yf_meta.get(k)

    if ed is None:
        return out

    latest, up_rev, down_rev = pick_event_time_row(hist, ed)
    analyst_stance = "unknown"
    target_upside = None

    if latest is not None:
        src = str(latest.get("source", ""))
        out["primary_analyst_source"] = src
        out["analyst_data_mode"] = "event_time_historical"
        if src.startswith("yfinance"):
            out["diagnostic_yfinance_fallback"] = True
        buy = int(latest.get("buy_count", 0) or 0)
        sell = int(latest.get("sell_count", 0) or 0)
        hold = int(latest.get("hold_count", 0) or 0)
        if latest.get("recent_upgrade") or latest.get("buy_count") == 1 and "fmp_grade" in src:
            buy = max(buy, 1)
        if latest.get("recent_downgrade") or latest.get("sell_count") == 1 and "fmp_grade" in src:
            sell = max(sell, 1)
        score = latest.get("rating_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        analyst_stance = analyst_stance_from_counts(buy, sell, hold)
        if analyst_stance == "neutral" and score_f is not None:
            analyst_stance = analyst_stance_from_rating(score_f, None)
        if analyst_stance == "unknown" and src.startswith(("fmp", "finnhub")):
            out["analyst_unknown"] = True
            out["analyst_event_time_usable"] = True
            out["analyst_alignment"] = "analyst_unknown"
        elif analyst_stance == "unknown":
            out["analyst_unknown"] = True
            out["analyst_event_time_usable"] = False
            out["analyst_alignment"] = "analyst_unknown"
        else:
            out["analyst_unknown"] = False
            out["analyst_event_time_usable"] = not out["diagnostic_yfinance_fallback"]
        out["fmp_rating_date"] = latest.get("record_date") if "fmp" in src else ""
        out["finnhub_period_date"] = latest.get("record_date") if "finnhub" in src else ""
        out["recent_analyst_upgrade_relay"] = up_rev
        out["recent_analyst_downgrade_relay"] = down_rev
    else:
        # diagnostic snapshot chain: FMP then Finnhub then yfinance
        snap = None
        source = ""
        if fmp_meta.get("fmp_snapshots"):
            snap = fmp_meta["fmp_snapshots"][-1]
            source = "fmp_snapshot"
            out["fmp_latest_only"] = True
        elif fh_meta.get("finnhub_price_target"):
            snap = fh_meta["finnhub_price_target"]
            source = "finnhub_snapshot"
            out["finnhub_latest_only"] = True
        elif yf_meta.get("yfinance_has_data"):
            snap = yf_meta
            source = "yfinance_snapshot"
            out["diagnostic_yfinance_fallback"] = True
            out["diagnostic_current_only"] = True
            out["yfinance_latest_only"] = True
            key = str(yf_meta.get("yf_recommendation_key", "")).lower()
            if "buy" in key or "outperform" in key:
                analyst_stance = "bullish"
            elif "sell" in key or "under" in key:
                analyst_stance = "bearish"
            elif key:
                analyst_stance = "neutral"
        if snap:
            out["analyst_data_mode"] = "diagnostic_current_only"
            out["diagnostic_current_only"] = True
            out["primary_analyst_source"] = source
            out["analyst_unknown"] = False
            tm = snap.get("target_mean") or snap.get("target_median") or snap.get("yf_target_mean")
            ref = pre_price or snap.get("yf_reference_price")
            if tm and ref:
                try:
                    target_upside = float(tm) / float(ref) - 1.0
                    out["fmp_target_upside_vs_pre_event_price"] = target_upside
                    out["yf_target_upside_vs_reference_price"] = target_upside
                    analyst_stance = analyst_stance_from_rating(None, target_upside)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass

    if analyst_stance == "bullish":
        out["analyst_bullish_aligned"] = fin_dir == "bullish"
        out["analyst_bearish_aligned"] = False
        out["analyst_neutral_or_mixed"] = fin_dir == "neutral"
        out["analyst_alignment"] = "analyst_bullish_aligned" if fin_dir == "bullish" else "analyst_neutral_or_mixed"
        if fin_dir == "bearish":
            out["finfluencer_contrarian_to_analyst"] = True
            out["analyst_alignment"] = "finfluencer_contrarian_to_analyst"
    elif analyst_stance == "bearish":
        out["analyst_bearish_aligned"] = fin_dir == "bearish"
        out["analyst_alignment"] = "analyst_bearish_aligned" if fin_dir == "bearish" else "analyst_neutral_or_mixed"
        if fin_dir == "bullish":
            out["finfluencer_contrarian_to_analyst"] = True
            out["analyst_alignment"] = "finfluencer_contrarian_to_analyst"
    elif analyst_stance == "neutral" and not out["analyst_unknown"]:
        out["analyst_neutral_or_mixed"] = True
        out["analyst_alignment"] = "analyst_neutral_or_mixed"
    else:
        out["analyst_alignment"] = "analyst_unknown"

    if out["analyst_event_time_usable"] and fin_dir in {"bullish", "bearish"} and analyst_stance in {"bullish", "bearish"}:
        out["analyst_relay_likely"] = (fin_dir == analyst_stance) or out["finfluencer_contrarian_to_analyst"]

    if out["diagnostic_current_only"]:
        out["analyst_alignment"] = "diagnostic_current_only"
        out["analyst_event_time_usable"] = False

    return out


def load_history_cache() -> pd.DataFrame:
    if ie.TICKER_HISTORY_CACHE.exists():
        return pd.read_csv(ie.TICKER_HISTORY_CACHE)
    if ie.COMPACT_CACHE.exists():
        return pd.read_csv(ie.COMPACT_CACHE)
    return pd.DataFrame()


def save_history_cache(df: pd.DataFrame) -> None:
    if not df.empty:
        df.drop_duplicates(subset=["ticker", "record_date", "source"], keep="last").to_csv(
            ie.TICKER_HISTORY_CACHE, index=False
        )


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        utils.write_md(OUT / "analyst_relay_summary.md", "Analyst Relay", "No events.")
        return 0

    fmp_key, fmp_src = ie.load_api_key("FMP_API_KEY")
    fh_key, fh_src = ie.load_api_key("FINNHUB_API_KEY")

    provider_status = [
        {"provider": "FMP", "status": "active" if fmp_key else "skipped_missing_key", "key_source": fmp_src},
        {"provider": "Finnhub", "status": "active" if fh_key else "skipped_missing_key", "key_source": fh_src},
        {"provider": "yfinance", "status": "diagnostic_fallback"},
    ]

    tickers = sorted(events["ticker"].astype(str).str.upper().unique())
    frames = rf.load_market_with_volume()
    request_log: list[dict[str, Any]] = []
    all_hist: list[dict[str, Any]] = []
    ticker_meta: dict[str, dict[str, Any]] = {}

    import os

    reclassify_only = os.environ.get("FIN496_ANALYST_RECLASSIFY_ONLY", "").lower() in ("1", "true")
    use_cache = reclassify_only or os.environ.get("FIN496_USE_ANALYST_CACHE", "").lower() in ("1", "true")
    cached = load_history_cache() if use_cache else pd.DataFrame()
    cached_tickers = set(cached["ticker"].astype(str).unique()) if not cached.empty and "ticker" in cached.columns else set()

    for ticker in tickers:
        fmp_meta: dict[str, Any] = {}
        fh_meta: dict[str, Any] = {}
        yf_meta: dict[str, Any] = {}
        thist: list[dict[str, Any]] = []

        if use_cache and ticker in cached_tickers:
            thist = cached[cached["ticker"] == ticker].to_dict("records")
            fmp_meta["fmp_provider_status"] = "cache"
            fmp_meta["fmp_has_event_time_data"] = bool(thist)
            fh_meta["finnhub_provider_status"] = "cache"
            fh_meta["finnhub_has_event_time_data"] = any("finnhub" in str(r.get("source")) for r in thist)

        if not reclassify_only and not thist and fmp_key:
            h, fmp_meta = fetch_fmp_ticker(ticker, fmp_key, request_log)
            thist.extend(h)

        if not reclassify_only and fh_key:
            h2, fh_meta = fetch_finnhub_ticker(ticker, fh_key, request_log)
            thist.extend(h2)

        if not reclassify_only and not use_cache:
            h3, yf_meta = fetch_yfinance_ticker(ticker, request_log)
            thist.extend(h3)

        all_hist.extend(thist)
        ticker_meta[ticker] = {"fmp": fmp_meta, "finnhub": fh_meta, "yfinance": yf_meta}

    if all_hist:
        save_history_cache(pd.DataFrame(all_hist))

    utils.write_csv(
        REQUEST_LOG,
        request_log,
        ["ticker", "provider", "endpoint", "status", "error_class_safe", "ts_utc"],
    )

    hist_df = enrich_history(pd.DataFrame(all_hist) if all_hist else pd.DataFrame())

    event_rows: list[dict[str, Any]] = []
    for _, ev in events.iterrows():
        ticker = str(ev["ticker"]).upper()
        th = hist_df[hist_df["ticker"] == ticker] if not hist_df.empty else pd.DataFrame()
        meta = ticker_meta.get(ticker, {"fmp": {}, "finnhub": {}, "yfinance": {}})
        px = pre_event_price(ticker, ev["event_date"], frames)
        cls = build_event_classification(ev, th, meta.get("fmp", {}), meta.get("finnhub", {}), meta.get("yfinance", {}), px)
        event_rows.append(
            {
                "event_id": ev["event_id"],
                "ticker": ticker,
                "event_date": ev["event_date"],
                "recommendation_type": ev.get("recommendation_type"),
                "top5_flag": ev.get("top5_flag"),
                "high_confidence": ev.get("high_confidence"),
                **cls,
            }
        )

    panel = pd.DataFrame(event_rows)
    panel.to_csv(OUT / "analyst_relay_event_panel.csv", index=False)

    coverage = []
    for ticker in tickers:
        sub = panel[panel["ticker"] == ticker]
        coverage.append(
            {
                "ticker": ticker,
                "n_events": len(sub),
                "event_time_usable_n": int(sub["analyst_event_time_usable"].sum()),
                "diagnostic_current_n": int(sub["diagnostic_current_only"].sum()),
                "yfinance_fallback_n": int(sub["diagnostic_yfinance_fallback"].sum()),
                "unknown_n": int(sub["analyst_unknown"].sum()),
                "fmp_ok": int((sub["fmp_provider_status"] == "ok").sum()) if "fmp_provider_status" in sub else 0,
            }
        )
    utils.write_csv(OUT / "analyst_relay_ticker_coverage.csv", coverage, list(coverage[0]) if coverage else ["ticker"])

    fwd = utils.forward_panel(["5D", "21D"])
    merged = fwd.merge(panel, on="event_id", how="left", suffixes=("", "_ar"))
    tick_col = "ticker" if "ticker" in merged.columns else "ticker_ar"
    summary_rows: list[dict] = []
    for align in sorted(panel["analyst_alignment"].dropna().unique()):
        m = merged["analyst_alignment"] == align
        for sample, mask in [
            ("full", pd.Series(True, index=merged.index)),
            ("top5", merged[tick_col].isin(utils.TOP5)),
            ("non_top", ~merged[tick_col].isin(utils.TOP5)),
        ]:
            sub = merged.loc[m & mask & (merged["horizon"] == "21D")]
            stats = utils.t_stats(sub["spy_bhar"].dropna().astype(float).tolist())
            summary_rows.append(
                {
                    "sample": sample,
                    "analyst_alignment": align,
                    "horizon": "21D",
                    "n": stats["n"],
                    "mean_spy_bhar": stats["mean"],
                    "t_stat": stats["t_stat"],
                    "p_value": stats["p_value"],
                }
            )
    utils.write_csv(OUT / "returns_by_analyst_alignment.csv", summary_rows, list(summary_rows[0]) if summary_rows else ["sample"])
    utils.write_md(OUT / "returns_by_analyst_alignment.md", "Returns by Analyst Alignment", utils.md_table(summary_rows))

    et_n = int(panel["analyst_event_time_usable"].sum())
    diag_n = int(panel["diagnostic_current_only"].sum())
    yf_n = int(panel["diagnostic_yfinance_fallback"].sum())
    unk_n = int(panel["analyst_unknown"].sum())
    align_bull = int(panel["analyst_bullish_aligned"].sum())
    align_bear = int(panel["analyst_bearish_aligned"].sum())
    contr = int(panel["finfluencer_contrarian_to_analyst"].sum())
    relay = int(panel["analyst_relay_likely"].sum())
    top5_et = int(panel.loc[panel["top5_flag"].astype(bool), "analyst_event_time_usable"].sum())
    nontop_et = int(panel.loc[~panel["top5_flag"].astype(bool), "analyst_event_time_usable"].sum())

    summary = f"""# Analyst relay layer (event-time validation)

## Provider status
{utils.md_table(provider_status)}

## Coverage
| Metric | Count |
| --- | ---: |
| Total events | {len(panel)} |
| Event-time analyst usable | **{et_n}** |
| Diagnostic current-only | **{diag_n}** |
| yfinance diagnostic fallback flagged | **{yf_n}** |
| Analyst unknown | **{unk_n}** |
| Bullish aligned | {align_bull} |
| Bearish aligned | {align_bear} |
| Contrarian to analyst | {contr} |
| Analyst relay likely | {relay} |
| Top-5 event-time usable | {top5_et} |
| Non-top event-time usable | {nontop_et} |

## Interpretation
- **FMP/Finnhub** are primary; **yfinance** is `diagnostic_yfinance_fallback` only — not authoritative historical evidence unless dated pre-event rows exist.
- **Unknown analyst ≠ clean.** Current-only snapshots cannot support event-time causal claims.
- Inspect `returns_by_analyst_alignment.md` for whether aligned vs contrarian buckets differ economically.

### Allowed paper language
- "Partial dated analyst metadata suggests many calls align with observable Wall Street consensus (relay), not independent information."
- "yfinance fills coverage gaps as a diagnostic fallback pending Bloomberg validation."

### Prohibited
- "Results are analyst-news-clean."
- "yfinance proves historical analyst alignment at event time" (unless `analyst_event_time_usable`).
- Causal skill, tradability, or full public-news-clean robustness.
"""
    utils.write_md(OUT / "analyst_relay_summary.md", "Analyst Relay Summary", summary)

    limits = """# Analyst relay limitations

- FMP/Finnhub free tiers may rate-limit; errors are logged in `analyst_relay_provider_request_log_safe.csv` (no raw bodies).
- yfinance is **diagnostic_yfinance_fallback** — gap-filler until Bloomberg exports validate.
- Monthly Finnhub recommendation bins are coarse vs daily upgrades.
- Alignment describes co-movement with observable consensus, not finfluencer skill.
- Unknown analyst coverage must never be coded as clean.
"""
    utils.write_md(OUT / "analyst_relay_limitations.md", "Analyst Relay Limitations", limits)
    print("Analyst relay layer complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
