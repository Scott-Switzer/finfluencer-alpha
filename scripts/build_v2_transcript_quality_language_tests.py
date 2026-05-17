"""Transcript language-style scores vs outcomes (evidence_window text only; no full transcript export)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("transcript_language_quality")


def main() -> int:
    events = rf.build_event_feature_table()
    text = rf.load_evidence_text()
    if events.empty:
        return 0
    events = events.merge(text, on="event_id", how="left")
    scores = events["evidence_window"].fillna("").map(rf.language_scores)
    score_df = pd.DataFrame(scores.tolist(), index=events.index)
    panel = pd.concat([events, score_df], axis=1)
    panel.to_csv(OUT / "transcript_language_quality_panel.csv", index=False)

    test_rows: list[dict] = []
    for score_col in score_df.columns:
        for ycol in ["forward_spy_bhar_5d", "forward_spy_bhar_21d", "forward_spy_bhar_63d"]:
            if ycol not in panel.columns:
                continue
            test_rows.append(rf.run_ols(panel[ycol], panel[[score_col]], f"{ycol}_on_{score_col}"))

    for score_col in ["hype_score", "risk_warning_score", "disclosure_score"]:
        hi = panel[score_col] >= panel[score_col].median()
        for ycol in ["forward_spy_bhar_21d"]:
            if ycol not in panel.columns:
                continue
            a = panel.loc[hi, ycol].dropna()
            b = panel.loc[~hi, ycol].dropna()
            sa, sb = utils.t_stats(a.astype(float).tolist()), utils.t_stats(b.astype(float).tolist())
            test_rows.append(
                {
                    "spec": f"high_vs_low_{score_col}_{ycol}",
                    "high_n": sa["n"],
                    "high_mean": sa["mean"],
                    "low_n": sb["n"],
                    "low_mean": sb["mean"],
                }
            )

    utils.write_csv(
        OUT / "transcript_language_quality_tests.csv",
        test_rows,
        list(test_rows[0]) if test_rows else ["spec"],
    )

    covered = int(panel["evidence_window"].notna().sum())
    summary = f"""# Transcript language quality

- Events with evidence-window text: **{covered}** / {len(panel)}
- Scores: hype, risk-warning, disclosure, valuation, technical, urgency, ambiguity (counts in evidence snippet only).

## Interpretation
Higher **hype/urgency** scores are examined for association with weaker follow-on returns; higher **risk-warning/disclosure** scores for investor-protection framing. Associations are **descriptive**; snippet text is not exported to git.

No full-transcript collection was performed in this pass.
"""
    utils.write_md(OUT / "transcript_language_quality_summary.md", "Transcript Language Quality", summary)
    print("Transcript language quality tests complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
