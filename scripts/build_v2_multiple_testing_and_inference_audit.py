"""Multiple-testing correction and coarse inference robustness."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "inference_robustness"


def holm_adjust(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [1.0] * m
    prev = 0.0
    for rank, idx in enumerate(order, start=1):
        val = min(1.0, pvals[idx] * (m - rank + 1))
        val = max(val, prev)
        adj[idx] = val
        prev = val
    return adj


def bh_fdr(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [1.0] * m
    prev = 1.0
    for rank, idx in reversed(list(enumerate(order, start=1))):
        val = min(prev, pvals[idx] * m / rank)
        q[idx] = val
        prev = val
    return q


def collect_pvalues() -> list[dict]:
    rows: list[dict] = []
    candidates = [
        (utils.OUT_DIR / "confounds_expanded/03_v2_clean_confounded_unknown_return_summary_expanded.csv", "confounds"),
        (utils.OUT_DIR / "market_implied_confounds/returns_by_market_confound_bucket.csv", "market_implied"),
        (utils.OUT_DIR / "research_frontier/placebo_matched_controls/placebo_matched_control_results.csv", "placebo"),
        (utils.OUT_DIR / "research_frontier/recommendation_selection/recommendation_selection_regressions.csv", "selection"),
    ]
    for path, family in candidates:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        pcol = next((c for c in df.columns if "p_value" in c.lower() or c == "p_value"), None)
        if not pcol:
            continue
        for _, r in df.iterrows():
            p = utils.clean_float(r.get(pcol))
            if p is None:
                continue
            label = "_".join(str(r.get(c, "")) for c in df.columns[:4])
            rows.append(
                {
                    "test_family": family,
                    "test_label": label[:120],
                    "p_value": p,
                    "classification": "exploratory" if family in {"selection", "placebo"} else "primary",
                }
            )
    return rows


def jackknife_by(col: str) -> list[dict]:
    panel = utils.forward_panel(["5D", "21D"])
    panel = panel[panel["status"] == "computed"]
    if col not in panel.columns:
        return []
    rows = []
    for horizon in ["5D", "21D"]:
        sub = panel[panel["horizon"] == horizon]
        groups = sub.groupby(col)["spy_bhar"]
        full = utils.t_stats(sub["spy_bhar"].dropna().astype(float).tolist())
        for g, _grp in groups:
            leave = sub[sub[col] != g]
            st = utils.t_stats(leave["spy_bhar"].dropna().astype(float).tolist())
            rows.append(
                {
                    "cluster": col,
                    "group_left_out": g,
                    "horizon": horizon,
                    "n_full": full["n"],
                    "mean_full": full["mean"],
                    "mean_leave_one": st["mean"],
                    "influence": None if full["mean"] is None or st["mean"] is None else full["mean"] - st["mean"],
                }
            )
    return rows


def bootstrap_cluster(col: str, n_draw: int = 200) -> list[dict]:
    panel = utils.forward_panel(["5D", "21D"])
    panel = panel[(panel["status"] == "computed") & (panel["horizon"] == "21D")]
    if col not in panel.columns or panel.empty:
        return []
    rng = np.random.default_rng(496)
    groups = list(panel.groupby(col))
    means = []
    for _ in range(n_draw):
        sampled = [groups[rng.integers(0, len(groups))][1] for _ in range(len(groups))]
        vals = pd.concat(sampled)["spy_bhar"].dropna().astype(float).tolist()
        if vals:
            means.append(float(np.mean(vals)))
    if not means:
        return []
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [
        {
            "method": f"cluster_bootstrap_{col}",
            "horizon": "21D",
            "n_draws": n_draw,
            "mean_bhar": float(np.mean(means)),
            "ci_2.5": float(lo),
            "ci_97.5": float(hi),
        }
    ]


def winsorized_stats() -> list[dict]:
    panel = utils.forward_panel(["5D", "21D"])
    rows = []
    for horizon in ["5D", "21D"]:
        sub = panel[(panel["horizon"] == horizon) & (panel["status"] == "computed")]
        for label, lo, hi in [("raw", 0, 1), ("winsor_1_99", 0.01, 0.99), ("winsor_5_95", 0.05, 0.95)]:
            ser = sub["spy_bhar"].astype(float)
            if label != "raw":
                ser = utils.winsorize(ser, lo, hi)
            st = utils.t_stats(ser.dropna().tolist())
            rows.append({"horizon": horizon, "spec": label, "mean": st["mean"], "t_stat": st["t_stat"], "p_value": st["p_value"], "n": st["n"]})
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tests = collect_pvalues()
    if tests:
        pvals = [float(t["p_value"]) for t in tests]
        holm = holm_adjust(pvals)
        fdr = bh_fdr(pvals)
        for i, t in enumerate(tests):
            t["holm_p"] = holm[i]
            t["fdr_q"] = fdr[i]
            t["survives_fdr_10pct"] = fdr[i] <= 0.10
            t["survives_holm_5pct"] = holm[i] <= 0.05
        utils.write_csv(OUT / "multiple_testing_audit.csv", tests, list(tests[0]))
        utils.write_md(
            OUT / "multiple_testing_audit.md",
            "Multiple Testing Audit",
            f"Collected **{len(tests)}** p-values. "
            f"Survive FDR 10%: **{sum(t['survives_fdr_10pct'] for t in tests)}**. "
            "Exploratory families labeled explicitly.",
        )

    jack = jackknife_by("ticker") + jackknife_by("creator")
    utils.write_csv(OUT / "jackknife_influence.csv", jack, list(jack[0]) if jack else ["cluster"])
    utils.write_md(OUT / "jackknife_influence.md", "Jackknife Influence", utils.md_table(jack[:30]))

    boot = bootstrap_cluster("ticker") + bootstrap_cluster("creator")
    utils.write_csv(OUT / "bootstrap_inference_summary.csv", boot, list(boot[0]) if boot else ["method"])
    utils.write_md(OUT / "bootstrap_inference_summary.md", "Bootstrap Summary", utils.md_table(boot))

    win = winsorized_stats()
    utils.write_csv(OUT / "winsorized_return_checks.csv", win, list(win[0]) if win else ["horizon"])

    print("Multiple testing and inference audit complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
