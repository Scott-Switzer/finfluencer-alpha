"""Long-horizon claim controls: 504D evidence flagged thin / diagnostic only."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "long_horizon_claim_controls"
THIN_N = 80


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = utils.long_panel()
    fwd = panel[(panel["window_type"] == "forward") & panel["horizon"].isin(["252D", "504D", "126D", "63D"])].copy()
    fwd = fwd.drop_duplicates(subset=["event_id", "horizon"], keep="first")

    rows = []
    for horizon, group in fwd.groupby("horizon"):
        g = group[group["status"].eq("computed")]
        n = len(g)
        cens = int(g["right_censored"].astype(str).str.lower().eq("true").sum()) if "right_censored" in g.columns else 0
        bh = g["spy_bhar"].dropna()
        mean_b = float(bh.mean()) if len(bh) else float("nan")
        thin = n < THIN_N or (str(horizon) == "504D" and n < int(THIN_N * 1.5))
        claim_tier = "downgraded_diagnostic_only" if thin else "usable_with_overlap_caveats"
        rows.append(
            {
                "horizon": horizon,
                "n_computed": n,
                "right_censored_count": cens,
                "mean_spy_bhar": utils.fmt(mean_b),
                "thin_sample_flag": thin,
                "claim_tier": claim_tier,
            }
        )

    utils.write_csv(OUT_DIR / "01_long_horizon_claim_controls.csv", rows, list(rows[0]) if rows else ["horizon"])
    utils.table_pair(OUT_DIR / "02_long_horizon_claim_summary", rows, "Long Horizon Claim Controls")

    top = fwd[(fwd["horizon"] == "504D") & fwd["top5_flag"].astype(str).str.lower().eq("true") & fwd["status"].eq("computed")]
    ntop = fwd[(fwd["horizon"] == "504D") & ~fwd["top5_flag"].astype(str).str.lower().eq("true") & fwd["status"].eq("computed")]
    contrast = [
        {
            "slice": "504D_top5",
            "n": len(top),
            "mean_spy_bhar": utils.fmt(float(top["spy_bhar"].mean())) if len(top) else "",
            "thin": len(top) < THIN_N,
        },
        {
            "slice": "504D_non_top",
            "n": len(ntop),
            "mean_spy_bhar": utils.fmt(float(ntop["spy_bhar"].mean())) if len(ntop) else "",
            "thin": len(ntop) < THIN_N,
        },
    ]
    utils.write_csv(
        OUT_DIR / "03_504d_top_vs_non_top.csv",
        contrast,
        list(contrast[0]) if contrast else ["slice", "n", "mean_spy_bhar", "thin"],
    )

    memo = f"""# Long-horizon claim controls

504D and very long windows are **diagnostic**, not standalone alpha claims. Thin effective sample (`n<{THIN_N}` baseline, stricter for 504D) forces **downgraded** language: cite only with overlap, censoring, and confound caveats.

Non-top 504D weakness is expected to be **noisier** than medium horizons; do not stack long-horizon non-top signals without manual data validation.
"""
    utils.write_md(OUT_DIR / "04_claim_language_guardrails.md", "Claim Language Guardrails", memo)
    print("Long-horizon claim controls complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
