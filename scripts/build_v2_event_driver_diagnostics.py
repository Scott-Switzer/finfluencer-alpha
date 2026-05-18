"""Concentration / driver diagnostics for event-study slices (ticker and creator depth)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "event_driver_diagnostics"
PANEL_PATH = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"


def _pivot_forward_returns(long: pd.DataFrame) -> pd.DataFrame:
    """One row per event_id with spy_bhar by horizon (5D / 21D / 63D)."""
    long = long[(long["status"] == "computed") & long["horizon"].isin(["5D", "21D", "63D"])].copy()
    if long.empty:
        return pd.DataFrame()
    p = long.pivot_table(index="event_id", columns="horizon", values="spy_bhar", aggfunc="first")
    p = p.rename(columns={h: f"spy_bhar_{h}" for h in p.columns})
    return p.reset_index()


def concentration_table(
    df: pd.DataFrame,
    key_col: str,
    total_n: int,
) -> pd.DataFrame:
    """Top contributors: counts, share, mean BHAR by horizon."""
    if df.empty or key_col not in df.columns:
        return pd.DataFrame()
    g = (
        df.groupby(key_col, dropna=False)
        .agg(
            n_events=("event_id", "count"),
            mean_spy_bhar_5D=("spy_bhar_5D", "mean"),
            mean_spy_bhar_21D=("spy_bhar_21D", "mean"),
            mean_spy_bhar_63D=("spy_bhar_63D", "mean"),
        )
        .reset_index()
        .rename(columns={key_col: "name"})
    )
    g = g.sort_values("n_events", ascending=False)
    g["share_of_sample"] = g["n_events"] / max(total_n, 1)
    g["rank"] = range(1, len(g) + 1)
    return g


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    long = utils.forward_panel(["5D", "21D", "63D"])
    wide = _pivot_forward_returns(long)
    manifest = utils.event_manifest()[["event_id", "ticker", "creator"]]
    if wide.empty:
        pd.DataFrame(columns=["horizon", "group", "key", "sum_spy_bhar"]).to_csv(
            OUT / "concentration_diagnostics.csv", index=False
        )
        Path(OUT / "concentration_summary.md").write_text("# Event driver\n\nNo forward returns to pivot.\n", encoding="utf-8")
        return 0
    base = manifest.merge(wide, on="event_id", how="inner")
    n_total = len(base)

    if PANEL_PATH.exists():
        panel = pd.read_csv(PANEL_PATH, usecols=["event_id", "news_clean_status_final"], low_memory=False)
        base = base.merge(panel, on="event_id", how="left")

    by_ticker = concentration_table(base, "ticker", n_total)
    by_creator = concentration_table(base, "creator", n_total)
    by_ticker.to_csv(OUT / "concentration_by_ticker.csv", index=False)
    by_creator.to_csv(OUT / "concentration_by_creator.csv", index=False)

    # Long-form top-5 sum of spy_bhar per horizon (legacy-style diagnostic)
    rows: list[dict[str, object]] = []
    merged_long = long.merge(manifest, on="event_id", how="left")
    if PANEL_PATH.exists():
        merged_long = merged_long.merge(
            pd.read_csv(PANEL_PATH, usecols=["event_id", "news_clean_status_final"], low_memory=False),
            on="event_id",
            how="left",
        )
    for h in ("21D", "63D"):
        g = merged_long[(merged_long["horizon"] == h) & (merged_long["status"] == "computed")]
        for col, name in (("ticker", "ticker"), ("creator", "creator")):
            if col not in g.columns:
                continue
            top = g.groupby(col)["spy_bhar"].sum().sort_values(ascending=False).head(5).reset_index()
            for _, r in top.iterrows():
                rows.append(
                    {
                        "horizon": h,
                        "group": name,
                        "key": str(r[col]),
                        "sum_spy_bhar": float(r["spy_bhar"]),
                    }
                )
    pd.DataFrame(rows, columns=["horizon", "group", "key", "sum_spy_bhar"]).to_csv(
        OUT / "concentration_diagnostics.csv", index=False
    )

    top5_share_ticker = float(by_ticker["share_of_sample"].head(5).sum()) if len(by_ticker) else 0.0
    top5_share_creator = float(by_creator["share_of_sample"].head(5).sum()) if len(by_creator) else 0.0
    summary = f"""# Concentration diagnostics

Sample: **{n_total}** events with computed **5D / 21D / 63D** forward SPY BHAR.

## Ticker concentration

- **Top-5 ticker share of events**: {top5_share_ticker:.3f}
- Full table: `concentration_by_ticker.csv` (ranks by `n_events`).

## Creator concentration

- **Top-5 creator share of events**: {top5_share_creator:.3f}
- Full table: `concentration_by_creator.csv`.

## Notes

- Means are **equal-weighted across events** within each name (not dollar-weighted).
- Use with sensitivity bounds; large names can drive heterogeneity.
- `concentration_diagnostics.csv` lists **summed** SPY BHAR for top-5 names by horizon (legacy-style concentration).
"""
    (OUT / "concentration_summary.md").write_text(summary, encoding="utf-8")

    pd.DataFrame(
        [{"slice": "all", "n_events": n_total, "warning": "window_overlap_21_63"}]
    ).to_csv(OUT / "event_driver_summary.csv", index=False)
    pd.DataFrame([{"exclusion": "see_statistical_robustness_layer", "n": 0}]).to_csv(
        OUT / "robustness_exclusion_table.csv", index=False
    )
    (OUT / "event_driver_diagnostics_summary.md").write_text(
        "# Event driver diagnostics\n\nSee `concentration_summary.md` for ticker/creator depth tables.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
