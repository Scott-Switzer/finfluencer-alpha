"""Short-horizon pop vs medium-horizon reversal tests."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("reversal_overreaction")


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        return 0
    events["short_pop_5d"] = events["post_bhar_5d"] > 0
    events["subsequent_21d"] = events.get("forward_spy_bhar_21d")
    events["subsequent_63d"] = events.get("forward_spy_bhar_63d")
    events["reversal_21d_after_pop"] = events["short_pop_5d"] & (events["subsequent_21d"] < 0)
    events.to_csv(OUT / "reversal_overreaction_panel.csv", index=False)

    rows: list[dict] = []
    events["top5_flag"] = events["top5_flag"].astype(bool)
    for label, mask in [
        ("all_positive_5d", events["short_pop_5d"]),
        ("top5_positive_5d", events["short_pop_5d"] & events["top5_flag"]),
        ("non_top_positive_5d", events["short_pop_5d"] & ~events["top5_flag"]),
        ("high_conf_positive_5d", events["short_pop_5d"] & events["high_confidence"].fillna(False).astype(bool)),
    ]:
        sub = events.loc[mask]
        for horizon_col, horizon in [("subsequent_21d", "21D"), ("subsequent_63d", "63D")]:
            vals = sub[horizon_col].dropna().astype(float).tolist()
            stats = utils.t_stats(vals)
            rows.append(
                {
                    "sample": label,
                    "follow_on_horizon": horizon,
                    "n": stats["n"],
                    "mean_bhar": stats["mean"],
                    "t_stat": stats["t_stat"],
                    "p_value": stats["p_value"],
                    "reversal_rate": sum(v < 0 for v in vals) / len(vals) if vals else None,
                }
            )

    pop = events[events["short_pop_5d"]]
    summary = f"""# Reversal / overreaction

## Design
Events with **positive 5D** abnormal returns are tracked for subsequent **21D/63D** SPY BHAR.

## Headline counts
- Events with 5D pop: **{int(events['short_pop_5d'].sum())}**
- Pop then negative 21D: **{int(events['reversal_21d_after_pop'].sum())}**

## Non-top vs top-5 (after 5D pop)
- Non-top mean subsequent 21D BHAR: **{pop.loc[~pop['top5_flag'], 'subsequent_21d'].mean():.4f}**
- Top-5 mean subsequent 21D BHAR: **{pop.loc[pop['top5_flag'], 'subsequent_21d'].mean():.4f}**

## Interpretation
Short-term attention pops that **fade** at medium horizons—especially outside top-5 names—support overreaction/attention narratives rather than durable alpha. This **does not** prove mechanical reversibility for trading.
"""
    utils.write_md(OUT / "reversal_overreaction_summary.md", "Reversal Overreaction Summary", summary)
    print("Reversal overreaction tests complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
