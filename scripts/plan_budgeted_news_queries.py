"""Budgeted news query planner: collapse events into provider/ticker/week buckets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "news_confound_master" / "query_plan"
CANARY = utils.OUT_DIR / "news_confound_master" / "provider_canaries" / "provider_canary_status.csv"
PANEL = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"

DEFAULT_CAPS = {
    "marketaux": 50,
    "massive_polygon": 30,
    "alpaca_news": 50,
    "eodhd": 10,
    "newsapi": 5,
    "gdelt_doc_api": 10,
    "fmp_stock_news": 3,
    "finnhub": 10,
    "alpha_vantage_news_sentiment": 10,
}


def canary_proceed_map() -> dict[str, bool]:
    if not CANARY.exists():
        return {k: False for k in DEFAULT_CAPS}
    frame = pd.read_csv(CANARY)
    out: dict[str, bool] = {}
    for provider in frame["provider"].unique():
        sub = frame[frame["provider"] == provider]
        p = sub["proceed"].astype(str).str.lower()
        out[str(provider)] = bool(p.isin(["yes", "skip_if_historical"]).any())
    return out


def priority_score(row: pd.Series, top5: set[str]) -> int:
    """Lower is higher priority."""
    t = str(row.get("ticker", "")).upper()
    news = str(row.get("news_clean_status", "unknown_news_coverage"))
    unknown = 1 if "unknown" in news else 0
    align = str(row.get("analyst_alignment_event_time", ""))
    top = 1 if t in top5 else 0
    bullish = 1 if "bullish_aligned" in align else 0
    p = unknown * 1 + (1 - top) * 10 + (1 - bullish) * 5
    try:
        ret = abs(float(row.get("spy_bhar_5d", 0) or 0))
        import math
        if math.isnan(ret):
            ret = 0.0
    except (TypeError, ValueError):
        ret = 0.0
    p -= min(ret * 2, 8)
    p = int(p) if p == p else 0
    return int(p)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-skipped", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    manifest = utils.event_manifest().copy()
    manifest["event_date_dt"] = pd.to_datetime(manifest["event_date"], errors="coerce")
    manifest["iso_year_week"] = manifest["event_date_dt"].dt.strftime("%G-W%V")

    top5 = utils.TOP5
    panel_cols = ["news_clean_status", "analyst_alignment_event_time", "provider_success_count"]
    if PANEL.exists():
        pg = pd.read_csv(PANEL)
        cols = ["event_id"] + [c for c in panel_cols if c in pg.columns]
        manifest = manifest.merge(pg[cols], on="event_id", how="left")
    else:
        manifest["news_clean_status"] = "unknown_news_coverage"
        manifest["analyst_alignment_event_time"] = ""

    if "forward_returns" not in manifest.columns:
        long = utils.forward_panel(["5D"])
        if not long.empty and "event_id" in long.columns:
            m5 = long[long["horizon"].eq("5D") & long["status"].eq("computed")][["event_id", "spy_bhar"]].rename(
                columns={"spy_bhar": "spy_bhar_5d"}
            )
            manifest = manifest.merge(m5, on="event_id", how="left")

    manifest["bucket_priority"] = manifest.apply(lambda r: priority_score(r, top5), axis=1)
    manifest = manifest.sort_values(["bucket_priority", "event_date", "event_id"])

    proceed = canary_proceed_map()
    planned: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    usage = {k: 0 for k in DEFAULT_CAPS}

    for provider, cap in DEFAULT_CAPS.items():
        if not proceed.get(provider, False):
            skipped.append({"provider": provider, "reason": "canary_did_not_proceed_or_missing", "calls": 0})
            continue
        sub = manifest.copy()
        if provider == "newsapi":
            sub = sub[sub["event_date_dt"].dt.year >= 2024]
        sub = sub.sort_values("bucket_priority")
        if provider == "gdelt_doc_api":
            u = sub.drop_duplicates(["ticker", "iso_year_week"]).head(cap)
            for _, row0 in u.iterrows():
                planned.append(
                    {
                        "provider": provider,
                        "ticker": row0["ticker"],
                        "iso_year_week": row0["iso_year_week"],
                        "event_id_anchor": int(row0["event_id"]),
                        "priority_score": int(row0["bucket_priority"]),
                        "planned_calls": 1,
                        "collapse": "ticker_week_gdelt",
                    }
                )
                usage[provider] += 1
            continue

        grouped = sub.groupby(["ticker", "iso_year_week"])["bucket_priority"].min().sort_values()
        for (ticker, week), _prio in grouped.items():
            if pd.isna(week):
                continue
            if usage[provider] >= cap:
                break
            g = sub[(sub["ticker"] == ticker) & (sub["iso_year_week"] == week)]
            if g.empty:
                continue
            row0 = g.iloc[0]
            planned.append(
                {
                    "provider": provider,
                    "ticker": row0["ticker"],
                    "iso_year_week": week,
                    "event_id_anchor": int(row0["event_id"]),
                    "priority_score": int(row0["bucket_priority"]),
                    "planned_calls": 1,
                    "collapse": "ticker_week",
                }
            )
            usage[provider] += 1

    plan = pd.DataFrame(planned)
    plan.to_csv(OUT / "budgeted_news_query_plan.csv", index=False)

    summary = f"""# Budgeted news query plan

Providers capped per defaults; NewsAPI recent-years only; buckets are provider+ticker+ISO week.

Planned rows: **{len(plan)}**

## Canary proceed map

- marketaux: {proceed.get('marketaux', False)}
- massive_polygon: {proceed.get('massive_polygon', False)}
- alpaca_news: {proceed.get('alpaca_news', False)}
- eodhd: {proceed.get('eodhd', False)}
- newsapi: {proceed.get('newsapi', False)}
- finnhub: {proceed.get('finnhub', False)}
- fmp_stock_news: {proceed.get('fmp_stock_news', False)}
- alpha_vantage_news_sentiment: {proceed.get('alpha_vantage_news_sentiment', False)}
- gdelt_doc_api: {proceed.get('gdelt_doc_api', False)}
"""
    (OUT / "budgeted_news_query_plan_summary.md").write_text(summary, encoding="utf-8")
    if args.write_skipped or skipped:
        pd.DataFrame(skipped).to_csv(OUT / "skipped_queries_due_to_budget.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
