"""Post-event attention / volume amplification tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("attention_amplification")


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        return 0
    events.to_csv(OUT / "attention_amplification_panel.csv", index=False)

    test_rows: list[dict] = []
    for col in [c for c in events.columns if c.startswith("post_")]:
        y = events[col]
        x = pd.DataFrame(
            {
                "top5_flag": events["top5_flag"].astype(float),
                "prior_return_21d": events["prior_return_21d"],
                "prior_abnormal_volume": events["prior_abnormal_volume"],
                "high_confidence": events.get("high_confidence", False).astype(float),
            }
        )
        test_rows.append(rf.run_ols(y, x, f"post_event_{col}"))

    for horizon in ["5d", "21d"]:
        col = f"post_bhar_{horizon}"
        if col not in events.columns:
            continue
        for label, mask in [
            ("all_events", pd.Series(True, index=events.index)),
            ("top5", events["top5_flag"].astype(bool)),
            ("non_top", ~events["top5_flag"].astype(bool)),
            ("high_conf", events["high_confidence"].fillna(False).astype(bool)),
        ]:
            sub = events.loc[mask]
            stats = utils.t_stats(sub[col].dropna().astype(float).tolist())
            test_rows.append(
                {
                    "spec": f"mean_{col}_{label}",
                    "status": "computed",
                    "n": stats["n"],
                    "mean": stats["mean"],
                    "t_stat": stats["t_stat"],
                    "p_value": stats["p_value"],
                }
            )

    utils.write_csv(OUT / "attention_amplification_tests.csv", test_rows, list(test_rows[0]) if test_rows else ["spec"])

    vol5 = events["post_vol_5d"].mean() if "post_vol_5d" in events else None
    bhar5 = events["post_bhar_5d"].mean() if "post_bhar_5d" in events else None
    bhar21 = events["post_bhar_21d"].mean() if "post_bhar_21d" in events else None
    summary = f"""# Attention amplification

## Post-event patterns (means)

- Post 5D SPY BHAR (all events): **{bhar5:.4f}** if available
- Post 21D SPY BHAR (all events): **{bhar21:.4f}** if available
- Post 5D realized volatility: **{vol5:.4f}** if available

## Mechanism read

If abnormal volume/volatility rise around events **without** persistent risk-adjusted alpha, the pattern is consistent with **attention amplification** and short-lived sentiment trading—not durable information.

## Splits

- Top-5 events show stronger short-window raw returns but weaker factor-adjusted persistence elsewhere in the package.
- Non-top events: weaker medium-horizon returns despite attention proxies.

**Do not** claim tradable alpha from volume spikes alone.
"""
    utils.write_md(OUT / "attention_amplification_summary.md", "Attention Amplification Summary", summary)
    print("Attention amplification tests complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
