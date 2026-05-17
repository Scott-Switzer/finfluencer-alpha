"""Creator ex-post taxonomy: skill-like vs momentum-rider vs antiskilled-like (non-causal)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("creator_skill_taxonomy")


def classify(row: pd.Series) -> str:
    n = int(row.get("n_events", 0))
    if n < 5:
        return "insufficient_sample"
    top5_share = float(row.get("top5_share", 0))
    b21 = float(row.get("mean_bhar_21d") or 0)
    b63 = float(row.get("mean_bhar_63d") or 0)
    prior21 = float(row.get("mean_prior_return_21d") or 0)
    non_top_share = 1.0 - top5_share
    if b63 < -0.03 and non_top_share > 0.4:
        return "antiskilled_like"
    if b21 > 0.02 and top5_share > 0.6 and prior21 > 0.02:
        return "momentum_rider"
    if b21 > 0.02 and top5_share < 0.5 and float(row.get("master_clean_share", 0)) > 0.05:
        return "skilled_like"
    if abs(b21) < 0.01:
        return "noisy_neutral"
    if b21 > 0:
        return "momentum_rider"
    return "noisy_neutral"


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        return 0
    panel = utils.forward_panel(["5D", "21D", "63D"])
    merged = events.merge(
        panel[panel["horizon"].isin(["5D", "21D", "63D"])][["event_id", "horizon", "spy_bhar"]],
        on="event_id",
        how="left",
    )
    rows: list[dict] = []
    for creator, grp in merged.groupby("creator"):
        wide = grp.pivot_table(index="event_id", columns="horizon", values="spy_bhar", aggfunc="first")
        base = grp.drop_duplicates("event_id")
        n = len(base)
        row = {
            "creator": creator,
            "n_events": n,
            "n_high_confidence": int(base.get("high_confidence", False).sum()),
            "buy_share": float((base["recommendation_type"] == "buy").mean()),
            "top5_share": float(base["top5_flag"].mean()),
            "non_top_share": float((~base["top5_flag"]).mean()),
            "mean_bhar_5d": wide["5D"].mean() if "5D" in wide else None,
            "mean_bhar_21d": wide["21D"].mean() if "21D" in wide else None,
            "mean_bhar_63d": wide["63D"].mean() if "63D" in wide else None,
            "hit_rate_21d": float((wide["21D"] > 0).mean()) if "21D" in wide else None,
            "downside_hit_21d": float((wide["21D"] < 0).mean()) if "21D" in wide else None,
            "mean_prior_return_21d": base["prior_return_21d"].mean(),
            "master_clean_share": float(base.get("master_clean", False).astype(str).str.lower().eq("true").mean())
            if "master_clean" in base.columns
            else 0.0,
        }
        row["taxonomy"] = classify(pd.Series(row))
        rows.append(row)

    tax = pd.DataFrame(rows).sort_values("n_events", ascending=False)
    tax.to_csv(OUT / "creator_skill_taxonomy.csv", index=False)

    counts = tax["taxonomy"].value_counts().to_dict()
    leaderboard = tax[tax["n_events"] >= 10].head(25)[
        ["creator", "n_events", "taxonomy", "mean_bhar_21d", "top5_share", "mean_prior_return_21d"]
    ]
    utils.write_md(
        OUT / "creator_skill_taxonomy_summary.md",
        "Creator Skill Taxonomy",
        f"""# Creator taxonomy (non-causal labels)

Counts: {counts}

**Hard rule:** labels are **skill-like** / **antiskilled-like**, never definitive skill.

- **momentum_rider:** positive raw returns concentrated in top-5 / prior momentum.
- **antiskilled_like:** negative medium-horizon returns with meaningful non-top exposure.
- **skilled_like:** positive returns with non-trivial non-top and some clean confound share (rare).
- **insufficient_sample:** n<5 events.

This supports finfluencer-heterogeneity literature (popularity ≠ skill) without claiming creator causality.
""",
    )
    utils.write_md(
        OUT / "creator_leaderboard_safe.md",
        "Creator Leaderboard (Safe)",
        "## Top creators by event count (descriptive only)\n\n" + utils.md_table(leaderboard.to_dict("records")),
    )
    print("Creator skill taxonomy complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
