from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_long_horizon_returns as lh  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
FALS_DIR = OUT_DIR / "long_horizon_falsification"
FALS_DIR.mkdir(parents=True, exist_ok=True)
RNG = random.Random(496)
HORIZONS = [21, 63, 126, 252]
SHIFTS = [-252, -126, -63, -21, 21, 63, 126, 252]


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:100], columns)
    )


def t(values: list[float]) -> dict[str, Any]:
    stats = base.t_test(values)
    return {
        "n": stats["n"],
        "mean": lh.format_float(stats["mean"]),
        "median": lh.format_float(stats["median"]),
        "t_stat": lh.format_float(stats["t"], 3),
        "p_value": lh.format_float(stats["p"], 6),
        "win_rate": lh.format_float(stats["win_rate"], 4),
    }


def get_ar(frame: pd.DataFrame, idx: int, horizon: int) -> float | None:
    metrics = lh.window_metrics(frame, idx, idx, idx + horizon, allow_right_censor=False)
    return lh.clean_float(metrics.get("spy_bhar"))


def pre_momentum(frame: pd.DataFrame, idx: int) -> float | None:
    metrics = lh.window_metrics(frame, idx, idx - 21, idx, allow_right_censor=False)
    return lh.clean_float(metrics.get("spy_bhar"))


def matched_control_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = base.fetch_events(base.load_market_data())
    frames = lh.market_frames()
    event_positions: dict[str, set[int]] = {}
    event_info = []
    for event in events:
        frame = frames.get(event.data_ticker)
        idx = lh.first_idx(frame, event.effective_trading_event_date) if frame is not None else None
        if idx is None:
            continue
        event_positions.setdefault(event.data_ticker, set()).add(idx)
        event_info.append((event, frame, idx, pre_momentum(frame, idx)))
    pair_rows = []
    summary_rows = []
    for horizon in HORIZONS:
        diffs = []
        treated_values = []
        control_values = []
        for event, frame, idx, event_pre in event_info:
            if idx + horizon >= len(frame):
                continue
            candidates = []
            candidate_positions = {
                idx - 252,
                idx - 126,
                idx - 63,
                idx - 21,
                idx + 21,
                idx + 63,
                idx + 126,
                idx + 252,
            }
            valid_positions = list(range(22, max(23, len(frame) - horizon)))
            if valid_positions:
                candidate_positions.update(
                    RNG.sample(valid_positions, min(20, len(valid_positions)))
                )
            for pos in sorted(candidate_positions):
                if pos < 22 or pos + horizon >= len(frame):
                    continue
                if any(
                    abs(pos - taken) <= 10
                    for taken in event_positions.get(event.data_ticker, set())
                ):
                    continue
                candidate_pre = pre_momentum(frame, pos)
                distance = abs((candidate_pre or 0.0) - (event_pre or 0.0))
                candidates.append((distance, pos, candidate_pre))
            if not candidates:
                continue
            _, control_idx, control_pre = min(candidates, key=lambda item: item[0])
            treated = get_ar(frame, idx, horizon)
            control = get_ar(frame, control_idx, horizon)
            if treated is None or control is None:
                continue
            diff = treated - control
            diffs.append(diff)
            treated_values.append(treated)
            control_values.append(control)
            pair_rows.append(
                {
                    "event_id": event.event_id,
                    "ticker": event.ticker,
                    "horizon_days": horizon,
                    "treated_event_date": event.event_date.isoformat() if event.event_date else "",
                    "control_trading_date": frame.iloc[control_idx]["date"].isoformat(),
                    "treated_pre21_spy_bhar": lh.format_float(event_pre),
                    "control_pre21_spy_bhar": lh.format_float(control_pre),
                    "treated_spy_bhar": lh.format_float(treated),
                    "control_spy_bhar": lh.format_float(control),
                    "treated_minus_control": lh.format_float(diff),
                    "match_rule": "same ticker, same month/quarter, no event within +/-10 trading days, closest pre-21 momentum",
                }
            )
        diff_stats = t(diffs)
        summary_rows.append(
            {
                "horizon_days": horizon,
                "matched_pairs": len(diffs),
                "treated_mean": lh.format_float(
                    statistics.mean(treated_values) if treated_values else None
                ),
                "control_mean": lh.format_float(
                    statistics.mean(control_values) if control_values else None
                ),
                "treated_minus_control_mean": diff_stats["mean"],
                "t_stat": diff_stats["t_stat"],
                "p_value": diff_stats["p_value"],
                "notes": "matched controls are diagnostic, not causal proof",
            }
        )
    base.write_csv(
        FALS_DIR / "00_long_horizon_matched_control_pairs.csv",
        pair_rows,
        list(pair_rows[0]) if pair_rows else ["status"],
    )
    return pair_rows, summary_rows


def placebo_rows() -> list[dict[str, Any]]:
    events = base.fetch_events(base.load_market_data())
    frames = lh.market_frames()
    rows = []
    for horizon in HORIZONS:
        actual_values = []
        for event in events:
            frame = frames.get(event.data_ticker)
            idx = (
                lh.first_idx(frame, event.effective_trading_event_date)
                if frame is not None
                else None
            )
            if idx is None:
                continue
            value = get_ar(frame, idx, horizon)
            if value is not None:
                actual_values.append(value)
        actual_mean = statistics.mean(actual_values) if actual_values else None
        for shift in SHIFTS:
            placebo_values = []
            for event in events:
                frame = frames.get(event.data_ticker)
                idx = (
                    lh.first_idx(frame, event.effective_trading_event_date)
                    if frame is not None
                    else None
                )
                if idx is None:
                    continue
                shifted = idx + shift
                if shifted < 0 or shifted + horizon >= len(frame):
                    continue
                value = get_ar(frame, shifted, horizon)
                if value is not None:
                    placebo_values.append(value)
            stats = t(placebo_values)
            rows.append(
                {
                    "horizon_days": horizon,
                    "shift_trading_days": shift,
                    "actual_n": len(actual_values),
                    "actual_mean_spy_bhar": lh.format_float(actual_mean),
                    "placebo_n": stats["n"],
                    "placebo_mean_spy_bhar": stats["mean"],
                    "placebo_p_value": stats["p_value"],
                    "actual_minus_placebo": lh.format_float(
                        None
                        if actual_mean is None or not placebo_values
                        else actual_mean - statistics.mean(placebo_values)
                    ),
                }
            )
    return rows


def permutation_rows(iterations: int = 50) -> list[dict[str, Any]]:
    events = base.fetch_events(base.load_market_data())
    frames = lh.market_frames()
    rows = []
    for horizon in HORIZONS:
        actual = []
        event_by_ticker: dict[str, int] = {}
        for event in events:
            frame = frames.get(event.data_ticker)
            idx = (
                lh.first_idx(frame, event.effective_trading_event_date)
                if frame is not None
                else None
            )
            if idx is None:
                continue
            value = get_ar(frame, idx, horizon)
            if value is not None:
                actual.append(value)
                event_by_ticker[event.data_ticker] = event_by_ticker.get(event.data_ticker, 0) + 1
        observed = statistics.mean(actual) if actual else 0.0
        simulated = []
        valid_by_ticker = {
            ticker: list(range(22, len(frame) - horizon))
            for ticker, frame in frames.items()
            if len(frame) > horizon + 30
        }
        for _ in range(iterations):
            values = []
            for ticker, count in event_by_ticker.items():
                frame = frames.get(ticker)
                positions = valid_by_ticker.get(ticker, [])
                if frame is None or not positions:
                    continue
                draw_count = min(count, len(positions), 75)
                for pos in RNG.sample(positions, draw_count):
                    value = get_ar(frame, pos, horizon)
                    if value is not None:
                        values.append(value)
            if values:
                simulated.append(statistics.mean(values))
        p_value = (
            sum(1 for value in simulated if abs(value) >= abs(observed)) / len(simulated)
            if simulated
            else None
        )
        rows.append(
            {
                "horizon_days": horizon,
                "permutations": len(simulated),
                "observed_mean_spy_bhar": lh.format_float(observed),
                "permutation_mean": lh.format_float(
                    statistics.mean(simulated) if simulated else None
                ),
                "permutation_p_value": lh.format_float(p_value, 6),
                "notes": "shuffle event dates within ticker while preserving ticker event counts",
            }
        )
    return rows


def main() -> int:
    _pairs, matched = matched_control_rows()
    write_table(
        FALS_DIR / "01_long_horizon_matched_controls", matched, "Long-Horizon Matched Controls"
    )
    placebos = placebo_rows()
    write_table(
        FALS_DIR / "02_long_horizon_placebo_shifts", placebos, "Long-Horizon Placebo Shifts"
    )
    permutations = permutation_rows()
    write_table(
        FALS_DIR / "03_long_horizon_permutation_tests",
        permutations,
        "Long-Horizon Permutation Tests",
    )
    text = """# Long-Horizon Falsification Interpretation

These tests ask whether recommendation-date returns differ from plausible
same-ticker non-event windows. If actual returns resemble matched controls,
shifted dates, or ticker-preserving permutations, the treatment-timing story is
weak and the evidence is better read as momentum selection or attention
synchronization.

The matched controls are diagnostic because event assignment is not random.
"""
    base.write_md(FALS_DIR / "04_long_horizon_falsification_interpretation.md", text)
    print(f"V2 long-horizon falsification complete: matched_rows={len(matched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
