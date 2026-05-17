"""Market sentiment regime conditioning (VIX, SPY/QQQ trend, drawdowns) — not causal identification."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = ie.info_dir("market_sentiment")


def vix_tercile(vix_level: float, edges: tuple[float, float]) -> str:
    if vix_level <= edges[0]:
        return "vix_low_tercile"
    if vix_level <= edges[1]:
        return "vix_mid_tercile"
    return "vix_high_tercile"


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        return 0

    spy = ie.spy_benchmark_series()
    vix = ie.vix_proxy_series()
    qqq = ie.qqq_series()
    aii_status = "skipped_no_cache"
    aii_path = OUT / "_aaii_compact.csv"
    aii = pd.DataFrame()
    if aii_path.exists():
        aii = pd.read_csv(aii_path)
        aii_status = "loaded_local_cache"
        if "report_date" in aii.columns and "bullish_pct" in aii.columns:
            aii["report_date"] = pd.to_datetime(aii["report_date"], errors="coerce").dt.date

    event_feats: list[dict] = []
    vix_levels = []
    for _, ev in events.iterrows():
        ed = ie.parse_iso_date(ev["event_date"])
        if not ed:
            continue
        feat = ie.features_on_date(ed, spy, vix, qqq if not qqq.empty else None)
        feat["event_id"] = ev["event_id"]
        feat["ticker"] = ev["ticker"]
        feat["top5_flag"] = ev.get("top5_flag")
        feat["high_confidence"] = ev.get("high_confidence")
        if aii_path.exists() and "report_date" in aii.columns:
            prior = aii[aii["report_date"] <= ed].tail(1)
            if not prior.empty:
                feat["aaii_bullish"] = float(prior.iloc[0]["bullish_pct"])
                feat["aaii_bearish"] = float(prior.iloc[0].get("bearish_pct", np.nan))
                feat["aaii_bull_bear_spread"] = feat["aaii_bullish"] - feat.get("aaii_bearish", np.nan)
                feat["high_retail_bullishness"] = bool(feat["aaii_bullish"] > 45)
        if feat.get("vix_level") is not None:
            vix_levels.append(float(feat["vix_level"]))
        event_feats.append(feat)

    panel = pd.DataFrame(event_feats)
    if vix_levels:
        e1, e2 = np.quantile(vix_levels, [1 / 3, 2 / 3])
        panel["vix_tercile"] = panel["vix_level"].apply(
            lambda x: vix_tercile(float(x), (e1, e2)) if pd.notna(x) else "vix_unknown"
        )
    else:
        panel["vix_tercile"] = "vix_unknown"

    panel["spy_trend_regime"] = panel["spy_prior_21d_return"].apply(
        lambda x: "spy_uptrend_21d"
        if pd.notna(x) and x > 0.01
        else ("spy_downtrend_21d" if pd.notna(x) and x < -0.01 else "spy_flat_21d")
    )
    panel.to_csv(OUT / "market_sentiment_event_panel.csv", index=False)

    fwd = utils.forward_panel(["5D", "21D", "63D"])
    merged = fwd.merge(panel, on="event_id", how="left", suffixes=("", "_ms"))
    tick_col = "ticker" if "ticker" in merged.columns else "ticker_ms"
    merged["top5_flag"] = merged[tick_col].isin(utils.TOP5)

    rows: list[dict] = []
    for regime_col in ["vix_tercile", "sentiment_regime", "spy_trend_regime"]:
        if regime_col not in merged.columns:
            continue
        for horizon in ["5D", "21D"]:
            for sample, mask in [
                ("full", pd.Series(True, index=merged.index)),
                ("top5", merged["top5_flag"]),
                ("non_top", ~merged["top5_flag"]),
            ]:
                sub = merged.loc[mask & (merged["horizon"] == horizon)]
                for bucket, grp in sub.groupby(regime_col, dropna=False):
                    stats = utils.t_stats(grp["spy_bhar"].dropna().astype(float).tolist())
                    rows.append(
                        {
                            "regime_variable": regime_col,
                            "bucket": str(bucket),
                            "sample": sample,
                            "horizon": horizon,
                            "n": stats["n"],
                            "mean_spy_bhar": stats["mean"],
                            "t_stat": stats["t_stat"],
                            "p_value": stats["p_value"],
                        }
                    )

    # Interactions: top5×risk_on, non_top×risk_off, hype proxy via high retail bullishness
    text = ie.load_evidence_text()
    if not text.empty:
        scores = text.set_index("event_id")["evidence_window"].fillna("").map(ie.narrative_relay_scores)
        hype = pd.Series({k: v["retail_hype_score"] for k, v in scores.items()})
        merged["high_hype"] = merged["event_id"].map(hype).fillna(0) >= 2
    for label, mask in [
        ("top5_risk_on", merged["top5_flag"] & (merged.get("sentiment_regime") == "risk_on")),
        ("non_top_risk_off", (~merged["top5_flag"]) & (merged.get("sentiment_regime") == "risk_off")),
        ("high_hype_risk_on", merged.get("high_hype", False) & (merged.get("sentiment_regime") == "risk_on")),
    ]:
        sub = merged.loc[mask & (merged["horizon"] == "21D")]
        stats = utils.t_stats(sub["spy_bhar"].dropna().astype(float).tolist())
        rows.append(
            {
                "regime_variable": "interaction",
                "bucket": label,
                "sample": "conditional",
                "horizon": "21D",
                "n": stats["n"],
                "mean_spy_bhar": stats["mean"],
                "t_stat": stats["t_stat"],
                "p_value": stats["p_value"],
            }
        )

    utils.write_csv(OUT / "returns_by_market_sentiment_regime.csv", rows, list(rows[0]) if rows else ["bucket"])
    utils.write_md(OUT / "returns_by_market_sentiment_regime.md", "Returns by Sentiment Regime", utils.md_table(rows[:40]))

    vix_src = vix["vix_source"].iloc[0] if not vix.empty and "vix_source" in vix.columns else "none"
    summary = f"""# Market sentiment regime layer

- VIX source: **{vix_src}**
- AAII: **{aii_status}** (optional local cache at `_aaii_compact.csv`)
- Events tagged: **{len(panel)}**

## Required reading
Sentiment regimes are **conditioning variables** for heterogeneity — not causal identification of finfluencer skill.

### Non-top underperformance by regime
Inspect `returns_by_market_sentiment_regime.csv` for `sample=non_top` and `horizon=21D`.

Market-implied quiet (separate layer): non-top + market_quiet 21D SPY BHAR ≈ **-0.56%** — sensitivity only, **not** public-news-clean.
"""
    utils.write_md(OUT / "market_sentiment_summary.md", "Market Sentiment Summary", summary)
    print("Market sentiment regime layer complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
