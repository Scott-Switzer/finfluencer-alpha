"""Aggressive yfinance analyst diagnostic layer — gap-filler until Bloomberg validation."""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_analyst_relay_layer as ar  # noqa: E402
import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = ie.info_dir("yfinance_analyst_diagnostic")
YF_PAUSE = 0.2
EVENT_LOOKBACK_DAYS = 365
REVISION_DAYS = 90


def safe_float(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        x = float(v)
        if pd.isna(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def grade_to_stance(text: str) -> str:
    t = (text or "").lower()
    if any(x in t for x in ["strong buy", "buy", "outperform", "overweight"]):
        return "bullish"
    if any(x in t for x in ["strong sell", "sell", "underperform", "underweight"]):
        return "bearish"
    if any(x in t for x in ["hold", "neutral", "equal", "maintain"]):
        return "neutral"
    return "unknown"


def alignment_flags(fin_dir: str, stance: str) -> dict[str, bool]:
    out = {
        "bullish_aligned": False,
        "bearish_aligned": False,
        "neutral_or_mixed": False,
        "contrarian": False,
        "relay_likely": False,
    }
    if stance == "bullish":
        out["bullish_aligned"] = fin_dir == "bullish"
        out["neutral_or_mixed"] = fin_dir == "neutral"
        out["contrarian"] = fin_dir == "bearish"
    elif stance == "bearish":
        out["bearish_aligned"] = fin_dir == "bearish"
        out["neutral_or_mixed"] = fin_dir == "neutral"
        out["contrarian"] = fin_dir == "bullish"
    elif stance == "neutral":
        out["neutral_or_mixed"] = True
    if fin_dir in {"bullish", "bearish"} and stance in {"bullish", "bearish"}:
        out["relay_likely"] = (fin_dir == stance) or out["contrarian"]
    return out


def normalize_upgrades_df(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.reset_index() if "index" in df.columns.names or df.index.name else df.copy()
    date_col = next((c for c in out.columns if str(c).lower() in {"date", "grade date", "index"}), out.columns[0])
    rows: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        d = ie.parse_iso_date(row.get(date_col))
        if not d:
            continue
        to_grade = str(row.get("To Grade", row.get("toGrade", row.get("to_grade", ""))))
        from_grade = str(row.get("From Grade", row.get("fromGrade", row.get("from_grade", ""))))
        firm = str(row.get("Firm", row.get("firm", "")))[:80]
        action = str(row.get("Action", row.get("action", ""))).lower()
        rows.append(
            {
                "ticker": ticker,
                "record_date": d.isoformat(),
                "firm": firm,
                "to_grade": to_grade[:40],
                "from_grade": from_grade[:40],
                "action": action[:40],
                "source": "yfinance_upgrades_downgrades",
            }
        )
    return pd.DataFrame(rows)


def normalize_recommendations_df(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.reset_index()
    date_col = out.columns[0]
    rows: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        d = ie.parse_iso_date(row.get(date_col))
        if not d:
            continue
        rows.append(
            {
                "ticker": ticker,
                "record_date": d.isoformat(),
                "firm": "",
                "to_grade": str(row.to_dict())[:80],
                "from_grade": "",
                "action": "recommendation",
                "source": "yfinance_recommendations",
            }
        )
    return pd.DataFrame(rows)


def fetch_ticker_yfinance(ticker: str) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    status_rows: list[dict[str, Any]] = []
    snap: dict[str, Any] = {"ticker": ticker, "yf_provider_status": "skipped", "yf_error_class_safe": ""}
    hist_parts: list[pd.DataFrame] = []

    try:
        import yfinance as yf
    except ImportError:
        snap["yf_provider_status"] = "missing_package"
        snap["yf_error_class_safe"] = "import_error"
        status_rows.append({"ticker": ticker, "endpoint": "import", "status": "missing_package"})
        return snap, pd.DataFrame(), pd.DataFrame(), status_rows

    try:
        t = yf.Ticker(ticker)
        info: dict[str, Any] = {}
        try:
            info = t.info or {}
            status_rows.append({"ticker": ticker, "endpoint": "info", "status": "ok"})
        except Exception as exc:
            status_rows.append({"ticker": ticker, "endpoint": "info", "status": "error", "error_class_safe": type(exc).__name__})

        snap.update(
            {
                "yf_provider_status": "ok",
                "yf_snapshot_available": True,
                "yf_recommendation_key": str(info.get("recommendationKey", ""))[:40],
                "yf_recommendation_mean": safe_float(info.get("recommendationMean")),
                "yf_number_of_analysts": safe_float(info.get("numberOfAnalystOpinions")),
                "yf_target_mean": safe_float(info.get("targetMeanPrice")),
                "yf_target_median": safe_float(info.get("targetMedianPrice")),
                "yf_target_high": safe_float(info.get("targetHighPrice")),
                "yf_target_low": safe_float(info.get("targetLowPrice")),
                "yf_current_price": safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
                "yf_beta": safe_float(info.get("beta")),
                "yf_sector": str(info.get("sector", ""))[:60],
                "yf_industry": str(info.get("industry", ""))[:60],
            }
        )
        key = str(snap.get("yf_recommendation_key", "")).lower()
        snap["yf_consensus_bucket_current"] = grade_to_stance(key) if key else "unknown"

        for attr, label in [
            ("upgrades_downgrades", "upgrades_downgrades"),
            ("recommendations", "recommendations"),
        ]:
            try:
                frame = getattr(t, attr, None)
                if frame is None or (hasattr(frame, "empty") and frame.empty):
                    status_rows.append({"ticker": ticker, "endpoint": attr, "status": "empty"})
                    continue
                if label == "upgrades_downgrades":
                    part = normalize_upgrades_df(frame, ticker)
                else:
                    part = normalize_recommendations_df(frame, ticker)
                if not part.empty:
                    hist_parts.append(part)
                status_rows.append({"ticker": ticker, "endpoint": attr, "status": "ok", "n_rows": len(part)})
            except Exception as exc:
                status_rows.append(
                    {"ticker": ticker, "endpoint": attr, "status": "error", "error_class_safe": type(exc).__name__}
                )

        for method_name, label in [
            ("get_recommendations_summary", "recommendations_summary"),
            ("get_analyst_price_targets", "analyst_price_targets"),
        ]:
            try:
                fn = getattr(t, method_name, None)
                if not callable(fn):
                    continue
                data = fn()
                if isinstance(data, pd.DataFrame) and not data.empty:
                    status_rows.append({"ticker": ticker, "endpoint": label, "status": "ok", "n_rows": len(data)})
                else:
                    status_rows.append({"ticker": ticker, "endpoint": label, "status": "empty"})
            except Exception as exc:
                status_rows.append(
                    {"ticker": ticker, "endpoint": label, "status": "error", "error_class_safe": type(exc).__name__}
                )

    except Exception as exc:
        snap["yf_provider_status"] = "error"
        snap["yf_error_class_safe"] = type(exc).__name__
        status_rows.append({"ticker": ticker, "endpoint": "ticker", "status": "error", "error_class_safe": type(exc).__name__})

    hist = pd.concat(hist_parts, ignore_index=True) if hist_parts else pd.DataFrame()
    if not hist.empty:
        hist = hist.drop_duplicates(subset=["ticker", "record_date", "source", "to_grade"], keep="last")
    return snap, hist, pd.DataFrame(), status_rows


def pick_pre_event_row(hist: pd.DataFrame, event_date: date) -> tuple[pd.Series | None, bool, bool]:
    if hist.empty:
        return None, False, False
    h = hist.copy()
    h["record_date_dt"] = pd.to_datetime(h["record_date"], errors="coerce").dt.date
    pre = h[(h["record_date_dt"] <= event_date) & (h["record_date_dt"] >= event_date - timedelta(days=EVENT_LOOKBACK_DAYS))]
    pre = pre.sort_values("record_date_dt")
    if pre.empty:
        return None, False, False
    latest = pre.iloc[-1]
    rev_start = event_date - timedelta(days=REVISION_DAYS)
    recent = pre["record_date_dt"] >= rev_start
    actions = pre["action"].astype(str).str.lower()
    up = bool((recent & actions.str.contains("upgrade", na=False)).any())
    down = bool((recent & actions.str.contains("downgrade", na=False)).any())
    to_g = str(latest.get("to_grade", ""))
    if "upgrade" in to_g.lower():
        up = True
    if "downgrade" in to_g.lower():
        down = True
    return latest, up, down


def build_event_row(ev: pd.Series, snap: dict[str, Any], hist: pd.DataFrame, event_price: float | None) -> dict[str, Any]:
    ed = ie.parse_iso_date(ev.get("event_date"))
    fin_dir = ar.finfluencer_direction(ev.get("recommendation_type"))
    row: dict[str, Any] = {
        "event_id": ev["event_id"],
        "ticker": str(ev["ticker"]).upper(),
        "event_date": ev["event_date"],
        "recommendation_type": ev.get("recommendation_type"),
        "top5_flag": ev.get("top5_flag"),
        "yf_snapshot_available": bool(snap.get("yf_snapshot_available")),
        "yf_event_time_usable": False,
        "yf_diagnostic_current_only": False,
        "yf_provider_status": snap.get("yf_provider_status", "skipped"),
        "yf_error_class_safe": snap.get("yf_error_class_safe", ""),
    }
    for k in (
        "yf_recommendation_key_current",
        "yf_recommendation_mean_current",
        "yf_number_of_analysts_current",
        "yf_target_mean_current",
        "yf_target_median_current",
        "yf_target_high_current",
        "yf_target_low_current",
        "yf_consensus_bucket_current",
    ):
        src = k.replace("_current", "")
        if src in snap:
            row[k] = snap.get(src)

    if snap.get("yf_snapshot_available"):
        row["yf_diagnostic_current_only"] = True
        ref = event_price or snap.get("yf_current_price")
        tm = snap.get("yf_target_mean") or snap.get("yf_target_median")
        if tm and ref:
            try:
                row["yf_target_upside_vs_event_price_current"] = float(tm) / float(ref) - 1.0
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        cur_stance = grade_to_stance(str(snap.get("yf_recommendation_key", "")))
        if cur_stance == "unknown":
            cur_stance = grade_to_stance(str(snap.get("yf_consensus_bucket_current", "")))
        cur_align = alignment_flags(fin_dir, cur_stance)
        row["yf_current_bullish_aligned"] = cur_align["bullish_aligned"]
        row["yf_current_bearish_aligned"] = cur_align["bearish_aligned"]
        row["yf_current_neutral_or_mixed"] = cur_align["neutral_or_mixed"]
        row["yf_current_contrarian_to_finfluencer"] = cur_align["contrarian"]
        row["yf_analyst_relay_likely_diagnostic"] = cur_align["relay_likely"]

    if ed is None:
        return row

    latest, up_rev, down_rev = pick_pre_event_row(hist, ed)
    if latest is not None:
        row["yf_event_time_usable"] = True
        row["yf_diagnostic_current_only"] = False
        row["yf_latest_recommendation_date_pre_event"] = latest.get("record_date")
        row["yf_latest_firm_pre_event"] = latest.get("firm")
        row["yf_latest_to_grade_pre_event"] = latest.get("to_grade")
        row["yf_latest_from_grade_pre_event"] = latest.get("from_grade")
        row["yf_latest_recommendation_action_pre_event"] = latest.get("action")
        row["yf_recent_upgrade_pre_event"] = up_rev
        row["yf_recent_downgrade_pre_event"] = down_rev
        et_stance = grade_to_stance(str(latest.get("to_grade", "")))
        row["yf_consensus_bucket_event_time_if_available"] = et_stance
        et_align = alignment_flags(fin_dir, et_stance)
        row["yf_event_time_bullish_aligned"] = et_align["bullish_aligned"]
        row["yf_event_time_bearish_aligned"] = et_align["bearish_aligned"]
        row["yf_event_time_neutral_or_mixed"] = et_align["neutral_or_mixed"]
        row["yf_event_time_contrarian_to_finfluencer"] = et_align["contrarian"]
        row["yf_analyst_relay_likely_event_time"] = et_align["relay_likely"]
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    events = rf.build_event_feature_table()
    if events.empty:
        utils.write_md(OUT / "yfinance_analyst_diagnostic_summary.md", "YFinance Analyst Diagnostic", "No events.")
        return 0

    frames = rf.load_market_with_volume()
    tickers = sorted(events["ticker"].astype(str).str.upper().unique())
    snapshots: list[dict[str, Any]] = []
    hist_all: list[pd.DataFrame] = []
    provider_status: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []

    for ticker in tickers:
        snap, hist, _summary_df, statuses = fetch_ticker_yfinance(ticker)
        snapshots.append(snap)
        if not hist.empty:
            hist_all.append(hist)
        provider_status.extend(statuses)
        time.sleep(YF_PAUSE)

    snap_df = pd.DataFrame(snapshots)
    snap_df.to_csv(OUT / "yfinance_ticker_analyst_snapshot.csv", index=False)
    hist_df = pd.concat(hist_all, ignore_index=True) if hist_all else pd.DataFrame()
    if not hist_df.empty:
        hist_df.to_csv(OUT / "yfinance_upgrades_downgrades_compact.csv", index=False)
        rec = hist_df[hist_df["source"] == "yfinance_recommendations"]
        if not rec.empty:
            rec.to_csv(OUT / "yfinance_recommendations_history_compact.csv", index=False)

    utils.write_csv(OUT / "yfinance_provider_status.csv", provider_status, ["ticker", "endpoint", "status"])
    for fname, cols in [
        ("yfinance_recommendations_summary_compact.csv", ["ticker"]),
        ("yfinance_earnings_estimates_compact.csv", ["ticker"]),
    ]:
        p = OUT / fname
        if not p.exists():
            pd.DataFrame(columns=cols).to_csv(p, index=False)

    hist_by_ticker = {t: hist_df[hist_df["ticker"] == t] if not hist_df.empty else pd.DataFrame() for t in tickers}
    snap_map = {r["ticker"]: r for r in snapshots}

    for _, ev in events.iterrows():
        ticker = str(ev["ticker"]).upper()
        px = ar.pre_event_price(ticker, ev["event_date"], frames)
        event_rows.append(build_event_row(ev, snap_map.get(ticker, {"ticker": ticker}), hist_by_ticker.get(ticker, pd.DataFrame()), px))

    event_panel = pd.DataFrame(event_rows)
    event_panel.to_csv(OUT / "yfinance_event_analyst_diagnostic_panel.csv", index=False)

    et_n = int(event_panel["yf_event_time_usable"].sum())
    diag_n = int(event_panel["yf_diagnostic_current_only"].sum())
    snap_n = int(event_panel["yf_snapshot_available"].sum())

    summary = f"""# yfinance analyst diagnostic layer

**diagnostic_yfinance_fallback** — gap-filler until Bloomberg validation. Not authoritative historical evidence unless dated pre-event rows exist.

## Coverage
| Metric | Count |
| --- | ---: |
| Tickers | {len(tickers)} |
| Events | {len(event_panel)} |
| Snapshot available | {snap_n} |
| yfinance event-time usable (dated pre-event) | **{et_n}** |
| Diagnostic current snapshot only | {diag_n} |

## Event-time alignment (yfinance dated only)
| Flag | Count |
| --- | ---: |
| Bullish aligned | {int(event_panel.get('yf_event_time_bullish_aligned', pd.Series(dtype=bool)).sum())} |
| Bearish aligned | {int(event_panel.get('yf_event_time_bearish_aligned', pd.Series(dtype=bool)).sum())} |
| Contrarian | {int(event_panel.get('yf_event_time_contrarian_to_finfluencer', pd.Series(dtype=bool)).sum())} |

## Current snapshot alignment (NOT historical event-time proof)
| Flag | Count |
| --- | ---: |
| Current bullish aligned | {int(event_panel.get('yf_current_bullish_aligned', pd.Series(dtype=bool)).sum())} |
| Current contrarian | {int(event_panel.get('yf_current_contrarian_to_finfluencer', pd.Series(dtype=bool)).sum())} |

## Paper use
- **Allowed:** yfinance improves **diagnostic** analyst-relay coverage; dated pre-event rows support **exploratory** event-time splits only.
- **Prohibited:** Treating current yfinance targets/ratings as historical event-time proof; analyst-news-clean claims.
"""
    utils.write_md(OUT / "yfinance_analyst_diagnostic_summary.md", "YFinance Analyst Diagnostic", summary)
    print("yfinance analyst diagnostic layer complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
