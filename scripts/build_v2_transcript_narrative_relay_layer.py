"""Transcript evidence-window narrative relay scores (no full transcript export)."""

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

OUT = ie.info_dir("transcript_narrative_relay")


def score_bucket(series: pd.Series, col: str) -> pd.Series:
    med = series.median()
    return pd.Series(
        np.where(series >= max(med, 1), f"high_{col}", np.where(series > 0, f"low_{col}", f"none_{col}")),
        index=series.index,
    )


def main() -> int:
    events = rf.build_event_feature_table()
    text = ie.load_evidence_text()
    if events.empty:
        return 0
    merged = events.merge(text, on="event_id", how="left")
    scores = merged["evidence_window"].fillna("").map(ie.narrative_relay_scores)
    score_df = pd.DataFrame(scores.tolist(), index=merged.index)
    panel = pd.concat([merged[["event_id", "ticker", "top5_flag", "recommendation_type", "high_confidence"]], score_df], axis=1)
    panel.to_csv(OUT / "transcript_narrative_relay_event_panel.csv", index=False)

    fwd = utils.forward_panel(["5D", "21D"])
    test = fwd.merge(panel, on="event_id", how="left")
    rows: list[dict] = []
    for col in [
        "analyst_relay_score",
        "retail_hype_score",
        "urgency_score",
        "valuation_score",
        "risk_score",
        "market_move_relay_score",
    ]:
        if col not in test.columns:
            continue
        test[f"{col}_bucket"] = score_bucket(test[col].fillna(0), col.replace("_score", ""))
        for horizon in ["5D", "21D"]:
            for bucket, grp in test.groupby(f"{col}_bucket"):
                sub = grp[grp["horizon"] == horizon]
                for sample, mask in [
                    ("full", pd.Series(True, index=sub.index)),
                    ("non_top", ~sub.get("ticker", sub.get("ticker_x", pd.Series())).isin(utils.TOP5)),
                ]:
                    g = sub.loc[mask]
                    stats = utils.t_stats(g["spy_bhar"].dropna().astype(float).tolist())
                    rows.append(
                        {
                            "score": col,
                            "bucket": bucket,
                            "sample": sample,
                            "horizon": horizon,
                            "n": stats["n"],
                            "mean_spy_bhar": stats["mean"],
                            "t_stat": stats["t_stat"],
                        }
                    )

    utils.write_csv(OUT / "transcript_narrative_relay_tests.csv", rows, list(rows[0]) if rows else ["score"])

    tick = test["ticker"] if "ticker" in test.columns else test.get("ticker_x", pd.Series(index=test.index))
    high_hype_non_top = test[(test["retail_hype_score"].fillna(0) >= 2) & (~tick.isin(utils.TOP5))]
    sub21 = high_hype_non_top[high_hype_non_top["horizon"] == "21D"]
    stats_h = utils.t_stats(sub21["spy_bhar"].dropna().astype(float).tolist())

    summary = f"""# Transcript narrative relay

- Events with evidence snippets: **{int(panel['analyst_relay_score'].notna().sum())}**
- High hype + non-top 21D n={stats_h['n']}, mean SPY BHAR={stats_h['mean']}

## Interpretation
Relay language (analyst/earnings/news/market-move keywords) tests whether finfluencer speech **repackages public narratives**.
Higher hype/urgency buckets are examined for **weaker** incremental returns, especially among non-top names.
Snippet scores are **exploratory** — not causal skill measures.
"""
    utils.write_md(OUT / "transcript_narrative_relay_summary.md", "Transcript Narrative Relay", summary)
    print("Transcript narrative relay layer complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
