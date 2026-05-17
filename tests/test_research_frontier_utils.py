"""Tests for research frontier utilities."""

from __future__ import annotations

from scripts import research_frontier_utils as rf


def test_language_scores_counts_keywords() -> None:
    scores = rf.language_scores("This stock could moon but there is risk and I own shares")
    assert scores["hype_score"] >= 1
    assert scores["risk_warning_score"] >= 1
    assert scores["disclosure_score"] >= 1


def test_placebo_indices_respects_event_positions() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=200),
            "adjusted_close": range(200),
            "benchmark_adjusted_close": range(200),
            "daily_stock_return": 0.001,
            "daily_spy_return": 0.0005,
            "daily_spy_ar": 0.0005,
        }
    )
    frame["date"] = frame["date"].dt.date
    idx = 100
    taken = {100, 101}
    placebos = rf.placebo_indices(frame, idx, taken, shifts=[-30, 30], n_random=1)
    assert all(p not in taken for _, p in placebos)
