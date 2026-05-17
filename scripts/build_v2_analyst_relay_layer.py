"""Event-time analyst relay: FMP → Finnhub → yfinance diagnostic fallback."""

from __future__ import annotations

import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_long_horizon_returns as lh  # noqa: E402
import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = ie.info_dir("analyst_relay")
GRADE_AUDIT_OUT = ie.info_dir("analyst_grade_normalization_audit")
YF_DIAG_PANEL = ie.INFO_ENV / "yfinance_analyst_diagnostic" / "yfinance_event_analyst_diagnostic_panel.csv"
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


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if text:
            return text
    return ""


def _stance_to_count_flags(stance: str) -> tuple[int, int, int]:
    return (
        int(stance == "bullish"),
        int(stance == "bearish"),
        int(stance == "neutral"),
    )


def _count_mapping(stance: str, buy: int, sell: int, hold: int) -> dict[str, str]:
    if stance == "unknown":
        return ie.normalize_analyst_grade("", "")
    return {
        "raw_grade": f"provider_counts buy={buy} hold={hold} sell={sell}",
        "normalized_grade": stance,
        "grade_mapping_confidence": "counts",
        "grade_mapping_rule": "provider_count_consensus",
    }


def latest_grade_mapping(latest: pd.Series, stance_from_counts: str, buy: int, sell: int, hold: int) -> dict[str, str]:
    src = str(latest.get("source", ""))
    raw = _first_nonempty(
        latest.get("to_grade"),
        latest.get("rating_bucket"),
        latest.get("grade_action"),
        latest.get("yf_recommendation_key"),
    )
    mapping = ie.normalize_analyst_grade(raw, src)
    if mapping["normalized_grade"] != "unknown":
        return mapping
    if stance_from_counts != "unknown":
        return _count_mapping(stance_from_counts, buy, sell, hold)
    return mapping


def stance_from_alignment_label(alignment: Any, fin_dir: Any) -> str:
    label = str(alignment or "")
    direction = str(fin_dir or "")
    if label == "analyst_bullish_aligned":
        return "bullish"
    if label == "analyst_bearish_aligned":
        return "bearish"
    if label == "analyst_neutral_or_mixed":
        return "neutral"
    if label == "finfluencer_contrarian_to_analyst":
        if direction == "bullish":
            return "bearish"
        if direction == "bearish":
            return "bullish"
    return "unknown"


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
                grade_mapping = ie.normalize_analyst_grade(item.get("newGrade", ""), "fmp")
                buy, sell, hold = _stance_to_count_flags(grade_mapping["normalized_grade"])
                hist.append(
                    {
                        "ticker": ticker,
                        "record_date": d.isoformat(),
                        "source": "fmp_grade",
                        "grade_action": f"{item.get('newGrade','')} ({item.get('action','')})"[:80],
                        "rating_bucket": str(item.get("newGrade", ""))[:40],
                        "buy_count": buy,
                        "sell_count": sell,
                        "hold_count": hold,
                        "recent_upgrade": act == "upgrade",
                        "recent_downgrade": act == "downgrade",
                    }
                )
        elif name == "upgrades-downgrades" and isinstance(data, list):
            for item in data:
                d = ie.parse_iso_date(item.get("publishedDate") or item.get("date"))
                if not d:
                    continue
                grade_mapping = ie.normalize_analyst_grade(item.get("newGrade", ""), "fmp")
                buy, sell, hold = _stance_to_count_flags(grade_mapping["normalized_grade"])
                hist.append(
                    {
                        "ticker": ticker,
                        "record_date": d.isoformat(),
                        "source": "fmp_upgrades_downgrades",
                        "buy_count": buy,
                        "sell_count": sell,
                        "hold_count": hold,
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

        def pick(row: pd.Series, *names: str) -> Any:
            normalized = {str(k).lower().replace(" ", "").replace("_", ""): k for k in row.index}
            for name in names:
                key = name.lower().replace(" ", "").replace("_", "")
                if key in normalized:
                    return row.get(normalized[key])
            return ""

        for attr in ("upgrades_downgrades",):
            try:
                frame = getattr(t, attr, None)
                if frame is None or (hasattr(frame, "empty") and frame.empty):
                    continue
                df = frame.reset_index() if hasattr(frame, "reset_index") else pd.DataFrame(frame)
                date_col = next(
                    (c for c in df.columns if str(c).lower().replace(" ", "") in {"date", "gradedate", "index"}),
                    df.columns[0],
                )
                for _, row in df.iterrows():
                    d = ie.parse_iso_date(row.get(date_col))
                    if not d:
                        continue
                    to_grade = str(pick(row, "ToGrade", "To Grade", "toGrade", "to_grade", "grade"))
                    grade_mapping = ie.normalize_analyst_grade(to_grade, "yfinance")
                    buy, sell, hold = _stance_to_count_flags(grade_mapping["normalized_grade"])
                    hist.append(
                        {
                            "ticker": ticker,
                            "record_date": d.isoformat(),
                            "source": f"yfinance_{attr}",
                            "rating_bucket": to_grade[:80],
                            "buy_count": buy,
                            "sell_count": sell,
                            "hold_count": hold,
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
            if int(row.get("buy_count", 0) or 0) == 0 and int(row.get("sell_count", 0) or 0) == 0:
                mapping = ie.normalize_analyst_grade(_first_nonempty(row.get("rating_bucket"), row.get("grade_action")), src)
                buy, sell, hold = _stance_to_count_flags(mapping["normalized_grade"])
                out.at[i, "buy_count"] = buy
                out.at[i, "sell_count"] = sell
                out.at[i, "hold_count"] = hold
        if "yfinance" in src:
            if int(row.get("buy_count", 0) or 0) == 0 and int(row.get("sell_count", 0) or 0) == 0:
                mapping = ie.normalize_analyst_grade(row.get("rating_bucket", ""), src)
                buy, sell, hold = _stance_to_count_flags(mapping["normalized_grade"])
                out.at[i, "buy_count"] = buy
                out.at[i, "sell_count"] = sell
                out.at[i, "hold_count"] = hold
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
        "raw_latest_grade": "",
        "normalized_latest_grade": "unknown",
        "grade_mapping_confidence": "unknown",
        "grade_mapping_rule": "missing",
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
        count_stance = analyst_stance_from_counts(buy, sell, hold)
        grade_mapping = latest_grade_mapping(latest, count_stance, buy, sell, hold)
        analyst_stance = grade_mapping["normalized_grade"]
        out["raw_latest_grade"] = grade_mapping["raw_grade"]
        out["normalized_latest_grade"] = grade_mapping["normalized_grade"]
        out["grade_mapping_confidence"] = grade_mapping["grade_mapping_confidence"]
        out["grade_mapping_rule"] = grade_mapping["grade_mapping_rule"]
        if analyst_stance == "unknown":
            analyst_stance = count_stance
        if analyst_stance in {"neutral", "unknown"} and score_f is not None:
            analyst_stance = analyst_stance_from_rating(score_f, None)
            out["normalized_latest_grade"] = analyst_stance
            out["grade_mapping_confidence"] = "score"
            out["grade_mapping_rule"] = "rating_score"
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
            grade_mapping = ie.normalize_analyst_grade(yf_meta.get("yf_recommendation_key", ""), "yfinance")
            out["raw_latest_grade"] = grade_mapping["raw_grade"]
            out["normalized_latest_grade"] = grade_mapping["normalized_grade"]
            out["grade_mapping_confidence"] = grade_mapping["grade_mapping_confidence"]
            out["grade_mapping_rule"] = grade_mapping["grade_mapping_rule"]
            analyst_stance = grade_mapping["normalized_grade"]
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
                    if out["normalized_latest_grade"] == "unknown":
                        out["raw_latest_grade"] = f"target_upside={target_upside:.6f}"
                        out["normalized_latest_grade"] = analyst_stance
                        out["grade_mapping_confidence"] = "target_upside"
                        out["grade_mapping_rule"] = "price_target_upside"
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


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].astype(str).str.lower().isin({"true", "1", "yes"})


def merge_yfinance_diagnostic_panel(base: pd.DataFrame, yf: pd.DataFrame) -> pd.DataFrame:
    """Merge yfinance diagnostic panel; FMP/Finnhub event-time fields take priority."""
    grade_cols = {
        "raw_latest_grade": "",
        "normalized_latest_grade": "unknown",
        "grade_mapping_confidence": "unknown",
        "grade_mapping_rule": "missing",
    }
    if yf.empty:
        base = base.copy()
        for col, default in grade_cols.items():
            if col not in base.columns:
                base[col] = default
        et = _bool_col(base, "analyst_event_time_usable")
        diag = _bool_col(base, "diagnostic_current_only")
        base["analyst_event_time_source"] = "none"
        if "primary_analyst_source" in base.columns:
            base.loc[et & base["primary_analyst_source"].astype(str).str.startswith("fmp"), "analyst_event_time_source"] = "fmp"
            base.loc[et & base["primary_analyst_source"].astype(str).str.startswith("finnhub"), "analyst_event_time_source"] = "finnhub"
        base["analyst_diagnostic_source"] = "none"
        base.loc[diag, "analyst_diagnostic_source"] = base.loc[diag, "analyst_event_time_source"]
        base["analyst_any_coverage"] = et | diag
        base["analyst_diagnostic_current_only"] = diag & ~et
        base["analyst_unknown"] = ~(et | base["analyst_diagnostic_current_only"])
        base["analyst_coverage_tier"] = "unknown"
        base.loc[et, "analyst_coverage_tier"] = "event_time_primary_provider"
        base.loc[base["analyst_diagnostic_current_only"], "analyst_coverage_tier"] = "diagnostic_current_snapshot"
        base["analyst_alignment_event_time"] = base["analyst_alignment"] if "analyst_alignment" in base.columns else "analyst_unknown"
        base["analyst_alignment_diagnostic"] = base["analyst_alignment_event_time"]
        base["analyst_alignment_source_used"] = "unknown"
        base.loc[et, "analyst_alignment_source_used"] = "event_time:" + base.loc[et, "analyst_event_time_source"].astype(str)
        base.loc[base["analyst_diagnostic_current_only"], "analyst_alignment_source_used"] = (
            "diagnostic_current:" + base.loc[base["analyst_diagnostic_current_only"], "analyst_diagnostic_source"].astype(str)
        )
        base["analyst_relay_likely_event_time"] = _bool_col(base, "analyst_relay_likely")
        base["analyst_relay_likely_diagnostic"] = base["analyst_relay_likely_event_time"]
        return base

    stale_yf_cols = [c for c in yf.columns if c in base.columns and c != "event_id"]
    m = base.drop(columns=stale_yf_cols, errors="ignore").merge(yf, on="event_id", how="left")

    primary_et = _bool_col(m, "analyst_event_time_usable")
    yf_et = _bool_col(m, "yf_event_time_usable")
    yf_snap = _bool_col(m, "yf_snapshot_available")
    diag_cur = _bool_col(m, "diagnostic_current_only") | (
        yf_snap & ~yf_et & ~primary_et
    )
    for col, default in grade_cols.items():
        if col not in m.columns:
            m[col] = default

    m["analyst_event_time_source"] = "none"
    m.loc[primary_et & m["primary_analyst_source"].astype(str).str.startswith("fmp"), "analyst_event_time_source"] = "fmp"
    m.loc[primary_et & m["primary_analyst_source"].astype(str).str.startswith("finnhub"), "analyst_event_time_source"] = "finnhub"
    primary_yf = primary_et & m["primary_analyst_source"].astype(str).str.startswith("yfinance")
    m.loc[primary_yf, "analyst_event_time_source"] = "yfinance"
    m.loc[~primary_et & yf_et, "analyst_event_time_source"] = "yfinance"
    m.loc[primary_et & ~m["analyst_event_time_source"].isin(["fmp", "finnhub", "yfinance"]), "analyst_event_time_source"] = "fmp"

    m["analyst_diagnostic_source"] = "none"
    m.loc[diag_cur & yf_snap, "analyst_diagnostic_source"] = "yfinance"
    m.loc[diag_cur & ~yf_snap & primary_et, "analyst_diagnostic_source"] = m["analyst_event_time_source"]

    m["analyst_event_time_usable"] = primary_et | yf_et
    m["analyst_diagnostic_current_only"] = diag_cur & ~m["analyst_event_time_usable"]
    m["diagnostic_yfinance_fallback"] = (
        _bool_col(m, "diagnostic_yfinance_fallback") | (yf_snap & m["analyst_diagnostic_current_only"])
    )

    m["analyst_alignment_event_time"] = m.get("analyst_alignment", "analyst_unknown")
    use_yf_et = (~primary_et | primary_yf) & yf_et
    m.loc[use_yf_et & _bool_col(m, "yf_event_time_bullish_aligned"), "analyst_alignment_event_time"] = "analyst_bullish_aligned"
    m.loc[use_yf_et & _bool_col(m, "yf_event_time_bearish_aligned"), "analyst_alignment_event_time"] = "analyst_bearish_aligned"
    m.loc[use_yf_et & _bool_col(m, "yf_event_time_contrarian_to_finfluencer"), "analyst_alignment_event_time"] = (
        "finfluencer_contrarian_to_analyst"
    )
    m.loc[use_yf_et & _bool_col(m, "yf_event_time_neutral_or_mixed"), "analyst_alignment_event_time"] = "analyst_neutral_or_mixed"
    for dest, src in [
        ("raw_latest_grade", "yf_raw_latest_grade_event_time"),
        ("normalized_latest_grade", "yf_normalized_latest_grade_event_time"),
        ("grade_mapping_confidence", "yf_grade_mapping_confidence_event_time"),
        ("grade_mapping_rule", "yf_grade_mapping_rule_event_time"),
    ]:
        if src in m.columns:
            m.loc[use_yf_et, dest] = m.loc[use_yf_et, src].fillna("").astype(str)

    m["analyst_alignment_diagnostic"] = "analyst_unknown"
    m.loc[_bool_col(m, "yf_current_bullish_aligned"), "analyst_alignment_diagnostic"] = "analyst_bullish_aligned"
    m.loc[_bool_col(m, "yf_current_bearish_aligned"), "analyst_alignment_diagnostic"] = "analyst_bearish_aligned"
    m.loc[_bool_col(m, "yf_current_neutral_or_mixed"), "analyst_alignment_diagnostic"] = "analyst_neutral_or_mixed"
    m.loc[_bool_col(m, "yf_current_contrarian_to_finfluencer"), "analyst_alignment_diagnostic"] = "finfluencer_contrarian_to_analyst"
    has_diag_label = m["analyst_alignment_diagnostic"].ne("analyst_unknown")
    fallback_diag = ~has_diag_label & primary_et
    m.loc[fallback_diag, "analyst_alignment_diagnostic"] = m.loc[fallback_diag, "analyst_alignment_event_time"]

    diag_grade_mask = ~m["analyst_event_time_usable"] & m["analyst_diagnostic_current_only"]
    for dest, src in [
        ("raw_latest_grade", "yf_raw_latest_grade_current"),
        ("normalized_latest_grade", "yf_normalized_latest_grade_current"),
        ("grade_mapping_confidence", "yf_grade_mapping_confidence_current"),
        ("grade_mapping_rule", "yf_grade_mapping_rule_current"),
    ]:
        if src in m.columns:
            m.loc[diag_grade_mask, dest] = m.loc[diag_grade_mask, src].fillna("").astype(str)

    m["analyst_relay_likely_event_time"] = _bool_col(m, "analyst_relay_likely") | _bool_col(m, "yf_analyst_relay_likely_event_time")
    m["analyst_relay_likely_diagnostic"] = _bool_col(m, "yf_analyst_relay_likely_diagnostic")

    m["analyst_any_coverage"] = m["analyst_event_time_usable"] | m["analyst_diagnostic_current_only"] | yf_snap
    m["analyst_unknown"] = ~(m["analyst_event_time_usable"] | m["analyst_diagnostic_current_only"])
    m["analyst_coverage_tier"] = "unknown"
    m.loc[m["analyst_event_time_usable"] & m["analyst_event_time_source"].isin(["fmp", "finnhub"]), "analyst_coverage_tier"] = (
        "event_time_primary_provider"
    )
    m.loc[m["analyst_event_time_usable"] & (m["analyst_event_time_source"] == "yfinance"), "analyst_coverage_tier"] = "event_time_yfinance"
    m.loc[m["analyst_diagnostic_current_only"] & ~m["analyst_event_time_usable"], "analyst_coverage_tier"] = "diagnostic_current_snapshot"

    m["analyst_alignment"] = m["analyst_alignment_event_time"]
    m.loc[~m["analyst_event_time_usable"] & m["analyst_diagnostic_current_only"], "analyst_alignment"] = (
        m["analyst_alignment_diagnostic"]
    )
    missing_grade = (
        m["analyst_event_time_usable"]
        & m["normalized_latest_grade"].astype(str).isin(["", "unknown"])
        & ~m["analyst_alignment_event_time"].astype(str).eq("analyst_unknown")
    )
    if missing_grade.any():
        inferred = m.loc[missing_grade].apply(
            lambda row: stance_from_alignment_label(row.get("analyst_alignment_event_time"), row.get("finfluencer_direction")),
            axis=1,
        )
        valid = inferred.ne("unknown")
        idx = inferred[valid].index
        m.loc[idx, "raw_latest_grade"] = "legacy_event_time_counts_no_raw_grade"
        m.loc[idx, "normalized_latest_grade"] = inferred.loc[idx]
        m.loc[idx, "grade_mapping_confidence"] = "legacy_counts"
        m.loc[idx, "grade_mapping_rule"] = "legacy_alignment_inferred_no_raw_grade"
    m["analyst_alignment_source_used"] = "unknown"
    m.loc[m["analyst_event_time_usable"], "analyst_alignment_source_used"] = (
        "event_time:" + m.loc[m["analyst_event_time_usable"], "analyst_event_time_source"].astype(str)
    )
    m.loc[~m["analyst_event_time_usable"] & m["analyst_diagnostic_current_only"], "analyst_alignment_source_used"] = (
        "diagnostic_current:"
        + m.loc[~m["analyst_event_time_usable"] & m["analyst_diagnostic_current_only"], "analyst_diagnostic_source"].astype(str)
    )
    return m


def load_yfinance_diagnostic_panel() -> pd.DataFrame:
    if not YF_DIAG_PANEL.exists():
        return pd.DataFrame()
    return pd.read_csv(YF_DIAG_PANEL)


def bootstrap_mean_ci(values: pd.Series, iterations: int = 500, seed: int = 496) -> tuple[float | None, float | None]:
    clean = pd.to_numeric(values, errors="coerce").dropna().astype(float).to_numpy()
    if len(clean) < 2:
        return None, None
    rng = np.random.default_rng(seed)
    means = [float(rng.choice(clean, size=len(clean), replace=True).mean()) for _ in range(iterations)]
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def alignment_return_rows(merged: pd.DataFrame, panel: pd.DataFrame, align_col: str, tick_col: str) -> list[dict]:
    rows: list[dict] = []
    if align_col not in panel.columns:
        return rows
    merged = merged.copy()
    merged[align_col] = merged["event_id"].map(panel.set_index("event_id")[align_col])
    for align in sorted(panel[align_col].dropna().astype(str).unique()):
        m = merged[align_col].astype(str) == align
        for sample, mask in [
            ("full", pd.Series(True, index=merged.index)),
            ("top5", merged[tick_col].isin(utils.TOP5)),
            ("non_top", ~merged[tick_col].isin(utils.TOP5)),
        ]:
            for horizon in ["5D", "21D", "63D"]:
                sub = merged.loc[m & mask & (merged["horizon"] == horizon)]
                if "status" in sub.columns:
                    sub = sub[sub["status"].astype(str).eq("computed")]
                values = pd.to_numeric(sub["spy_bhar"], errors="coerce").dropna().astype(float)
                stats = utils.t_stats(values.tolist())
                winsorized = utils.winsorize(values).dropna() if len(values) else pd.Series(dtype=float)
                lo, hi = bootstrap_mean_ci(values)
                rows.append(
                    {
                        "alignment_type": align_col,
                        "sample": sample,
                        "analyst_alignment": align,
                        "horizon": horizon,
                        "n": stats["n"],
                        "mean_spy_bhar": stats["mean"],
                        "median_spy_bhar": stats["median"],
                        "t_stat": stats["t_stat"],
                        "p_value": stats["p_value"],
                        "winsorized_mean_spy_bhar": float(winsorized.mean()) if len(winsorized) else None,
                        "bootstrap_ci_lower": lo,
                        "bootstrap_ci_upper": hi,
                        "warning_flags": "thin_n_lt_50" if int(stats["n"] or 0) < 50 else "",
                    }
                )
    return rows


def save_history_cache(df: pd.DataFrame) -> None:
    if not df.empty:
        df.drop_duplicates(subset=["ticker", "record_date", "source"], keep="last").to_csv(
            ie.TICKER_HISTORY_CACHE, index=False
        )


def _alignment_unknown_count(panel: pd.DataFrame) -> int:
    col = "analyst_alignment_event_time" if "analyst_alignment_event_time" in panel.columns else "analyst_alignment"
    if col not in panel.columns:
        return 0
    return int(panel[col].astype(str).eq("analyst_unknown").sum())


def _event_time_count(panel: pd.DataFrame) -> int:
    return int(_bool_col(panel, "analyst_event_time_usable").sum())


def _value_counts_rows(frame: pd.DataFrame, group_cols: list[str], count_name: str = "n") -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return (
        frame.groupby(group_cols, dropna=False)
        .size()
        .reset_index(name=count_name)
        .sort_values(count_name, ascending=False)
        .to_dict("records")
    )


def write_grade_normalization_audit(panel: pd.DataFrame, previous_panel: pd.DataFrame | None = None) -> None:
    panel = panel.copy()
    for col, default in {
        "raw_latest_grade": "",
        "normalized_latest_grade": "unknown",
        "grade_mapping_confidence": "unknown",
        "grade_mapping_rule": "missing",
        "analyst_event_time_source": "none",
        "analyst_coverage_tier": "unknown",
    }.items():
        if col not in panel.columns:
            panel[col] = default
        else:
            panel[col] = panel[col].fillna(default)
    grade_cols = [
        "analyst_event_time_source",
        "analyst_coverage_tier",
        "raw_latest_grade",
        "normalized_latest_grade",
        "grade_mapping_confidence",
        "grade_mapping_rule",
    ]
    raw_rows = _value_counts_rows(panel[grade_cols], grade_cols)
    utils.write_csv(GRADE_AUDIT_OUT / "raw_grade_frequency.csv", raw_rows, grade_cols + ["n"])

    normalized_rows = _value_counts_rows(
        panel[["analyst_event_time_source", "analyst_coverage_tier", "normalized_latest_grade"]],
        ["analyst_event_time_source", "analyst_coverage_tier", "normalized_latest_grade"],
    )
    utils.write_csv(
        GRADE_AUDIT_OUT / "normalized_grade_frequency.csv",
        normalized_rows,
        ["analyst_event_time_source", "analyst_coverage_tier", "normalized_latest_grade", "n"],
    )

    provider_rows = _value_counts_rows(
        panel[[
            "analyst_event_time_source",
            "raw_latest_grade",
            "normalized_latest_grade",
            "grade_mapping_confidence",
            "grade_mapping_rule",
        ]],
        [
            "analyst_event_time_source",
            "raw_latest_grade",
            "normalized_latest_grade",
            "grade_mapping_confidence",
            "grade_mapping_rule",
        ],
    )
    utils.write_csv(
        GRADE_AUDIT_OUT / "provider_by_grade_mapping.csv",
        provider_rows,
        [
            "analyst_event_time_source",
            "raw_latest_grade",
            "normalized_latest_grade",
            "grade_mapping_confidence",
            "grade_mapping_rule",
            "n",
        ],
    )

    unknown_mask = panel["normalized_latest_grade"].astype(str).eq("unknown")
    example_cols = [
        "event_id",
        "ticker",
        "event_date",
        "recommendation_type",
        "analyst_event_time_source",
        "analyst_coverage_tier",
        "analyst_alignment_event_time",
        "raw_latest_grade",
        "grade_mapping_rule",
    ]
    examples = panel.loc[unknown_mask, [c for c in example_cols if c in panel.columns]].head(200)
    examples.to_csv(GRADE_AUDIT_OUT / "unknown_grade_examples.csv", index=False)

    before_unknown = _alignment_unknown_count(previous_panel) if previous_panel is not None and not previous_panel.empty else _alignment_unknown_count(panel)
    after_unknown = _alignment_unknown_count(panel)
    before_event_time = _event_time_count(previous_panel) if previous_panel is not None and not previous_panel.empty else _event_time_count(panel)
    after_event_time = _event_time_count(panel)
    reclassified = 0
    reclass_provider_rows: list[dict[str, Any]] = []
    before_dist: dict[str, int] = {}
    if previous_panel is not None and not previous_panel.empty and "event_id" in previous_panel.columns:
        before_col = "analyst_alignment_event_time" if "analyst_alignment_event_time" in previous_panel.columns else "analyst_alignment"
        before_dist = previous_panel[before_col].value_counts(dropna=False).to_dict()
        cur_col = "analyst_alignment_event_time" if "analyst_alignment_event_time" in panel.columns else "analyst_alignment"
        comp = previous_panel[["event_id", before_col]].rename(columns={before_col: "alignment_before"}).merge(
            panel[["event_id", cur_col, "analyst_event_time_source", "analyst_coverage_tier"]].rename(
                columns={cur_col: "alignment_after"}
            ),
            on="event_id",
            how="inner",
        )
        moved = comp[
            comp["alignment_before"].astype(str).eq("analyst_unknown")
            & ~comp["alignment_after"].astype(str).eq("analyst_unknown")
        ]
        reclassified = len(moved)
        if not moved.empty:
            reclass_provider_rows = _value_counts_rows(
                moved[["analyst_event_time_source", "analyst_coverage_tier", "alignment_after"]],
                ["analyst_event_time_source", "analyst_coverage_tier", "alignment_after"],
            )
    else:
        before_dist = panel["analyst_alignment_event_time"].value_counts(dropna=False).to_dict()
    after_dist = panel["analyst_alignment_event_time"].value_counts(dropna=False).to_dict()
    remaining_unknown_top = _value_counts_rows(
        panel.loc[panel["analyst_alignment_event_time"].astype(str).eq("analyst_unknown"), ["raw_latest_grade", "grade_mapping_rule"]],
        ["raw_latest_grade", "grade_mapping_rule"],
    )[:20]

    summary = f"""# Analyst grade normalization audit

| Metric | Count |
| --- | ---: |
| Event-time alignment unknown before | {before_unknown} |
| Event-time alignment unknown after | {after_unknown} |
| Events reclassified from analyst_unknown | {reclassified} |
| Event-time coverage before | {before_event_time} |
| Event-time coverage after | {after_event_time} |

## Reclassified distribution by provider
{utils.md_table(reclass_provider_rows)}

## Alignment distribution before
{utils.md_table([{"analyst_alignment": k, "n": v} for k, v in before_dist.items()])}

## Alignment distribution after
{utils.md_table([{"analyst_alignment": k, "n": v} for k, v in after_dist.items()])}

## Top raw strings causing remaining unknowns
{utils.md_table(remaining_unknown_top)}

## Claim discipline
- Grade normalization improves descriptive analyst-relay classification.
- It does not turn yfinance current snapshots into event-time evidence.
- It does not establish causality, tradability, or clean public-information controls.
"""
    utils.write_md(
        GRADE_AUDIT_OUT / "analyst_unknown_reduction_summary.md",
        "Analyst Unknown Reduction Summary",
        summary,
    )


def write_alignment_count_outputs(panel: pd.DataFrame) -> None:
    rows: list[dict[str, Any]] = []
    for col in ["analyst_alignment", "analyst_alignment_event_time", "analyst_alignment_diagnostic"]:
        if col not in panel.columns:
            continue
        for label, n in panel[col].value_counts(dropna=False).items():
            rows.append({"alignment_type": col, "sample": "full", "analyst_alignment": label, "n": int(n)})
    utils.write_csv(
        OUT / "alignment_counts_full_sample.csv",
        rows,
        ["alignment_type", "sample", "analyst_alignment", "n"],
    )
    utils.write_md(OUT / "alignment_counts_full_sample.md", "Alignment Counts Full Sample", utils.md_table(rows))

    split_rows: list[dict[str, Any]] = []
    top5 = panel["ticker"].astype(str).isin(utils.TOP5)
    for sample, mask in [
        ("top5", top5),
        ("non_top", ~top5),
    ]:
        sub = panel.loc[mask]
        for col in ["analyst_alignment", "analyst_alignment_event_time", "analyst_alignment_diagnostic"]:
            if col not in sub.columns:
                continue
            for label, n in sub[col].value_counts(dropna=False).items():
                split_rows.append({"alignment_type": col, "sample": sample, "analyst_alignment": label, "n": int(n)})
    utils.write_csv(
        OUT / "alignment_counts_top5_vs_non_top.csv",
        split_rows,
        ["alignment_type", "sample", "analyst_alignment", "n"],
    )
    utils.write_md(
        OUT / "alignment_counts_top5_vs_non_top.md",
        "Alignment Counts Top-5 vs Non-Top",
        utils.md_table(split_rows),
    )


def write_alignment_focus_outputs(summary_rows: list[dict[str, Any]]) -> None:
    focus = []
    for row in summary_rows:
        alignment_type = row.get("alignment_type")
        align = row.get("analyst_alignment")
        sample = row.get("sample")
        if alignment_type == "analyst_alignment_event_time":
            if align in {"analyst_bullish_aligned", "analyst_neutral_or_mixed", "analyst_unknown"}:
                focus.append({**row, "focus": f"event_time_{align}"})
            if align == "analyst_bullish_aligned" and sample in {"top5", "non_top"}:
                focus.append({**row, "focus": "top5_vs_non_top_bullish_aligned"})
        if alignment_type == "analyst_alignment":
            if align in {"analyst_bullish_aligned", "analyst_neutral_or_mixed", "analyst_unknown"}:
                focus.append({**row, "focus": f"diagnostic_current_included_{align}"})
        if alignment_type == "analyst_alignment_diagnostic" and align in {
            "analyst_bullish_aligned",
            "analyst_neutral_or_mixed",
            "analyst_unknown",
        }:
            focus.append({**row, "focus": f"diagnostic_current_snapshot_{align}"})
    columns = [
        "focus",
        "alignment_type",
        "sample",
        "analyst_alignment",
        "horizon",
        "n",
        "mean_spy_bhar",
        "median_spy_bhar",
        "t_stat",
        "p_value",
        "winsorized_mean_spy_bhar",
        "bootstrap_ci_lower",
        "bootstrap_ci_upper",
        "warning_flags",
    ]
    utils.write_csv(OUT / "alignment_return_focus_tables.csv", focus, columns)
    utils.write_md(OUT / "alignment_return_focus_tables.md", "Alignment Return Focus Tables", utils.md_table(focus, columns))


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

    skip_fetch = os.environ.get("FIN496_SKIP_PROVIDER_FETCH", "").lower() in ("1", "true")
    existing_panel_path = OUT / "analyst_relay_event_panel.csv"
    previous_panel = pd.read_csv(existing_panel_path) if existing_panel_path.exists() else pd.DataFrame()
    if skip_fetch and existing_panel_path.exists():
        panel = pd.read_csv(existing_panel_path)
        yf_panel = load_yfinance_diagnostic_panel()
        panel = merge_yfinance_diagnostic_panel(panel, yf_panel)
        panel.to_csv(existing_panel_path, index=False)
        return _write_analyst_outputs(panel, events, provider_status, request_log, tickers, previous_panel)

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
    yf_panel = load_yfinance_diagnostic_panel()
    panel = merge_yfinance_diagnostic_panel(panel, yf_panel)
    panel.to_csv(OUT / "analyst_relay_event_panel.csv", index=False)
    return _write_analyst_outputs(panel, events, provider_status, request_log, tickers, previous_panel)


def _write_analyst_outputs(
    panel: pd.DataFrame,
    events: pd.DataFrame,
    provider_status: list[dict[str, Any]],
    request_log: list[dict[str, Any]],
    tickers: list[str],
    previous_panel: pd.DataFrame | None = None,
) -> int:
    tickers = tickers or sorted(panel["ticker"].astype(str).str.upper().unique())
    coverage = []
    for ticker in tickers:
        sub = panel[panel["ticker"] == ticker]
        coverage.append(
            {
                "ticker": ticker,
                "n_events": len(sub),
                "event_time_usable_n": int(_bool_col(sub, "analyst_event_time_usable").sum()),
                "diagnostic_current_n": int(_bool_col(sub, "analyst_diagnostic_current_only").sum()),
                "yfinance_fallback_n": int(_bool_col(sub, "diagnostic_yfinance_fallback").sum()),
                "unknown_n": int(_bool_col(sub, "analyst_unknown").sum()),
                "fmp_ok": int((sub["fmp_provider_status"] == "ok").sum()) if "fmp_provider_status" in sub else 0,
            }
        )
    utils.write_csv(OUT / "analyst_relay_ticker_coverage.csv", coverage, list(coverage[0]) if coverage else ["ticker"])

    fwd = utils.forward_panel(["5D", "21D", "63D"])
    merged = fwd.merge(panel, on="event_id", how="left", suffixes=("", "_ar"))
    tick_col = "ticker" if "ticker" in merged.columns else "ticker_ar"
    summary_rows = alignment_return_rows(merged, panel, "analyst_alignment", tick_col)
    summary_rows.extend(alignment_return_rows(merged, panel, "analyst_alignment_event_time", tick_col))
    summary_rows.extend(alignment_return_rows(merged, panel, "analyst_alignment_diagnostic", tick_col))
    utils.write_csv(OUT / "returns_by_analyst_alignment.csv", summary_rows, list(summary_rows[0]) if summary_rows else ["sample"])
    utils.write_md(OUT / "returns_by_analyst_alignment.md", "Returns by Analyst Alignment", utils.md_table(summary_rows))
    write_alignment_count_outputs(panel)
    write_alignment_focus_outputs(summary_rows)
    write_grade_normalization_audit(panel, previous_panel)

    et_n = int(_bool_col(panel, "analyst_event_time_usable").sum())
    diag_n = int(_bool_col(panel, "analyst_diagnostic_current_only").sum())
    yf_n = int(_bool_col(panel, "diagnostic_yfinance_fallback").sum())
    unk_n = int(_bool_col(panel, "analyst_unknown").sum())
    top5_et = int(panel.loc[panel["top5_flag"].astype(bool), "analyst_event_time_usable"].sum()) if "top5_flag" in panel else 0
    nontop_et = int(panel.loc[~panel["top5_flag"].astype(bool), "analyst_event_time_usable"].sum()) if "top5_flag" in panel else 0

    src_counts = panel["analyst_event_time_source"].value_counts().to_dict() if "analyst_event_time_source" in panel else {}
    tier_counts = panel["analyst_coverage_tier"].value_counts().to_dict() if "analyst_coverage_tier" in panel else {}
    et_align = panel["analyst_alignment_event_time"].value_counts().to_dict() if "analyst_alignment_event_time" in panel else {}
    diag_align = panel["analyst_alignment_diagnostic"].value_counts().to_dict() if "analyst_alignment_diagnostic" in panel else {}

    yf_et = int(_bool_col(panel, "yf_event_time_usable").sum()) if "yf_event_time_usable" in panel else 0
    yf_diag = int(_bool_col(panel, "yf_diagnostic_current_only").sum()) if "yf_diagnostic_current_only" in panel else 0
    both = 0
    if "analyst_alignment_event_time" in panel and "analyst_alignment_diagnostic" in panel:
        diagnostic_available = _bool_col(panel, "yf_snapshot_available") | ~panel["analyst_alignment_diagnostic"].astype(str).eq(
            "analyst_unknown"
        )
        has_both = _bool_col(panel, "analyst_event_time_usable") & diagnostic_available
        if has_both.any():
            agree = panel.loc[has_both, "analyst_alignment_event_time"] == panel.loc[has_both, "analyst_alignment_diagnostic"]
            both = int(has_both.sum())
            agree_n = int(agree.sum())
        else:
            agree_n = 0
    else:
        agree_n = 0

    summary = f"""# Analyst relay layer (FMP / Finnhub / yfinance)

## Provider status
{utils.md_table(provider_status)}

## A. Event-time analyst evidence
| Metric | Count |
| --- | ---: |
| Total events | {len(panel)} |
| Event-time analyst usable (combined) | **{et_n}** |
| yfinance dated pre-event usable | {yf_et} |
| Analyst unknown (no usable coverage) | **{unk_n}** |
| Top-5 event-time usable | {top5_et} |
| Non-top event-time usable | {nontop_et} |

Event-time source counts: {src_counts}

Event-time alignment: {et_align}

**Paper use:** Only dated pre-event FMP/Finnhub/yfinance rows support event-time relay claims. Unknown ≠ clean.

## B. yfinance diagnostic current snapshot evidence
| Metric | Count |
| --- | ---: |
| Diagnostic current-only (combined) | **{diag_n}** |
| yfinance diagnostic current-only flagged | {yf_diag} |
| yfinance fallback flagged | {yf_n} |

Diagnostic alignment: {diag_align}

**Warning:** Current yfinance recommendation keys and price targets are **current-snapshot diagnostics only** — not historical event-time proof.

## C. Event-time vs diagnostic comparison
| Metric | Count |
| --- | ---: |
| Events with both event-time and diagnostic fields | {both} |
| Agreement (same alignment label) | {agree_n} |

Do not treat diagnostic-current agreement as validation of historical analyst positioning.

## D. Impact on thesis (exploratory)
- Top-5 positives: inspect whether event-time alignment is bullish/contrarian/unknown in `returns_by_analyst_alignment.md`.
- Non-top weakness: check whether analyst evidence is aligned, contrarian, or unknown — not causal skill.
- yfinance improves **coverage** for narrative-relay classification; it does **not** strengthen causal identification.

Coverage tier: {tier_counts}

### Allowed paper language
- "yfinance is used more aggressively as a diagnostic gap-filling analyst layer pending Bloomberg validation."
- "Partial dated analyst metadata suggests relay with observable consensus where event-time fields exist."

### Prohibited
- Full analyst-news-clean or public-news-clean robustness.
- Causal finfluencer skill, tradability, or using current yfinance snapshots as historical proof.
"""
    utils.write_md(OUT / "analyst_relay_summary.md", "Analyst Relay Summary", summary)

    limits = """# Analyst relay limitations

- FMP/Finnhub remain preferred when usable; yfinance fills gaps as **diagnostic_yfinance_fallback**.
- Current-only yfinance snapshots are diagnostic — not event-time historical evidence.
- Bloomberg analyst exports are the planned authoritative validation path.
- Unknown analyst coverage must never be coded as clean.
- Alignment is descriptive co-movement with consensus, not skill or tradability.
"""
    utils.write_md(OUT / "analyst_relay_limitations.md", "Analyst Relay Limitations", limits)
    print("Analyst relay layer complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
