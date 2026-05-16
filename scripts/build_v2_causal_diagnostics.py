from __future__ import annotations

import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
CAUSAL_DIR = OUT_DIR / "causal_diagnostics"
CAUSAL_DIR.mkdir(parents=True, exist_ok=True)
RNG = random.Random(496)


def event_index(event: base.EventRecord, market: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], int | None]:
    rows = market.get(event.data_ticker, [])
    if not rows or event.weekday_adjusted_date is None:
        return rows, None
    return rows, base.first_on_or_after(rows, event.weekday_adjusted_date)


def window_ar(rows: list[dict[str, Any]], idx: int | None, start: int, end: int) -> float | None:
    if idx is None:
        return None
    i0 = idx + start
    i1 = idx + end
    if i0 < 0 or i1 < 0 or i0 >= len(rows) or i1 >= len(rows):
        return None
    stock0 = rows[i0]["adjusted_close"]
    stock1 = rows[i1]["adjusted_close"]
    bench0 = rows[i0]["benchmark_adjusted_close"]
    bench1 = rows[i1]["benchmark_adjusted_close"]
    if not stock0 or not bench0:
        return None
    return (stock1 / stock0 - 1.0) - (bench1 / bench0 - 1.0)


def summarize_values(label: str, values: list[float], notes: str = "") -> dict[str, Any]:
    stats = base.t_test(values)
    return {
        "specification": label,
        "n": stats["n"],
        "mean_ar": base.fmt(stats["mean"]),
        "median_ar": base.fmt(stats["median"]),
        "t_stat": base.fmt(stats["t"], 3),
        "p_value": base.fmt(stats["p"], 6),
        "win_rate": base.fmt(stats["win_rate"], 6),
        "notes": notes,
    }


def build_pretrend(events: list[base.EventRecord], market: dict[str, list[dict[str, Any]]]) -> None:
    windows = [("-20_-1", -20, -1), ("-10_-1", -10, -1), ("-5_-1", -5, -1), ("-3_-1", -3, -1)]
    samples = {
        "all": lambda event: True,
        "top5": lambda event: event.ticker in base.TOP5_TICKERS,
        "non_top": lambda event: event.ticker not in base.TOP5_TICKERS,
        "low_lookahead": lambda event: event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS,
    }
    rows = []
    for sample, predicate in samples.items():
        for name, start, end in windows:
            values = []
            for event in events:
                if not predicate(event):
                    continue
                market_rows, idx = event_index(event, market)
                value = window_ar(market_rows, idx, start, end)
                if value is not None:
                    values.append(value)
            rows.append(summarize_values(f"{sample} AR_{name}", values, "pre-event abnormal return"))
    columns = list(rows[0])
    base.write_csv(CAUSAL_DIR / "01_v2_pretrend_tests.csv", rows, columns)
    base.write_md(
        CAUSAL_DIR / "01_v2_pretrend_tests.md",
        "# V2 Pretrend Tests\n\n"
        + base.markdown_table(rows, columns)
        + "\n\nPositive pretrends indicate creators may select into already-moving stocks.",
    )


def build_decay(events: list[base.EventRecord], market: dict[str, list[dict[str, Any]]]) -> None:
    windows = [
        ("0_1", 0, 1),
        ("0_2", 0, 2),
        ("0_3", 0, 3),
        ("0_5", 0, 5),
        ("0_10", 0, 10),
        ("0_20", 0, 20),
        ("6_20", 6, 20),
        ("11_20", 11, 20),
    ]
    samples = {
        "all": lambda event: True,
        "top5": lambda event: event.ticker in base.TOP5_TICKERS,
        "non_top": lambda event: event.ticker not in base.TOP5_TICKERS,
    }
    rows = []
    for sample, predicate in samples.items():
        for name, start, end in windows:
            values = []
            for event in events:
                if not predicate(event):
                    continue
                market_rows, idx = event_index(event, market)
                value = window_ar(market_rows, idx, start, end)
                if value is not None:
                    values.append(value)
            rows.append(summarize_values(f"{sample} AR_{name}", values, "post-event decay/reversal"))
    columns = list(rows[0])
    base.write_csv(CAUSAL_DIR / "02_v2_post_event_decay_curve.csv", rows, columns)
    base.write_md(
        CAUSAL_DIR / "02_v2_post_event_decay_curve.md",
        "# V2 Post-Event Decay Curve\n\n" + base.markdown_table(rows, columns),
    )


def build_placebo(events: list[base.EventRecord], market: dict[str, list[dict[str, Any]]]) -> None:
    shifts = [-60, -30, 30, 60]
    rows = []
    for shift in shifts:
        values = []
        actual = []
        for event in events:
            market_rows, idx = event_index(event, market)
            if idx is None:
                continue
            placebo = window_ar(market_rows, idx + shift, 0, 5)
            observed = window_ar(market_rows, idx, 0, 5)
            if placebo is not None:
                values.append(placebo)
            if observed is not None:
                actual.append(observed)
        placebo_stats = base.t_test(values)
        actual_stats = base.t_test(actual)
        rows.append(
            {
                "shift_trading_days": shift,
                "actual_n": actual_stats["n"],
                "actual_mean_5d_ar": base.fmt(actual_stats["mean"]),
                "placebo_n": placebo_stats["n"],
                "placebo_mean_5d_ar": base.fmt(placebo_stats["mean"]),
                "placebo_t": base.fmt(placebo_stats["t"], 3),
                "placebo_p": base.fmt(placebo_stats["p"], 6),
                "actual_minus_placebo": base.fmt(
                    None
                    if actual_stats["mean"] is None or placebo_stats["mean"] is None
                    else float(actual_stats["mean"]) - float(placebo_stats["mean"])
                ),
            }
        )
    columns = list(rows[0])
    base.write_csv(CAUSAL_DIR / "03_v2_placebo_shift_tests.csv", rows, columns)
    base.write_md(
        CAUSAL_DIR / "03_v2_placebo_shift_tests.md",
        "# V2 Placebo Shift Tests\n\n" + base.markdown_table(rows, columns),
    )


def build_permutation(events: list[base.EventRecord], market: dict[str, list[dict[str, Any]]]) -> None:
    ticker_indices: dict[str, list[int]] = defaultdict(list)
    observed = []
    for event in events:
        rows, idx = event_index(event, market)
        value = window_ar(rows, idx, 0, 5)
        if value is not None and idx is not None:
            ticker_indices[event.data_ticker].append(idx)
            observed.append(value)
    observed_mean = sum(observed) / len(observed)
    permutation_means = []
    for _ in range(500):
        values = []
        for event in events:
            rows = market.get(event.data_ticker, [])
            candidates = ticker_indices.get(event.data_ticker, [])
            if not rows or not candidates:
                continue
            idx = RNG.choice(candidates)
            value = window_ar(rows, idx, 0, 5)
            if value is not None:
                values.append(value)
        if values:
            permutation_means.append(sum(values) / len(values))
    p_value = sum(abs(x) >= abs(observed_mean) for x in permutation_means) / len(permutation_means)
    rows = [
        {
            "test": "shuffle_event_dates_within_ticker",
            "permutations": len(permutation_means),
            "observed_mean_5d_ar": base.fmt(observed_mean),
            "permutation_mean": base.fmt(sum(permutation_means) / len(permutation_means)),
            "permutation_p_value": base.fmt(p_value, 6),
            "notes": "preserves ticker event-count structure",
        }
    ]
    base.write_csv(CAUSAL_DIR / "04_v2_permutation_tests.csv", rows, list(rows[0]))
    base.write_md(
        CAUSAL_DIR / "04_v2_permutation_tests.md",
        "# V2 Permutation Tests\n\n" + base.markdown_table(rows, list(rows[0])),
    )


def build_matched_controls(events: list[base.EventRecord], market: dict[str, list[dict[str, Any]]]) -> None:
    event_indices: dict[str, set[int]] = defaultdict(set)
    for event in events:
        _rows, idx = event_index(event, market)
        if idx is not None:
            event_indices[event.data_ticker].add(idx)
    treated, controls, pair_rows = [], [], []
    for event in events:
        rows, idx = event_index(event, market)
        if idx is None:
            continue
        actual = window_ar(rows, idx, 0, 5)
        pre = window_ar(rows, idx, -20, -1)
        if actual is None or pre is None:
            continue
        candidates = []
        event_month = rows[idx]["date"].month
        for cand in range(20, len(rows) - 20):
            if rows[cand]["date"].month != event_month:
                continue
            if any(abs(cand - used) <= 5 for used in event_indices[event.data_ticker]):
                continue
            cand_pre = window_ar(rows, cand, -20, -1)
            cand_post = window_ar(rows, cand, 0, 5)
            if cand_pre is None or cand_post is None:
                continue
            candidates.append((abs(cand_pre - pre), cand, cand_post))
        if not candidates:
            continue
        _dist, control_idx, control_return = min(candidates, key=lambda item: item[0])
        treated.append(actual)
        controls.append(control_return)
        pair_rows.append(
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "event_date": rows[idx]["date"].isoformat(),
                "control_date": rows[control_idx]["date"].isoformat(),
                "treated_5d_ar": base.fmt(actual),
                "control_5d_ar": base.fmt(control_return),
                "difference": base.fmt(actual - control_return),
            }
        )
    diff = [a - b for a, b in zip(treated, controls, strict=True)]
    summary = [
        summarize_values("treated_5d_ar", treated),
        summarize_values("matched_control_5d_ar", controls),
        summarize_values("treated_minus_control", diff, "same ticker/month and similar pretrend"),
    ]
    base.write_csv(CAUSAL_DIR / "05_v2_matched_control_tests.csv", summary, list(summary[0]))
    base.write_md(
        CAUSAL_DIR / "05_v2_matched_control_tests.md",
        "# V2 Matched Control Tests\n\n"
        + base.markdown_table(summary, list(summary[0]))
        + f"\n\nMatched pairs constructed: `{len(pair_rows)}`.",
    )
    base.write_csv(
        CAUSAL_DIR / "05_v2_matched_control_pairs_preview.csv",
        pair_rows[:250],
        list(pair_rows[0]) if pair_rows else ["event_id"],
    )


def build_did_memo() -> None:
    matched = pd.read_csv(CAUSAL_DIR / "05_v2_matched_control_tests.csv")
    row = matched.loc[matched["specification"].eq("treated_minus_control")].iloc[0]
    rows = [
        {
            "diagnostic": "matched_ticker_month_difference",
            "n": row["n"],
            "mean_difference": row["mean_ar"],
            "t_stat": row["t_stat"],
            "p_value": row["p_value"],
            "status": "diagnostic_not_causal",
            "notes": "same ticker/month matched controls approximate a DiD-style contrast without random assignment",
        }
    ]
    base.write_csv(CAUSAL_DIR / "06_v2_did_diagnostic.csv", rows, list(rows[0]))
    base.write_md(
        CAUSAL_DIR / "06_v2_did_diagnostic.md",
        "# V2 Difference-in-Differences Style Diagnostic\n\n" + base.markdown_table(rows, list(rows[0])),
    )


def write_causal_memo() -> None:
    text = """# V2 Causal Identification Memo

The v2 event study estimates abnormal returns by comparing realized stock returns
around YouTube recommendation events with modeled normal returns. It is not a
causal design.

Main identification threats:

- Simultaneity with existing news, price momentum, and retail attention.
- Creator selection into already-trending stocks.
- YouTube upload timestamps may lag recording or private preview timing.
- Repeated recommendation clusters can amplify a common underlying event.
- Retail attention and public information are hard to separate with free data.
- There is no random assignment of recommendations to tickers or dates.

The falsification tests in this folder should be interpreted as stress tests for
the causal story. Passing them would not prove causality; failing or weakening
them should narrow the claim to attention amplification and heterogeneous
association.
"""
    base.write_md(CAUSAL_DIR / "07_v2_causal_identification_memo.md", text)


def main() -> int:
    market = base.load_market_data()
    events = base.fetch_events(market)
    build_pretrend(events, market)
    build_decay(events, market)
    build_placebo(events, market)
    build_permutation(events, market)
    build_matched_controls(events, market)
    build_did_memo()
    write_causal_memo()
    print("V2 causal diagnostics complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
