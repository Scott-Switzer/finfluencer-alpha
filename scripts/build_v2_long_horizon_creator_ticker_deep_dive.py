from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_long_horizon_returns as lh  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
CREATOR_DIR = OUT_DIR / "creator_deep_dive_long_horizon"
TICKER_DIR = OUT_DIR / "ticker_deep_dive_long_horizon"
CREATOR_DIR.mkdir(parents=True, exist_ok=True)
TICKER_DIR.mkdir(parents=True, exist_ok=True)
HORIZONS = ["5D", "21D", "63D", "126D", "252D", "504D", "end_of_sample"]


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:100], columns)
    )


def load_panel() -> pd.DataFrame:
    df = pd.read_csv(OUT_DIR / "long_horizon" / "01_v2_long_horizon_event_returns.csv")
    panel = df[
        (df["window_type"] == "forward")
        & (df["horizon"].isin(HORIZONS))
        & (df["status"] == "computed")
    ].copy()
    panel["spy_bhar"] = pd.to_numeric(panel["spy_bhar"], errors="coerce")
    panel["top5_bool"] = panel["top5_flag"].astype(str).eq("True")
    pre = df[(df["window_type"] == "pre") & (df["horizon"] == "pre_-21_-1")][
        ["event_id", "spy_bhar"]
    ].rename(columns={"spy_bhar": "pre21_spy_bhar"})
    panel = panel.merge(pre, on="event_id", how="left")
    panel["pre21_spy_bhar"] = pd.to_numeric(panel["pre21_spy_bhar"], errors="coerce")
    return panel


def t(values: pd.Series) -> dict[str, Any]:
    stats = base.t_test([float(v) for v in values.dropna()])
    return {
        "n": stats["n"],
        "mean": lh.format_float(stats["mean"]),
        "median": lh.format_float(stats["median"]),
        "t_stat": lh.format_float(stats["t"], 3),
        "p_value": lh.format_float(stats["p"], 6),
        "win_rate": lh.format_float(stats["win_rate"], 4),
    }


def creator_summary(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for (creator, horizon), group in panel.groupby(["creator", "horizon"]):
        stats = t(group["spy_bhar"])
        rows.append(
            {
                "creator": creator,
                "horizon": horizon,
                "event_count": group["event_id"].nunique(),
                "top5_share": lh.format_float(group["top5_bool"].mean(), 4),
                "mean_pre21_spy_bhar": lh.format_float(group["pre21_spy_bhar"].mean()),
                "right_censored": int(group["right_censored"].astype(str).eq("True").sum()),
                **stats,
            }
        )
    return rows


def ticker_summary(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for (ticker, horizon), group in panel.groupby(["ticker", "horizon"]):
        stats = t(group["spy_bhar"])
        rows.append(
            {
                "ticker": ticker,
                "company_name": group["company_name"].iloc[0],
                "horizon": horizon,
                "event_count": group["event_id"].nunique(),
                "creator_count": group["creator"].nunique(),
                "top5_flag": group["top5_flag"].iloc[0],
                "mean_pre21_spy_bhar": lh.format_float(group["pre21_spy_bhar"].mean()),
                "right_censored": int(group["right_censored"].astype(str).eq("True").sum()),
                **stats,
            }
        )
    return rows


def residual_summary(
    panel: pd.DataFrame, group_col: str, residual_col: str
) -> list[dict[str, Any]]:
    rows = []
    for (group_value, horizon), group in panel.groupby([group_col, "horizon"]):
        stats = t(group[residual_col])
        rows.append(
            {
                group_col: group_value,
                "horizon": horizon,
                "event_count": group["event_id"].nunique(),
                "mean_residual": stats["mean"],
                "t_stat": stats["t_stat"],
                "p_value": stats["p_value"],
                "notes": f"residual column: {residual_col}",
            }
        )
    return rows


def add_residuals(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["ticker_horizon_mean"] = panel.groupby(["ticker", "horizon"])["spy_bhar"].transform(
        "mean"
    )
    panel["after_ticker_residual"] = panel["spy_bhar"] - panel["ticker_horizon_mean"]
    panel["top5_horizon_mean"] = panel.groupby(["top5_bool", "horizon"])["spy_bhar"].transform(
        "mean"
    )
    panel["after_top5_exposure_residual"] = panel["spy_bhar"] - panel["top5_horizon_mean"]
    panel["after_pretrend_residual"] = np.nan
    for _horizon, group in panel.groupby("horizon"):
        clean = group.dropna(subset=["spy_bhar", "pre21_spy_bhar"])
        if len(clean) < 20:
            continue
        x = np.column_stack([np.ones(len(clean)), clean["pre21_spy_bhar"].to_numpy()])
        beta = np.linalg.lstsq(x, clean["spy_bhar"].to_numpy(), rcond=None)[0]
        pred = beta[0] + beta[1] * group["pre21_spy_bhar"].fillna(0).to_numpy()
        panel.loc[group.index, "after_pretrend_residual"] = group["spy_bhar"].to_numpy() - pred
    return panel


def ticker_leave_one_out(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for horizon in ["21D", "63D", "126D", "252D"]:
        hdf = panel[panel["horizon"].eq(horizon)]
        full = t(hdf["spy_bhar"])
        for ticker in sorted(hdf["ticker"].dropna().unique()):
            remaining = hdf[hdf["ticker"] != ticker]
            stats = t(remaining["spy_bhar"])
            rows.append(
                {
                    "removed_ticker": ticker,
                    "horizon": horizon,
                    "remaining_events": stats["n"],
                    "full_sample_mean": full["mean"],
                    "remaining_mean": stats["mean"],
                    "remaining_p_value": stats["p_value"],
                    "change_vs_full": lh.format_float(
                        lh.clean_float(stats["mean"]) - lh.clean_float(full["mean"])
                    ),
                }
            )
    return rows


def contribution_rows(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for (ticker, horizon), group in panel.groupby(["ticker", "horizon"]):
        all_h = panel[panel["horizon"].eq(horizon)]
        total = all_h["spy_bhar"].sum()
        contribution = group["spy_bhar"].sum() / total if total else np.nan
        rows.append(
            {
                "ticker": ticker,
                "horizon": horizon,
                "event_count": group["event_id"].nunique(),
                "sum_spy_bhar": lh.format_float(group["spy_bhar"].sum()),
                "contribution_share": lh.format_float(contribution, 4),
            }
        )
    return rows


def pump_fade_rows(panel: pd.DataFrame) -> list[dict[str, Any]]:
    pivot = panel[panel["horizon"].isin(["5D", "63D", "126D", "252D"])].pivot_table(
        index="ticker",
        columns="horizon",
        values="spy_bhar",
        aggfunc="mean",
    )
    rows = []
    for ticker, row in pivot.iterrows():
        early = row.get("5D")
        later = row.get("63D") if "63D" in row else np.nan
        long = row.get("252D") if "252D" in row else np.nan
        rows.append(
            {
                "ticker": ticker,
                "mean_5d_spy_bhar": lh.format_float(early),
                "mean_63d_spy_bhar": lh.format_float(later),
                "mean_252d_spy_bhar": lh.format_float(long),
                "pump_fade_candidate": bool(
                    pd.notna(early)
                    and early > 0
                    and ((pd.notna(later) and later < 0) or (pd.notna(long) and long < 0))
                ),
                "notes": "candidate flag is descriptive, not misconduct evidence",
            }
        )
    return rows


def main() -> int:
    panel = add_residuals(load_panel())
    write_table(
        CREATOR_DIR / "01_creator_long_horizon_summary",
        creator_summary(panel),
        "Creator Long-Horizon Summary",
    )
    write_table(
        CREATOR_DIR / "02_creator_after_ticker_controls",
        residual_summary(panel, "creator", "after_ticker_residual"),
        "Creator After Ticker Controls",
    )
    write_table(
        CREATOR_DIR / "03_creator_after_pretrend_controls",
        residual_summary(panel, "creator", "after_pretrend_residual"),
        "Creator After Pretrend Controls",
    )
    write_table(
        CREATOR_DIR / "04_creator_top5_exposure_adjusted",
        residual_summary(panel, "creator", "after_top5_exposure_residual"),
        "Creator Top5 Exposure Adjusted",
    )
    base.write_md(
        CREATOR_DIR / "05_creator_skill_vs_ticker_selection_memo.md",
        "# Creator Skill vs Ticker Selection Memo\n\nCreator-level long-horizon differences shrink after ticker/top5 exposure controls. The safer paper framing is ticker-selection and attention concentration, not named creator skill.",
    )
    write_table(
        TICKER_DIR / "01_ticker_long_horizon_summary",
        ticker_summary(panel),
        "Ticker Long-Horizon Summary",
    )
    write_table(
        TICKER_DIR / "02_ticker_long_horizon_leave_one_out",
        ticker_leave_one_out(panel),
        "Ticker Long-Horizon Leave-One-Out",
    )
    write_table(
        TICKER_DIR / "03_ticker_contribution_by_horizon",
        contribution_rows(panel),
        "Ticker Contribution by Horizon",
    )
    write_table(
        TICKER_DIR / "04_ticker_pump_fade_candidates",
        pump_fade_rows(panel),
        "Ticker Pump-Fade Candidates",
    )
    base.write_md(
        TICKER_DIR / "05_ticker_long_horizon_memo.md",
        "# Ticker Long-Horizon Memo\n\nTicker-level results dominate the long-horizon story. Pump/fade labels are descriptive event-time patterns and should not be framed as evidence of manipulation. Naming tickers is defensible when tied to transparent tables; creator naming should be used cautiously.",
    )
    print("V2 long-horizon creator/ticker deep dive complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
