"""Tests for expanded Alpha Vantage news layer (format, safety, unknown handling)."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
from scripts import build_v2_alpha_vantage_news_expanded as avx


def test_event_time_bounds_uses_yyyymmddthhmm() -> None:
    d = date(2024, 3, 15)
    a, b = avx.event_time_bounds(d, 5)
    assert re.match(r"^\d{8}T\d{4}$", a)
    assert re.match(r"^\d{8}T\d{4}$", b)
    assert a.endswith("0000")
    assert b.endswith("2359")


def test_unknown_rows_not_clean() -> None:
    events = pd.DataFrame(
        [
            {"event_id": 1, "ticker": "ABC", "company_name": "X", "event_date": "2024-01-10"},
        ]
    )
    plan = pd.DataFrame(
        [
            {
                "query_key": "evt_1_ABC",
                "event_id": 1,
                "ticker": "ABC",
                "query_status": "missing_runtime_key",
            }
        ]
    )
    panel = avx.map_events_to_panel(events, pd.DataFrame(), plan)
    assert len(panel) == 1
    row = panel.iloc[0]
    assert bool(row["av_expanded_news_unknown_flag"])
    assert not bool(row["av_expanded_news_clean_flag"])


def test_safe_log_row_has_no_secret_fields() -> None:
    row = {
        "query_key": "evt_1_Z",
        "event_id": 1,
        "ticker": "Z",
        "time_from": "20240101T0000",
        "time_to": "20240131T2359",
    }
    log = avx.safe_log_row(row, "ok", 0, "")
    assert "apikey" not in log
    assert "ALPHAVANTAGE" not in str(log).upper()
    keys = set(log.keys())
    assert "api_key" not in keys


def test_windows_are_5_21_63() -> None:
    assert avx.WINDOW_CAL_DAYS == [5, 21, 63]
