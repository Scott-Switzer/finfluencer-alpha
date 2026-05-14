from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from finfluencer_alpha.research_expansion import (
    BENCHMARK_TICKERS,
    PRE_EVENT_HORIZONS,
    SAMPLE_MODES,
    SECTOR_ETF_MAP,
    TICKER_TO_SECTOR_ETF,
    _apply_sample_mode,
    _clean,
    _next_trading_day,
    build_event_window_returns,
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


def test_apply_sample_mode_cap_500() -> None:
    df = pd.DataFrame({
        "creator": ["A"] * 600 + ["B"] * 20,
        "published_at": ["2024-01-01"] * 620,
    })
    result = _apply_sample_mode(df, "cap_500_per_creator")
    assert len(result[result["creator"] == "A"]) == 500
    assert len(result[result["creator"] == "B"]) == 20


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


def test_apply_sample_mode_balanced_changes_imbalanced_composition() -> None:
    df = pd.DataFrame({
        "creator": ["A"] * 100 + ["B"] * 2,
        "published_at": ["2024-01-01"] * 102,
    })
    result = _apply_sample_mode(df, "balanced_creator_year_sample")
    assert len(result) < len(df)
    assert (
        result["creator"].value_counts(normalize=True).max()
        < df["creator"].value_counts(normalize=True).max()
    )


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


def _write_event_window_inputs(
    tmp_path: Path,
    events: pd.DataFrame,
    market: pd.DataFrame,
) -> tuple[Path, Path, Path]:
    events_path = tmp_path / "events.csv"
    market_path = tmp_path / "market.csv"
    out_dir = tmp_path / "out"
    events.to_csv(events_path, index=False)
    market.to_csv(market_path, index=False)
    return events_path, market_path, out_dir


def _synthetic_market(
    include_benchmark: bool = True,
    duplicate_stock_row: bool = False,
) -> pd.DataFrame:
    dates = pd.bdate_range("2023-09-01", periods=320).strftime("%Y-%m-%d")
    rows = []
    for i, date in enumerate(dates):
        rows.append({"ticker": "AAA", "date": date, "adjusted_close": 100 + i})
        if duplicate_stock_row and i == 90:
            rows.append({"ticker": "AAA", "date": date, "adjusted_close": 100 + i})
        if include_benchmark:
            rows.append({"ticker": "SPY", "date": date, "adjusted_close": 200 + i})
    return pd.DataFrame(rows)


def _single_event(date: str = "2024-01-06") -> pd.DataFrame:
    return pd.DataFrame([{
        "event_id": "1",
        "video_id": "v1",
        "creator": "Creator",
        "ticker": "AAA",
        "recommendation_type": "buy",
        "direction": "positive",
        "published_at": f"{date}T12:00:00Z",
        "event_date_utc": date,
    }])


def _event_windows(tmp_path: Path, events: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    events_path, market_path, out_dir = _write_event_window_inputs(tmp_path, events, market)
    result_path = build_event_window_returns(events_path, market_path, out_dir)
    return pd.read_csv(result_path)


def test_event_window_weekend_maps_to_next_trading_day(tmp_path: Path) -> None:
    df = _event_windows(tmp_path, _single_event("2024-01-06"), _synthetic_market())
    row = df[df["window"] == "1D"].iloc[0]
    assert row["next_trading_day"] == "2024-01-08"


def test_event_window_1d_uses_trading_day_sequence_and_abnormal_return(tmp_path: Path) -> None:
    df = _event_windows(tmp_path, _single_event("2024-01-08"), _synthetic_market())
    row = df[df["window"] == "1D"].iloc[0]
    start_idx = list(pd.bdate_range("2023-09-01", periods=320).strftime("%Y-%m-%d")).index(
        "2024-01-08"
    )
    stock_return = ((100 + start_idx + 1) / (100 + start_idx)) - 1
    benchmark_return = ((200 + start_idx + 1) / (200 + start_idx)) - 1
    assert row["raw_stock_return"] == pytest.approx(round(stock_return, 6), abs=1e-6)
    assert row["abnormal_return_SPY"] == pytest.approx(
        round(round(stock_return, 6) - round(benchmark_return, 6), 6),
        abs=1e-6,
    )


def test_event_window_5d_21d_63d_use_trading_days(tmp_path: Path) -> None:
    df = _event_windows(tmp_path, _single_event("2024-01-08"), _synthetic_market())
    assert {"1W", "1M", "3M"}.issubset(set(df["window"]))
    starts = df[df["window"].isin(["1W", "1M", "3M"])]
    assert starts["next_trading_day"].eq("2024-01-08").all()


def test_event_window_long_windows_invalid_without_future_data(tmp_path: Path) -> None:
    market = _synthetic_market().head(40)
    df = _event_windows(tmp_path, _single_event("2023-09-04"), market)
    assert "1Y" not in set(df["window"])
    assert "2Y" not in set(df["window"])


def test_event_window_end_of_sample_uses_last_future_price(tmp_path: Path) -> None:
    market = _synthetic_market().head(20)
    df = _event_windows(tmp_path, _single_event("2023-09-04"), market)
    row = df[df["window"] == "END_OF_SAMPLE"].iloc[0]
    assert row["raw_stock_return"] == pytest.approx(round((109 / 101) - 1, 6), abs=1e-6)


def test_event_window_pre_windows_use_only_pre_event_prices(tmp_path: Path) -> None:
    df = _event_windows(tmp_path, _single_event("2024-01-08"), _synthetic_market())
    assert {"PRE_1W", "PRE_1M", "PRE_3M"}.issubset(set(df["window"]))
    pre = df[df["window"].str.startswith("PRE_")]
    assert pre["next_trading_day"].eq("2024-01-08").all()


def test_event_window_abnormal_return_equals_stock_minus_benchmark(tmp_path: Path) -> None:
    df = _event_windows(tmp_path, _single_event("2024-01-08"), _synthetic_market())
    row = df[df["window"] == "1W"].iloc[0]
    assert row["abnormal_return_SPY"] == pytest.approx(
        row["raw_stock_return"] - row["benchmark_return_SPY"],
        abs=1e-6,
    )


def test_event_window_missing_benchmark_leaves_abnormal_return_missing(tmp_path: Path) -> None:
    df = _event_windows(
        tmp_path,
        _single_event("2024-01-08"),
        _synthetic_market(include_benchmark=False),
    )
    assert "abnormal_return_SPY" not in df.columns or df["abnormal_return_SPY"].isna().all()


def test_event_window_duplicate_price_rows_do_not_duplicate_windows(tmp_path: Path) -> None:
    df = _event_windows(
        tmp_path,
        _single_event("2024-01-08"),
        _synthetic_market(duplicate_stock_row=True),
    )
    assert df.groupby(["event_id", "window"]).size().max() == 1


def test_event_window_uses_embedded_spy_benchmark_columns(tmp_path: Path) -> None:
    market = _synthetic_market(include_benchmark=False)
    market["benchmark_ticker"] = "SPY"
    market["benchmark_adjusted_close"] = [200 + i for i in range(len(market))]
    df = _event_windows(tmp_path, _single_event("2024-01-08"), market)
    assert "abnormal_return_SPY" in df.columns
    assert df[df["window"] == "1D"]["abnormal_return_SPY"].notna().all()
