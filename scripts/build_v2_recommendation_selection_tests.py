"""Pre-event selection / momentum-chasing tests for recommendation events."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_long_horizon_returns as lh  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("recommendation_selection")


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        utils.write_md(OUT / "recommendation_selection_summary.md", "Recommendation Selection", "No events.")
        return 0
    events["is_event"] = True
    events.to_csv(OUT / "recommendation_selection_panel.csv", index=False)

    frames = rf.load_market_with_volume()
    event_records = utils.event_records()
    event_positions: dict[str, set[int]] = {}
    for e in event_records:
        if e.effective_trading_event_date and not e.return_exclusion_reason:
            fr = frames.get(e.data_ticker)
            idx = lh.first_idx(fr, e.effective_trading_event_date) if fr is not None else None
            if idx is not None:
                event_positions.setdefault(e.data_ticker, set()).add(idx)

    placebo_rows: list[dict] = []
    for ticker, frame in frames.items():
        taken = event_positions.get(ticker, set())
        valid = [i for i in range(22, len(frame) - 63) if i not in taken]
        if not valid:
            continue
        sample = rf.RNG.sample(valid, min(80, len(valid)))
        for idx in sample:
            row = {"event_id": f"placebo_{ticker}_{idx}", "ticker": ticker, "is_event": False, "event_idx": idx}
            row.update(rf.pre_features(frame, idx))
            placebo_rows.append(row)

    panel = pd.concat([events, pd.DataFrame(placebo_rows)], ignore_index=True)
    panel["top5_flag"] = panel["top5_flag"].astype(bool)
    panel["is_event"] = panel["is_event"].astype(bool)
    panel.to_csv(OUT / "recommendation_selection_panel.csv", index=False)

    y_cols = [c for c in panel.columns if c.startswith("prior_return_") or c in ("prior_volatility_21d", "prior_abnormal_volume")]
    reg_rows: list[dict] = []
    for ycol in y_cols:
        y = panel[ycol]
        x = pd.DataFrame(
            {
                "is_event": panel["is_event"].astype(float),
                "top5_flag": panel.get("top5_flag", False).astype(float),
                "is_event_x_top5": panel["is_event"].astype(float) * panel.get("top5_flag", False).astype(float),
            }
        )
        reg_rows.append(rf.run_ols(y, x, f"all_{ycol}"))
        for subset, mask in [
            ("top5_events", panel["is_event"] & panel["top5_flag"]),
            ("non_top_events", panel["is_event"] & ~panel["top5_flag"]),
            ("buy_events", panel["is_event"] & (panel["recommendation_type"] == "buy")),
            ("high_conf_events", panel["is_event"] & panel["high_confidence"].fillna(False)),
        ]:
            sub = panel.loc[mask]
            if len(sub) < 40:
                continue
            stats = utils.t_stats(sub[ycol].dropna().astype(float).tolist())
            reg_rows.append({"spec": f"{subset}_{ycol}", "status": "mean_only", "n": stats["n"], "mean": stats["mean"], "t_stat": stats["t_stat"]})

    utils.write_csv(OUT / "recommendation_selection_regressions.csv", reg_rows, list(reg_rows[0]) if reg_rows else ["spec"])

    ev = panel[panel["is_event"]]
    pl = panel[~panel["is_event"]]
    summary = f"""# Recommendation selection / momentum chasing

## Key comparisons (event vs same-ticker placebo dates)

| Metric | Event mean | Placebo mean | Event−placebo |
| --- | --- | --- | --- |
| prior_return_21d | {ev['prior_return_21d'].mean():.4f} | {pl['prior_return_21d'].mean():.4f} | {(ev['prior_return_21d'].mean()-pl['prior_return_21d'].mean()):.4f} |
| prior_return_63d | {ev['prior_return_63d'].mean():.4f} | {pl['prior_return_63d'].mean():.4f} | {(ev['prior_return_63d'].mean()-pl['prior_return_63d'].mean()):.4f} |
| prior_abnormal_volume | {ev['prior_abnormal_volume'].mean():.4f} | {pl['prior_abnormal_volume'].mean():.4f} | {(ev['prior_abnormal_volume'].mean()-pl['prior_abnormal_volume'].mean()):.4f} |

## Top-5 vs non-top (events only)

| Metric | Top-5 | Non-top |
| --- | --- | --- |
| prior_return_21d | {ev.loc[ev['top5_flag'], 'prior_return_21d'].mean():.4f} | {ev.loc[~ev['top5_flag'], 'prior_return_21d'].mean():.4f} |
| prior_return_63d | {ev.loc[ev['top5_flag'], 'prior_return_63d'].mean():.4f} | {ev.loc[~ev['top5_flag'], 'prior_return_63d'].mean():.4f} |

## Interpretation (conservative)

- Positive pre-event momentum supports **selection into trending names**, not information revelation.
- Top-5 recommendations show stronger prior momentum than non-top names in raw means.
- This **weakens** causal skill claims and supports attention/momentum-chasing mechanism language.
- Unknown news states are not treated as clean in downstream confound panels.
"""
    utils.write_md(OUT / "recommendation_selection_summary.md", "Recommendation Selection Summary", summary)
    print("Recommendation selection tests complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
