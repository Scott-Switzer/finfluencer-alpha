"""Tests for information environment helpers."""

from __future__ import annotations

from scripts import information_environment_utils as ie


def test_narrative_relay_scores_detects_analyst_and_hype():
    text = "Wall Street analysts upgraded the price target. This could moon 10x — buy now."
    scores = ie.narrative_relay_scores(text)
    assert scores["analyst_relay_score"] >= 2
    assert scores["retail_hype_score"] >= 1
    assert scores["urgency_score"] >= 1


def test_load_api_key_from_env(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test-key-not-real")
    key, source = ie.load_api_key("FMP_API_KEY")
    assert key == "test-key-not-real"
    assert source == "environment"
    monkeypatch.delenv("FMP_API_KEY", raising=False)


def test_features_on_date_spy_regime():
    from datetime import date, timedelta

    import pandas as pd

    start = date(2020, 1, 1)
    rows = [{"date": start + timedelta(days=i), "spy_close": 100 + i * 0.1} for i in range(100)]
    spy = pd.DataFrame(rows)
    spy["spy_return_1d"] = spy["spy_close"].pct_change()
    vix = pd.DataFrame({"date": [start + timedelta(days=99)], "vix_level": [18.0], "vix_source": ["test"]})
    feat = ie.features_on_date(start + timedelta(days=99), spy, vix)
    assert "spy_prior_21d_return" in feat
    assert feat.get("vix_level") == 18.0
