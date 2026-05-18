"""Concentration / driver diagnostics for event-study slices."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "event_driver_diagnostics"
PANEL_PATH = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = utils.event_manifest()
    long = utils.forward_panel(["21D", "63D"])
    merged = long.merge(manifest, on="event_id", how="left")
    if PANEL_PATH.exists():
        merged = merged.merge(pd.read_csv(PANEL_PATH, usecols=["event_id", "news_clean_status_final"]), on="event_id", how="left")
    rows: list[dict[str, object]] = []
    for h in ("21D", "63D"):
        g = merged[(merged["horizon"] == h) & (merged["status"] == "computed")]
        for col, name in (("ticker", "ticker"), ("creator", "creator")):
            if col not in g.columns:
                continue
            top = g.groupby(col)["spy_bhar"].sum().sort_values(ascending=False).head(5).reset_index()
            for _, r in top.iterrows():
                rows.append({"horizon": h, "group": name, "key": str(r[col]), "sum_spy_bhar": float(r["spy_bhar"])})

    cols = ["horizon", "group", "key", "sum_spy_bhar"]
    pd.DataFrame(rows, columns=cols).to_csv(OUT / "concentration_diagnostics.csv", index=False)
    pd.DataFrame(
        [{"slice": "all", "n_events": int(merged['event_id'].nunique()), "warning": "window_overlap_21_63"}]
    ).to_csv(OUT / "event_driver_summary.csv", index=False)
    pd.DataFrame([{"exclusion": "placeholder_run_full_robustness_later", "n": 0}]).to_csv(
        OUT / "robustness_exclusion_table.csv", index=False
    )
    (OUT / "event_driver_diagnostics_summary.md").write_text(
        "# Event driver diagnostics\n\nTop ticker/creator contributions to summed SPY BHAR within horizon. "
        "Use alongside sensitivity bounds — results may concentrate in liquid mega-caps.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
