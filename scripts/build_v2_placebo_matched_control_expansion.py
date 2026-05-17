"""Expanded placebo and matched-control falsification."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_long_horizon_returns as lh  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("placebo_matched_controls")
SHIFTS = [-90, -60, -30, 30, 60, 90]


def main() -> int:
    events = utils.event_records()
    frames = rf.load_market_with_volume()
    event_positions: dict[str, set[int]] = {}
    event_info: list[tuple[Any, pd.DataFrame, int]] = []
    for event in events:
        if event.return_exclusion_reason or event.effective_trading_event_date is None:
            continue
        frame = frames.get(event.data_ticker)
        idx = lh.first_idx(frame, event.effective_trading_event_date) if frame is not None else None
        if idx is None or frame is None:
            continue
        event_positions.setdefault(event.data_ticker, set()).add(idx)
        event_info.append((event, frame, idx))

    panel_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    for event, frame, idx in event_info:
        treated_5 = lh.clean_float(
            lh.window_metrics(frame, idx, idx, idx + 5, allow_right_censor=False).get("spy_bhar")
        )
        treated_21 = lh.clean_float(
            lh.window_metrics(frame, idx, idx, idx + 21, allow_right_censor=False).get("spy_bhar")
        )
        panel_rows.append(
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "control_type": "treated",
                "offset_days": 0,
                "bhar_5d": treated_5,
                "bhar_21d": treated_21,
            }
        )
        for label, pos in rf.placebo_indices(frame, idx, event_positions[event.data_ticker], SHIFTS):
            c5 = lh.clean_float(lh.window_metrics(frame, pos, pos, pos + 5, allow_right_censor=False).get("spy_bhar"))
            c21 = lh.clean_float(
                lh.window_metrics(frame, pos, pos, pos + 21, allow_right_censor=False).get("spy_bhar")
            )
            panel_rows.append(
                {
                    "event_id": event.event_id,
                    "ticker": event.ticker,
                    "control_type": label,
                    "offset_days": pos - idx,
                    "bhar_5d": c5,
                    "bhar_21d": c21,
                }
            )

    panel = pd.DataFrame(panel_rows)
    panel.to_csv(OUT / "placebo_matched_control_panel.csv", index=False)

    treated = panel[panel["control_type"] == "treated"]
    for ctype in panel["control_type"].unique():
        if ctype == "treated":
            continue
        ctrl = panel[panel["control_type"] == ctype]
        merged = treated.merge(ctrl, on="event_id", suffixes=("_t", "_c"))
        for horizon in ["5d", "21d"]:
            tc, cc = f"bhar_{horizon}_t", f"bhar_{horizon}_c"
            if tc not in merged or cc not in merged:
                continue
            diff = (merged[tc] - merged[cc]).dropna()
            stats = utils.t_stats(diff.astype(float).tolist())
            result_rows.append(
                {
                    "control_type": ctype,
                    "horizon": horizon.upper(),
                    "n_pairs": stats["n"],
                    "mean_diff_treated_minus_control": stats["mean"],
                    "t_stat": stats["t_stat"],
                    "p_value": stats["p_value"],
                }
            )

    utils.write_csv(OUT / "placebo_matched_control_results.csv", result_rows, list(result_rows[0]) if result_rows else ["control_type"])

    summary = f"""# Placebo / matched-control expansion

## Tests
1. Same-ticker shifted dates ({', '.join(str(s) for s in SHIFTS)} trading days)
2. Random same-ticker non-event dates
3. Paired differences: treated minus placebo

## Interpretation
Findings that **shrink** under placebos support attention/selection rather than event-specific information.
Failed placebos (no shrinkage) are reported explicitly—do not hide.

See `placebo_matched_control_results.csv` for paired test statistics.
"""
    utils.write_md(OUT / "placebo_matched_control_summary.md", "Placebo Matched Controls", summary)

    # Creator cross-ticker placebo: same date, different ticker (matched top-5 status)
    tickers_by_top5: dict[bool, list[str]] = {True: [], False: []}
    for t in frames:
        tickers_by_top5[t in utils.TOP5].append(t)
    cross_rows: list[dict[str, Any]] = []
    for event, frame, idx in event_info:
        treated_5 = lh.clean_float(
            lh.window_metrics(frame, idx, idx, idx + 5, allow_right_censor=False).get("spy_bhar")
        )
        pool = [t for t in tickers_by_top5[event.ticker in utils.TOP5] if t != event.data_ticker and t in frames]
        if not pool:
            continue
        placebo_ticker = rf.RNG.choice(pool)
        pframe = frames[placebo_ticker]
        pidx = lh.first_idx(pframe, event.effective_trading_event_date)
        if pidx is None or pidx + 5 >= len(pframe):
            continue
        placebo_5 = lh.clean_float(
            lh.window_metrics(pframe, pidx, pidx, pidx + 5, allow_right_censor=False).get("spy_bhar")
        )
        if treated_5 is None or placebo_5 is None:
            continue
        cross_rows.append(
            {
                "event_id": event.event_id,
                "creator": event.creator,
                "treated_ticker": event.ticker,
                "placebo_ticker": placebo_ticker,
                "event_date": str(event.effective_trading_event_date),
                "treated_bhar_5d": treated_5,
                "placebo_bhar_5d": placebo_5,
                "diff_treated_minus_placebo": treated_5 - placebo_5,
                "top5_matched": event.ticker in utils.TOP5,
            }
        )

    cross_df = pd.DataFrame(cross_rows)
    if not cross_df.empty:
        cross_df.to_csv(OUT / "creator_cross_ticker_placebo_results.csv", index=False)
        diffs = cross_df["diff_treated_minus_placebo"].astype(float).tolist()
        st = utils.t_stats(diffs)
        utils.write_md(
            OUT / "creator_cross_ticker_placebo_summary.md",
            "Creator Cross-Ticker Placebo",
            f"""# Creator cross-ticker placebo

Same event date and creator context; placebo ticker drawn from same top-5/non-top pool.

- Pairs: **{st['n']}**
- Mean treated − placebo 5D BHAR: **{st['mean']:.4f}** (t={st['t_stat']:.2f}, p={st['p_value']:.4f})

Shrinkage toward zero supports **attention/selection** rather than creator-specific information in the recommended ticker.
""",
        )

    print("Placebo matched control expansion complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
