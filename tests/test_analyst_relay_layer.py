"""Tests for analyst relay classification and key loading."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from scripts import build_v2_analyst_relay_layer as ar
from scripts import information_environment_utils as ie


def test_load_api_key_from_marketdata_env(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "fin496"
    cfg.mkdir()
    env_file = cfg / "marketdata.env"
    env_file.write_text("FMP_API_KEY=test-fmp\nFINNHUB_API_KEY=test-fh\n", encoding="utf-8")
    monkeypatch.setattr(ie, "config_dir", lambda: cfg)
    monkeypatch.setattr(ie, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    key, source = ie.load_api_key("FMP_API_KEY")
    assert key == "test-fmp"
    assert source == "marketdata_env"


def test_finnhub_alias_finhub(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "fin496"
    cfg.mkdir()
    (cfg / "marketdata.env").write_text("FINHUB_API_KEY=alias-key\n", encoding="utf-8")
    monkeypatch.setattr(ie, "config_dir", lambda: cfg)
    monkeypatch.setattr(ie, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("FINHUB_API_KEY", raising=False)
    key, _ = ie.load_api_key("FINNHUB_API_KEY")
    assert key == "alias-key"


def test_pick_event_time_uses_pre_event_row() -> None:
    ed = date(2024, 6, 1)
    hist = pd.DataFrame(
        [
            {
                "record_date": (ed + timedelta(days=10)).isoformat(),
                "source": "fmp_grade",
                "buy_count": 5,
                "sell_count": 0,
                "hold_count": 0,
            },
            {
                "record_date": (ed - timedelta(days=5)).isoformat(),
                "source": "fmp_grade",
                "buy_count": 3,
                "sell_count": 1,
                "hold_count": 1,
            },
        ]
    )
    latest, _, _ = ar.pick_event_time_row(hist, ed)
    assert latest is not None
    assert latest["record_date"] <= ed.isoformat()


def test_diagnostic_current_only_when_no_dated_rows() -> None:
    ev = pd.Series({"event_date": "2024-01-15", "recommendation_type": "buy"})
    cls = ar.build_event_classification(
        ev,
        pd.DataFrame(),
        {"fmp_snapshots": [{"target_mean": 100}], "fmp_provider_status": "ok", "fmp_latest_only": True},
        {},
        {},
        90.0,
    )
    assert cls["diagnostic_current_only"] is True
    assert cls["analyst_event_time_usable"] is False


def test_bullish_alignment() -> None:
    ed = date(2024, 1, 15)
    hist = pd.DataFrame(
        [{"record_date": "2024-01-10", "buy_count": 10, "sell_count": 0, "hold_count": 1, "source": "fmp"}]
    )
    ev = pd.Series({"event_date": ed.isoformat(), "recommendation_type": "buy"})
    cls = ar.build_event_classification(ev, hist, {"fmp_has_event_time_data": True}, {}, {}, 100.0)
    assert cls["analyst_event_time_usable"] is True
    assert cls["analyst_bullish_aligned"] is True
    assert cls["analyst_unknown"] is False


def test_contrarian_classification() -> None:
    ed = date(2024, 1, 15)
    hist = pd.DataFrame(
        [{"record_date": "2024-01-10", "buy_count": 0, "sell_count": 10, "hold_count": 1, "source": "fmp"}]
    )
    ev = pd.Series({"event_date": ed.isoformat(), "recommendation_type": "buy"})
    cls = ar.build_event_classification(ev, hist, {}, {}, {}, None)
    assert cls["finfluencer_contrarian_to_analyst"] is True


def test_yfinance_flagged_diagnostic() -> None:
    ev = pd.Series({"event_date": "2024-01-15", "recommendation_type": "buy"})
    yf = {
        "yfinance_has_data": True,
        "diagnostic_yfinance_fallback": True,
        "yf_recommendation_key": "buy",
        "yf_target_mean": 110,
        "yf_reference_price": 100,
    }
    cls = ar.build_event_classification(ev, pd.DataFrame(), {}, {}, yf, 100.0)
    assert cls["diagnostic_yfinance_fallback"] is True


def test_yfinance_rejects_future_dated_rows() -> None:
    from scripts.build_v2_yfinance_analyst_diagnostic_layer import pick_pre_event_row

    ed = date(2024, 6, 1)
    hist = pd.DataFrame(
        [
            {"record_date": "2024-07-01", "action": "upgrade", "to_grade": "buy"},
            {"record_date": "2024-05-01", "action": "hold", "to_grade": "hold"},
        ]
    )
    latest, _, _ = pick_pre_event_row(hist, ed)
    assert latest is not None
    assert latest["record_date"] == "2024-05-01"


def test_merge_yfinance_does_not_overwrite_fmp_event_time() -> None:
    base = pd.DataFrame(
        [
            {
                "event_id": "e1",
                "analyst_event_time_usable": True,
                "analyst_alignment": "analyst_bullish_aligned",
                "primary_analyst_source": "fmp_grade",
                "analyst_unknown": False,
                "diagnostic_current_only": False,
                "analyst_relay_likely": True,
            }
        ]
    )
    yf = pd.DataFrame(
        [
            {
                "event_id": "e1",
                "yf_event_time_usable": True,
                "yf_event_time_bullish_aligned": False,
                "yf_event_time_bearish_aligned": True,
                "yf_snapshot_available": True,
                "yf_current_bullish_aligned": True,
            }
        ]
    )
    merged = ar.merge_yfinance_diagnostic_panel(base, yf)
    assert merged.loc[0, "analyst_event_time_source"] == "fmp"
    assert merged.loc[0, "analyst_alignment_event_time"] == "analyst_bullish_aligned"
    assert merged.loc[0, "analyst_alignment_diagnostic"] == "analyst_bullish_aligned"


def test_merge_yfinance_fills_event_time_gap() -> None:
    base = pd.DataFrame(
        [
            {
                "event_id": "e2",
                "analyst_event_time_usable": False,
                "analyst_alignment": "analyst_unknown",
                "primary_analyst_source": "",
                "analyst_unknown": True,
                "diagnostic_current_only": False,
                "analyst_relay_likely": False,
            }
        ]
    )
    yf = pd.DataFrame(
        [
            {
                "event_id": "e2",
                "yf_event_time_usable": True,
                "yf_event_time_bullish_aligned": True,
                "yf_snapshot_available": True,
                "yf_diagnostic_current_only": False,
                "yf_analyst_relay_likely_event_time": True,
            }
        ]
    )
    merged = ar.merge_yfinance_diagnostic_panel(base, yf)
    assert merged.loc[0, "analyst_event_time_source"] == "yfinance"
    assert merged.loc[0, "analyst_coverage_tier"] == "event_time_yfinance"
    assert merged.loc[0, "analyst_alignment_event_time"] == "analyst_bullish_aligned"


def test_yfinance_current_only_stays_diagnostic() -> None:
    base = pd.DataFrame(
        [
            {
                "event_id": "e3",
                "analyst_event_time_usable": False,
                "analyst_alignment": "analyst_unknown",
                "primary_analyst_source": "",
                "analyst_unknown": True,
                "diagnostic_current_only": False,
                "analyst_relay_likely": False,
            }
        ]
    )
    yf = pd.DataFrame(
        [
            {
                "event_id": "e3",
                "yf_event_time_usable": False,
                "yf_snapshot_available": True,
                "yf_diagnostic_current_only": True,
                "yf_current_bullish_aligned": True,
            }
        ]
    )
    merged = ar.merge_yfinance_diagnostic_panel(base, yf)
    assert not bool(merged.loc[0, "analyst_event_time_usable"])
    assert bool(merged.loc[0, "analyst_diagnostic_current_only"])
    assert merged.loc[0, "analyst_coverage_tier"] == "diagnostic_current_snapshot"


@patch("scripts.build_v2_analyst_relay_layer.fetch_fmp_ticker")
@patch("scripts.build_v2_analyst_relay_layer.fetch_finnhub_ticker")
def test_fmp_failure_falls_through_to_finnhub(mock_fh, mock_fmp) -> None:
    mock_fmp.return_value = ([], {"fmp_provider_status": "http_429", "fmp_error_class_safe": "http_429"})
    mock_fh.return_value = (
        [{"ticker": "AAPL", "record_date": "2024-01-01", "buy_count": 5, "sell_count": 0, "hold_count": 1}],
        {"finnhub_provider_status": "ok", "finnhub_has_event_time_data": True},
    )
    log: list = []
    h, meta = mock_fh("AAPL", "k", log)
    assert meta["finnhub_has_event_time_data"] is True
