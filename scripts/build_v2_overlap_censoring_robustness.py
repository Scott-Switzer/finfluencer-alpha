from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "overlap_censoring_robustness"


def bool_col(frame: pd.DataFrame, col: str) -> pd.Series:
    return frame[col].astype(str).str.lower().eq("true")


def select_non_overlap(frame: pd.DataFrame, gap: int, rule: str) -> pd.DataFrame:
    base = frame[frame["horizon"].eq(f"{gap}D")].copy()
    base["event_date_dt"] = pd.to_datetime(base["event_date"], errors="coerce")
    if rule == "highest_confidence":
        base = base.sort_values(["ticker", "event_date_dt", "actionability_score"], ascending=[True, True, False])
    elif rule == "random_seed":
        base = base.sample(frac=1.0, random_state=496).sort_values(["ticker", "event_date_dt"])
    else:
        base = base.sort_values(["ticker", "event_date_dt", "event_id"])
    keep = []
    last_by_ticker = {}
    for _, row in base.iterrows():
        d = row.event_date_dt
        if pd.isna(d):
            continue
        last = last_by_ticker.get(row.ticker)
        if last is None or (d - last).days >= gap:
            keep.append(int(row.event_id))
            last_by_ticker[row.ticker] = d
    return frame[frame["event_id"].isin(keep)]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = utils.forward_panel()
    non_rows = []
    for gap in [21, 63, 126]:
        for rule in ["earliest", "highest_confidence", "random_seed"]:
            selected = select_non_overlap(panel, gap, rule)
            non_rows.extend(
                utils.summarize_return_panel(
                    selected,
                    "spy_bhar",
                    {f"non_overlap_{gap}d_{rule}": pd.Series(True, index=selected.index)},
                    [f"{gap}D"],
                )
            )
    utils.table_pair(OUT_DIR / "01_non_overlapping_summary", non_rows, "Non-Overlapping Summary")
    cens_rows = []
    for label, mask in {
        "all_rows_including_censored": pd.Series(True, index=panel.index),
        "full_window_only": ~bool_col(panel, "right_censored"),
        "events_with_252d_full_window": panel["event_id"].isin(
            set(panel[(panel["horizon"].eq("252D")) & (~bool_col(panel, "right_censored"))]["event_id"])
        ),
        "events_with_504d_full_window": panel["event_id"].isin(
            set(panel[(panel["horizon"].eq("504D")) & (~bool_col(panel, "right_censored"))]["event_id"])
        ),
    }.items():
        cens_rows.extend(utils.summarize_return_panel(panel[mask], "spy_bhar", {label: pd.Series(True, index=panel[mask].index)}))
    utils.table_pair(OUT_DIR / "02_censoring_summary", cens_rows, "Censoring Summary")
    loo_rows = []
    baseline = panel[panel["horizon"].eq("63D")]
    for field in ["ticker", "creator"]:
        for value in baseline[field].dropna().unique():
            selected = baseline[baseline[field] != value]
            stats = utils.t_stats(selected["spy_bhar"].dropna().tolist())
            loo_rows.append(
                {
                    "leave_one_field": field,
                    "removed": value,
                    "horizon": "63D",
                    "n": stats["n"],
                    "mean_pct": utils.fmt_pct(stats["mean"]),
                    "t_stat": utils.fmt(stats["t_stat"], 3),
                    "p_value": utils.fmt(stats["p_value"]),
                }
            )
    utils.table_pair(OUT_DIR / "03_leave_one_out_summary", loo_rows, "Leave One Out Summary")
    outlier_rows = []
    for horizon in utils.HORIZONS:
        group = panel[panel["horizon"].eq(horizon)].copy()
        group["winsor_spy_bhar"] = utils.winsorize(group["spy_bhar"])
        for col, name in [("spy_bhar", "raw"), ("winsor_spy_bhar", "winsor_1_99")]:
            stats = utils.t_stats(group[col].dropna().tolist())
            outlier_rows.append(
                {
                    "sample": name,
                    "horizon": horizon,
                    "n": stats["n"],
                    "mean_pct": utils.fmt_pct(stats["mean"]),
                    "median_pct": utils.fmt_pct(stats["median"]),
                    "t_stat": utils.fmt(stats["t_stat"], 3),
                    "p_value": utils.fmt(stats["p_value"]),
                    "win_rate": utils.fmt(stats["win_rate"]),
                }
            )
    utils.table_pair(OUT_DIR / "04_outlier_robustness", outlier_rows, "Outlier Robustness")
    utils.write_md(
        OUT_DIR / "05_overlap_censoring_interpretation.md",
        "Overlap Censoring Interpretation",
        "Long-horizon results must be read with overlap and right-censoring caveats. Full-window-only, non-overlapping, leave-one-out, and winsorized tables are the preferred robustness checks before citing 252D/504D effects.",
    )
    print("Overlap/censoring robustness complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
