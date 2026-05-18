"""Ticker-date matched controls (no future data; deterministic seed)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "matched_ticker_date_controls"
RNG_SEED = 496


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = utils.event_manifest().copy()
    manifest["event_date_dt"] = pd.to_datetime(manifest["event_date"], errors="coerce")
    long = utils.forward_panel(["5D", "21D", "63D"])
    if long.empty:
        print("Missing forward returns")
        return 1
    wide = long.pivot_table(index="event_id", columns="horizon", values="spy_bhar", aggfunc="first")
    base = manifest.merge(wide, on="event_id", how="left")
    rng = random.Random(RNG_SEED)
    rows: list[dict[str, object]] = []

    for _, ev in base.iterrows():
        tkr = str(ev["ticker"])
        ed = ev["event_date_dt"]
        if pd.isna(ed):
            continue
        pool = base[(base["ticker"].astype(str) == tkr) & (base["event_id"] != ev["event_id"])]
        pool = pool[
            (pool["event_date_dt"].notna())
            & (pool["event_date_dt"] < ed)
            & (pool["event_date_dt"] >= ed - pd.Timedelta(days=400))
        ]
        if pool.empty:
            ctrl_date = ""
            ctrl_id = ""
        else:
            pick = pool.iloc[rng.randrange(len(pool))]
            ctrl_date = str(pick["event_date"])
            ctrl_id = int(pick["event_id"])
        rows.append(
            {
                "event_id": int(ev["event_id"]),
                "ticker": tkr,
                "event_date": ev["event_date"],
                "control_event_id": ctrl_id,
                "control_event_date": ctrl_date,
                "bhar_5d_event": ev.get("5D", ""),
                "bhar_21d_event": ev.get("21D", ""),
                "bhar_63d_event": ev.get("63D", ""),
            }
        )

    panel_df = pd.DataFrame(rows)
    panel_df.to_csv(OUT / "matched_control_event_panel.csv", index=False)
    long = utils.forward_panel(["5D", "21D", "63D"])
    ctrl_long = long.rename(columns={"event_id": "control_event_id", "spy_bhar": "spy_bhar_ctrl"})
    m = long.merge(panel_df[["event_id", "control_event_id"]], on="event_id", how="inner")
    m = m.merge(ctrl_long, on=["control_event_id", "horizon"], how="left")
    m["diff"] = pd.to_numeric(m["spy_bhar"], errors="coerce") - pd.to_numeric(m["spy_bhar_ctrl"], errors="coerce")
    m.groupby("horizon")["diff"].agg(["mean", "median", "count"]).reset_index().to_csv(
        OUT / "matched_control_return_summary.csv", index=False
    )
    (OUT / "matched_control_summary.md").write_text(
        "# Matched ticker-date controls\n\nControl matched on same ticker using a **prior** event from the manifest "
        "(no future-looking). This is a diagnostic baseline, not a full calendar-time matching engine.\n",
        encoding="utf-8",
    )
    pd.DataFrame([{"note": "by_alignment_requires_analyst_merge"}]).to_csv(OUT / "matched_control_by_alignment.csv", index=False)
    pd.DataFrame([{"note": "by_news_status_requires_news_panel_merge"}]).to_csv(
        OUT / "matched_control_by_news_status.csv", index=False
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
