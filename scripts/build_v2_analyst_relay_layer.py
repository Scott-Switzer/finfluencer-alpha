"""Analyst consensus / price-target relay layer (event-time when dated; diagnostic if snapshot-only)."""

from __future__ import annotations

import sys
import time
import urllib.parse
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = ie.info_dir("analyst_relay")
LOOKBACK_DAYS = 30
REVISION_DAYS = 14


def fetch_finnhub_history(ticker: str, key: str) -> tuple[list[dict[str, Any]], str]:
    q = urllib.parse.urlencode({"symbol": ticker, "token": key})
    url = f"https://finnhub.io/api/v1/stock/recommendation?{q}"
    data, status = ie.http_json(url)
    if not isinstance(data, list):
        return [], status
    rows = []
    for item in data:
        d = ie.parse_iso_date(item.get("period"))
        if not d:
            continue
        buy = int(item.get("buy", 0) or 0) + int(item.get("strongBuy", 0) or 0)
        sell = int(item.get("sell", 0) or 0) + int(item.get("strongSell", 0) or 0)
        hold = int(item.get("hold", 0) or 0)
        rows.append(
            {
                "ticker": ticker,
                "record_date": d.isoformat(),
                "buy_count": buy,
                "sell_count": sell,
                "hold_count": hold,
                "source": "finnhub_recommendation",
            }
        )
    return rows, "ok"


def fetch_fmp_grades(ticker: str, key: str) -> tuple[list[dict[str, Any]], str]:
    q = urllib.parse.urlencode({"symbol": ticker, "apikey": key})
    url = f"https://financialmodelingprep.com/api/v3/grade/{ticker}?{q}"
    data, status = ie.http_json(url)
    if not isinstance(data, list):
        return [], status
    rows = []
    for item in data:
        d = ie.parse_iso_date(item.get("date"))
        if not d:
            continue
        rows.append(
            {
                "ticker": ticker,
                "record_date": d.isoformat(),
                "grade_action": str(item.get("newGrade", "") or item.get("gradingCompany", ""))[:80],
                "prior_grade": str(item.get("previousGrade", ""))[:40],
                "source": "fmp_grade",
            }
        )
    return rows, "ok"


def fetch_fmp_consensus_snapshot(ticker: str, key: str) -> dict[str, Any]:
    q = urllib.parse.urlencode({"symbol": ticker, "apikey": key})
    url = f"https://financialmodelingprep.com/api/v4/price-target-consensus?{q}"
    data, status = ie.http_json(url)
    if isinstance(data, list) and data:
        row = data[0]
    elif isinstance(data, dict):
        row = data
    else:
        return {"status": status}
    return {
        "status": "ok",
        "target_consensus": row.get("targetConsensus") or row.get("consensus"),
        "target_high": row.get("targetHigh"),
        "target_low": row.get("targetLow"),
        "target_median": row.get("targetMedian"),
    }


def analyst_sentiment_from_counts(buy: int, sell: int, hold: int) -> str:
    total = buy + sell + hold
    if total == 0:
        return "analyst_unknown"
    if buy >= sell * 2 and buy > hold:
        return "analyst_bullish_aligned"
    if sell >= buy * 2 and sell > hold:
        return "analyst_bearish_aligned"
    return "analyst_neutral_or_mixed"


def classify_event(
    event_date: Any,
    rec_type: str,
    hist: pd.DataFrame,
    snapshot: dict[str, Any] | None,
    pre_price: float | None,
) -> dict[str, Any]:
    ed = ie.parse_iso_date(event_date)
    out: dict[str, Any] = {
        "analyst_data_mode": "analyst_unknown",
        "analyst_alignment": "analyst_unknown",
        "recent_analyst_revision_pre_event": False,
        "finfluencer_contrarian_to_analyst": False,
        "diagnostic_current_only": False,
    }
    if ed is None:
        return out
    dated = hist.copy()
    if not dated.empty and "record_date" in dated.columns:
        dated["record_date_dt"] = pd.to_datetime(dated["record_date"], errors="coerce").dt.date
        pre = dated[dated["record_date_dt"] <= ed].sort_values("record_date_dt")
        if not pre.empty:
            latest = pre.iloc[-1]
            buy = int(latest.get("buy_count", 0) or 0)
            sell = int(latest.get("sell_count", 0) or 0)
            hold = int(latest.get("hold_count", 0) or 0)
            align = analyst_sentiment_from_counts(buy, sell, hold)
            out["analyst_data_mode"] = "event_time_historical"
            out["analyst_alignment"] = align
            rev_window = ed - timedelta(days=REVISION_DAYS)
            out["recent_analyst_revision_pre_event"] = bool((pre["record_date_dt"] >= rev_window).any())
            is_buy = str(rec_type).lower() in {"buy", "strong_buy", "accumulate"}
            is_sell = str(rec_type).lower() in {"sell", "short", "avoid"}
            if is_buy and align == "analyst_bearish_aligned":
                out["finfluencer_contrarian_to_analyst"] = True
            if is_sell and align == "analyst_bullish_aligned":
                out["finfluencer_contrarian_to_analyst"] = True
            return out
    if snapshot and snapshot.get("status") == "ok":
        out["analyst_data_mode"] = "diagnostic_current_only"
        out["diagnostic_current_only"] = True
        out["analyst_alignment"] = "diagnostic_current_only"
        tc = snapshot.get("target_consensus") or snapshot.get("target_median")
        if pre_price and tc:
            try:
                upside = float(tc) / float(pre_price) - 1.0
                out["target_upside_vs_pre_event"] = upside
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    return out


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        utils.write_md(OUT / "analyst_relay_summary.md", "Analyst Relay", "No events.")
        return 0

    fmp_key, fmp_src = ie.load_api_key("FMP_API_KEY")
    fh_key, fh_src = ie.load_api_key("FINNHUB_API_KEY")

    provider_status = []
    if fmp_key:
        provider_status.append({"provider": "FMP", "status": "active", "key_source": fmp_src})
    else:
        provider_status.append({"provider": "FMP", "status": "skipped_missing_key", "key_source": fmp_src})
    if fh_key:
        provider_status.append({"provider": "Finnhub", "status": "active", "key_source": fh_src})
    else:
        provider_status.append({"provider": "Finnhub", "status": "skipped_missing_key", "key_source": fh_src})

    hist_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    tickers = sorted(events["ticker"].astype(str).str.upper().unique())

    if ie.COMPACT_CACHE.exists():
        cache = pd.read_csv(ie.COMPACT_CACHE)
        hist_rows = cache.to_dict("records")
        provider_status.append({"provider": "local_cache", "status": "loaded", "n_rows": len(cache)})
    elif fh_key or fmp_key:
        for i, ticker in enumerate(tickers):
            if fh_key:
                rows, st = fetch_finnhub_history(ticker, fh_key)
                hist_rows.extend(rows)
                if st != "ok" and i == 0:
                    provider_status.append({"provider": "Finnhub", "status": st})
                time.sleep(0.25)
            if fmp_key:
                grades, st = fetch_fmp_grades(ticker, fmp_key)
                for g in grades:
                    hist_rows.append(
                        {
                            "ticker": ticker,
                            "record_date": g["record_date"],
                            "buy_count": 1 if "upgrade" in g.get("grade_action", "").lower() else 0,
                            "sell_count": 1 if "downgrade" in g.get("grade_action", "").lower() else 0,
                            "hold_count": 0,
                            "source": "fmp_grade",
                        }
                    )
                snap = fetch_fmp_consensus_snapshot(ticker, fmp_key)
                snapshot_rows.append({"ticker": ticker, **snap})
                time.sleep(0.25)
        if hist_rows:
            pd.DataFrame(hist_rows).drop_duplicates().to_csv(ie.COMPACT_CACHE, index=False)
    else:
        provider_status.append(
            {
                "provider": "all",
                "status": "SKIPPED",
                "reason": "Set FMP_API_KEY or FINNHUB_API_KEY in env or /root/.config/fin496/*.env",
            }
        )

    hist_df = pd.DataFrame(hist_rows) if hist_rows else pd.DataFrame()
    snap_map = {r["ticker"]: r for r in snapshot_rows}

    event_rows: list[dict[str, Any]] = []
    for _, ev in events.iterrows():
        ticker = str(ev["ticker"]).upper()
        th = hist_df[hist_df["ticker"] == ticker] if not hist_df.empty and "ticker" in hist_df.columns else pd.DataFrame()
        cls = classify_event(ev["event_date"], ev.get("recommendation_type", ""), th, snap_map.get(ticker), None)
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
                "event_time_historical_n": int((sub["analyst_data_mode"] == "event_time_historical").sum()),
                "diagnostic_only_n": int(sub["diagnostic_current_only"].sum()),
                "unknown_n": int((sub["analyst_alignment"] == "analyst_unknown").sum()),
            }
        )
    utils.write_csv(OUT / "analyst_relay_ticker_coverage.csv", coverage, list(coverage[0]) if coverage else ["ticker"])

    fwd = utils.forward_panel(["5D", "21D"])
    merged = fwd.merge(panel, on="event_id", how="left", suffixes=("", "_ar"))
    tick_col = "ticker" if "ticker" in merged.columns else "ticker_ar"
    summary_rows: list[dict] = []
    for align in panel["analyst_alignment"].dropna().unique():
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
                    **{k: stats[k] for k in ["n", "mean", "t_stat", "p_value"]},
                }
            )
    utils.write_csv(OUT / "returns_by_analyst_alignment.csv", summary_rows, list(summary_rows[0]) if summary_rows else ["sample"])

    event_time_n = int((panel["analyst_data_mode"] == "event_time_historical").sum())
    diag_n = int(panel["diagnostic_current_only"].sum())
    contrarian_n = int(panel["finfluencer_contrarian_to_analyst"].sum())
    mode_note = (
        "event-time historical classifications available"
        if event_time_n > 0
        else "**diagnostic current-only or unknown** — do not make historical analyst-alignment claims"
    )

    summary = f"""# Analyst relay layer

## Provider status
{utils.md_table(provider_status)}

## Coverage
- Events: **{len(panel)}**
- Event-time historical: **{event_time_n}**
- Diagnostic current-only: **{diag_n}**
- Contrarian-to-analyst (dated): **{contrarian_n}**

## Interpretation
{mode_note}

Analyst consensus is **not** public-news-clean. Unknown analyst coverage is **never clean**.
Latest-only snapshots are **diagnostic_current_only** and cannot support event-study causal claims.
"""
    utils.write_md(OUT / "analyst_relay_summary.md", "Analyst Relay Summary", summary)

    limits = """# Analyst relay limitations

- Free-tier APIs may lack full historical depth; undated consensus is diagnostic only.
- FMP grade history and Finnhub monthly recommendation bins are coarse.
- No Bloomberg; no guarantee of complete Wall Street coverage.
- Alignment buckets describe **co-movement with observable consensus**, not finfluencer skill.
- Unknown analyst state must not be treated as clean confound removal.
"""
    utils.write_md(OUT / "analyst_relay_limitations.md", "Analyst Relay Limitations", limits)
    print("Analyst relay layer complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
