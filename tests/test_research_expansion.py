from __future__ import annotations

import pandas as pd

from finfluencer_alpha.research_expansion import (
    BENCHMARK_TICKERS,
    PRE_EVENT_HORIZONS,
    SAMPLE_MODES,
    SECTOR_ETF_MAP,
    TICKER_TO_SECTOR_ETF,
    _apply_sample_mode,
    _clean,
    _next_trading_day,
)


def test_clean() -> None:
    assert _clean(None) == ""
    assert _clean("  foo  ") == "foo"
    assert _clean(123) == "123"


def test_next_trading_day() -> None:
    days = {"2024-01-02", "2024-01-03", "2024-01-04"}
    assert _next_trading_day("2024-01-01", days) == "2024-01-02"
    assert _next_trading_day("2024-01-02", days) == "2024-01-02"
    assert _next_trading_day("2024-01-05", days) is None


def test_apply_sample_mode_uncapped() -> None:
    df = pd.DataFrame({
        "creator": ["A", "A", "B", "B"],
        "published_at": ["2024-01-01", "2024-01-02", "2024-01-01", "2024-01-02"],
    })
    result = _apply_sample_mode(df, "uncapped_full")
    assert len(result) == 4


def test_apply_sample_mode_cap_250() -> None:
    df = pd.DataFrame({
        "creator": ["A"] * 300 + ["B"] * 10,
        "published_at": ["2024-01-01"] * 310,
    })
    result = _apply_sample_mode(df, "cap_250_per_creator")
    assert len(result[result["creator"] == "A"]) == 250
    assert len(result[result["creator"] == "B"]) == 10


def test_apply_sample_mode_cap_100_per_creator_year() -> None:
    df = pd.DataFrame({
        "creator": ["A"] * 150,
        "published_at": ["2024-01-01"] * 100 + ["2023-01-01"] * 50,
    })
    result = _apply_sample_mode(df, "cap_100_per_creator_year")
    assert len(result) == 100 + 50


def test_apply_sample_mode_balanced() -> None:
    df = pd.DataFrame({
        "creator": ["A"] * 10 + ["B"] * 2,
        "published_at": ["2024-01-01"] * 12,
    })
    result = _apply_sample_mode(df, "balanced_creator_year_sample")
    assert len(result) <= 12
    assert len(result[result["creator"] == "B"]) >= 1


def test_sector_map_coverage() -> None:
    assert "XLK" in SECTOR_ETF_MAP
    assert "AAPL" in TICKER_TO_SECTOR_ETF
    assert TICKER_TO_SECTOR_ETF["AAPL"] == "XLK"


def test_horizons_include_pre_event() -> None:
    assert "PRE_1W" in PRE_EVENT_HORIZONS
    assert "PRE_1M" in PRE_EVENT_HORIZONS
    assert "PRE_3M" in PRE_EVENT_HORIZONS


def test_benchmark_tickers() -> None:
    assert "SPY" in BENCHMARK_TICKERS
    assert "QQQ" in BENCHMARK_TICKERS
    assert "IWM" in BENCHMARK_TICKERS


def test_sample_modes() -> None:
    assert len(SAMPLE_MODES) == 6
    assert "uncapped_full" in SAMPLE_MODES
    assert "balanced_creator_year_sample" in SAMPLE_MODES
