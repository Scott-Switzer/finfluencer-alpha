import tempfile
from pathlib import Path

import pandas as pd

from finfluencer_alpha.statistical_models import (
    _bootstrap_ci,
    _build_creator_alpha_table,
    _build_ticker_robustness,
    _build_window_robustness,
    _calc_window_stats,
    _permutation_test,
    _run_cross_sectional_regression,
    run_statistical_models,
)


def _make_event_study_df(n: int = 50, seed: int = 42) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "event_id": range(1, n + 1),
            "ticker": rng.choice(["AAPL", "META", "AMD", "DIS"], size=n),
            "data_ticker": rng.choice(["AAPL", "META", "AMD", "DIS"], size=n),
            "event_date_weekday_adjusted": pd.date_range("2024-01-01", periods=n, freq="B").astype(
                str
            ),
            "matched_market_date": pd.date_range("2024-01-01", periods=n, freq="B").astype(str),
            "recommendation_type": rng.choice(["buy", "sell", "price_target"], size=n),
            "direction": rng.choice(["positive", "negative"], size=n),
            "confidence": rng.uniform(0.5, 1.0, size=n),
            "adjusted_close": rng.uniform(100, 500, size=n),
            "benchmark_ticker": "SPY",
            "benchmark_adjusted_close": rng.uniform(400, 500, size=n),
            "return_1d": rng.normal(0.001, 0.02, size=n),
            "benchmark_return_1d": rng.normal(0.0005, 0.01, size=n),
            "abnormal_return_1d": rng.normal(0.0005, 0.015, size=n),
            "return_5d": rng.normal(0.005, 0.05, size=n),
            "benchmark_return_5d": rng.normal(0.002, 0.03, size=n),
            "abnormal_return_5d": rng.normal(0.003, 0.04, size=n),
            "data_source": "yfinance_yahoo_prototype",
        }
    )


def _make_clean_events_df(n: int = 50) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": range(1, n + 1),
            "creator": ["CreatorA"] * (n // 2) + ["CreatorB"] * (n // 2),
            "ticker": ["AAPL"] * (n // 4) + ["META"] * (n // 4) + ["AMD"] * (n // 4) + ["DIS"] * (n // 4),
            "recommendation_type": ["buy"] * n,
            "direction": ["positive"] * n,
            "confidence": [0.9] * n,
        }
    )


def test_calc_window_stats_basic():
    df = _make_event_study_df(n=100)
    ws = _calc_window_stats(df, "1D", "abnormal_return_1d")
    assert ws.window == "1D"
    assert ws.n == 100
    assert isinstance(ws.mean_ar, float)
    assert isinstance(ws.t_stat, float)
    assert isinstance(ws.p_value, float)
    assert 0 <= ws.win_rate <= 100


def test_calc_window_stats_empty():
    df = pd.DataFrame({"abnormal_return_1d": []})
    ws = _calc_window_stats(df, "1D", "abnormal_return_1d")
    assert ws.n == 0
    assert ws.mean_ar == 0.0
    assert ws.p_value == 1.0


def test_bootstrap_ci():
    ar = pd.Series([0.01, -0.005, 0.02, -0.01, 0.015])
    lower, upper = _bootstrap_ci(ar, n_boot=500, seed=42)
    assert lower < upper
    assert isinstance(lower, float)
    assert isinstance(upper, float)


def test_permutation_test():
    ar = pd.Series([0.01, 0.02, 0.015, 0.005, 0.01])
    p = _permutation_test(ar, n_perm=500, seed=42)
    assert 0 < p <= 1


def test_build_window_robustness():
    df = _make_event_study_df(n=50)
    robust = _build_window_robustness(df)
    assert not robust.empty
    assert "window" in robust.columns
    assert "bootstrap_ci_lower_pct" in robust.columns
    assert "permutation_p_value" in robust.columns


def test_run_cross_sectional_regression():
    df = _make_event_study_df(n=100)
    results = _run_cross_sectional_regression(df, "1D", "abnormal_return_1d")
    assert len(results) >= 1
    intercept = [r for r in results if r.model_type == "intercept_only"]
    assert len(intercept) == 1
    assert "const" in intercept[0].coefficients


def test_build_creator_alpha_table():
    events = _make_event_study_df(n=100)
    clean = _make_clean_events_df(n=100)
    alphas = _build_creator_alpha_table(events, clean)
    assert len(alphas) >= 1
    for ca in alphas:
        assert ca.n >= 3
        assert isinstance(ca.mean_car_1d, float)


def test_build_ticker_robustness():
    df = _make_event_study_df(n=100)
    robust = _build_ticker_robustness(df)
    assert not robust.empty
    assert "ticker" in robust.columns
    assert "significant_5pct" in robust.columns


def test_run_statistical_models_empty_inputs():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        result = run_statistical_models(
            event_study_path=Path("nonexistent.csv"),
            clean_events_path=Path("nonexistent.csv"),
            output_dir=out,
        )
        assert result.model_summary_path.exists()
        assert result.model_results_path.exists()
        assert len(result.window_stats) == 0


def test_run_statistical_models_with_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        event_path = tmp / "event_study_results.csv"
        clean_path = tmp / "clean_events.csv"
        _make_event_study_df(n=100).to_csv(event_path, index=False)
        _make_clean_events_df(n=100).to_csv(clean_path, index=False)

        out = tmp / "models"
        result = run_statistical_models(
            event_study_path=event_path,
            clean_events_path=clean_path,
            output_dir=out,
        )
        assert result.model_summary_path.exists()
        assert result.model_results_path.exists()
        assert result.creator_alpha_path.exists()
        assert result.ticker_robustness_path.exists()
        assert result.event_window_robustness_path.exists()
        assert len(result.window_stats) >= 1
        assert len(result.notes) >= 1

        # Verify CSV contents
        results_df = pd.read_csv(result.model_results_path)
        assert not results_df.empty
        creator_df = pd.read_csv(result.creator_alpha_path)
        assert not creator_df.empty
