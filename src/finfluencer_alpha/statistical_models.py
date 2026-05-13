from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .config import EXPORTS_DIR
from .utils import configure_csv_field_size_limit

STATISTICAL_MODELS_DIR = EXPORTS_DIR / "statistical_models"

MODEL_SUMMARY_PATH = STATISTICAL_MODELS_DIR / "model_summary.md"
MODEL_RESULTS_PATH = STATISTICAL_MODELS_DIR / "model_results.csv"
CREATOR_ALPHA_PATH = STATISTICAL_MODELS_DIR / "creator_alpha_table.csv"
TICKER_ROBUSTNESS_PATH = STATISTICAL_MODELS_DIR / "ticker_robustness_table.csv"
EVENT_WINDOW_ROBUSTNESS_PATH = STATISTICAL_MODELS_DIR / "event_window_robustness.csv"

EVENT_STUDY_RESULTS_PATH = EXPORTS_DIR / "event_study" / "event_study_results.csv"
CLEAN_EVENTS_PATH = EXPORTS_DIR / "validation" / "clean_auto_labeled_events.csv"

WINDOW_COLUMNS = {
    "1D": "abnormal_return_1d",
    "5D": "abnormal_return_5d",
}

PERCENTAGE_MULTIPLIER = 100


@dataclass(frozen=True)
class WindowStats:
    window: str
    n: int
    mean_ar: float
    median_ar: float
    std_ar: float
    t_stat: float
    p_value: float
    win_rate: float
    ci_lower: float
    ci_upper: float


@dataclass(frozen=True)
class RegressionResult:
    window: str
    model_type: str
    r_squared: float
    adj_r_squared: float
    n_obs: int
    coefficients: dict[str, dict[str, float]]
    notes: str


@dataclass(frozen=True)
class CreatorAlpha:
    creator: str
    n: int
    mean_car_1d: float
    mean_car_5d: float
    median_car: float
    win_rate_1d: float
    t_stat_1d: float
    p_value_1d: float
    t_stat_5d: float
    p_value_5d: float
    significance_flag: str


@dataclass(frozen=True)
class StatisticalModelResult:
    model_summary_path: Path
    model_results_path: Path
    creator_alpha_path: Path
    ticker_robustness_path: Path
    event_window_robustness_path: Path
    window_stats: list[WindowStats]
    regression_results: list[RegressionResult]
    creator_alphas: list[CreatorAlpha]
    notes: list[str]


def _read_csv(path: Path) -> pd.DataFrame:
    configure_csv_field_size_limit()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _safe_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _calc_window_stats(df: pd.DataFrame, window: str, col: str) -> WindowStats:
    ar = _safe_float(df[col]).dropna()
    n = len(ar)
    if n < 2:
        return WindowStats(
            window=window,
            n=n,
            mean_ar=0.0,
            median_ar=0.0,
            std_ar=0.0,
            t_stat=0.0,
            p_value=1.0,
            win_rate=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
        )
    mean_ar = float(ar.mean()) * PERCENTAGE_MULTIPLIER
    median_ar = float(ar.median()) * PERCENTAGE_MULTIPLIER
    std_ar = float(ar.std(ddof=1)) * PERCENTAGE_MULTIPLIER
    se = std_ar / np.sqrt(n)
    t_stat = mean_ar / se if se > 0 else 0.0
    p_value = 2 * (1 - stats_t_cdf(abs(t_stat), n - 1)) if se > 0 else 1.0
    win_rate = float((ar > 0).mean()) * PERCENTAGE_MULTIPLIER
    ci_lower = mean_ar - 1.96 * se
    ci_upper = mean_ar + 1.96 * se
    return WindowStats(
        window=window,
        n=n,
        mean_ar=mean_ar,
        median_ar=median_ar,
        std_ar=std_ar,
        t_stat=t_stat,
        p_value=p_value,
        win_rate=win_rate,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
    )


def _bootstrap_ci(ar: pd.Series, n_boot: int = 1000, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(ar)
    if n < 2:
        return 0.0, 0.0
    boot_means = []
    for _ in range(n_boot):
        sample = ar.iloc[rng.integers(0, n, size=n)]
        boot_means.append(sample.mean())
    boot_arr = np.array(boot_means) * PERCENTAGE_MULTIPLIER
    return float(np.percentile(boot_arr, 2.5)), float(np.percentile(boot_arr, 97.5))


def _permutation_test(ar: pd.Series, n_perm: int = 1000, seed: int = 42) -> float:
    rng = np.random.default_rng(seed)
    n = len(ar)
    if n < 2:
        return 1.0
    observed = abs(ar.mean())
    count = 0
    for _ in range(n_perm):
        signs = rng.choice([-1, 1], size=n)
        perm_mean = abs((ar * signs).mean())
        if perm_mean >= observed:
            count += 1
    return max(count / n_perm, 1 / n_perm)


def _build_window_robustness(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for window, col in WINDOW_COLUMNS.items():
        ar = _safe_float(df[col]).dropna()
        if len(ar) < 2:
            continue
        boot_lower, boot_upper = _bootstrap_ci(ar)
        perm_p = _permutation_test(ar)
        rows.append(
            {
                "window": window,
                "n": len(ar),
                "bootstrap_ci_lower_pct": boot_lower,
                "bootstrap_ci_upper_pct": boot_upper,
                "permutation_p_value": perm_p,
                "method": "sign-flip permutation",
            }
        )
    return pd.DataFrame(rows)


def _run_cross_sectional_regression(
    df: pd.DataFrame, window: str, ar_col: str
) -> list[RegressionResult]:
    results = []
    df = df.copy()
    df["ar"] = _safe_float(df[ar_col])
    df = df.dropna(subset=["ar"])
    if len(df) < 10:
        results.append(
            RegressionResult(
                window=window,
                model_type="OLS",
                r_squared=0.0,
                adj_r_squared=0.0,
                n_obs=len(df),
                coefficients={},
                notes=f"Sample size too small for regression (N={len(df)}).",
            )
        )
        return results

    # Build dummy variables
    if "recommendation_type" in df.columns:
        dummies = pd.get_dummies(df["recommendation_type"], prefix="rec", drop_first=True)
        df = pd.concat([df, dummies], axis=1)
    if "direction" in df.columns:
        dummies = pd.get_dummies(df["direction"], prefix="dir", drop_first=True)
        df = pd.concat([df, dummies], axis=1)

    # Base spec: intercept only
    X = pd.DataFrame({"const": 1.0}, index=df.index)
    y = df["ar"]
    model = sm.OLS(y, X).fit(cov_type="HC1")
    results.append(
        RegressionResult(
            window=window,
            model_type="intercept_only",
            r_squared=float(model.rsquared),
            adj_r_squared=float(model.rsquared_adj),
            n_obs=int(model.nobs),
            coefficients={
                "const": {
                    "coef": float(model.params["const"]) * PERCENTAGE_MULTIPLIER,
                    "std_err": float(model.bse["const"]) * PERCENTAGE_MULTIPLIER,
                    "p_value": float(model.pvalues["const"]),
                }
            },
            notes="Heteroskedasticity-robust SE (HC1).",
        )
    )

    # Extended spec with recommendation type
    rec_cols = [c for c in df.columns if c.startswith("rec_")]
    if rec_cols:
        X_ext = pd.DataFrame({"const": 1.0}, index=df.index)
        for c in rec_cols:
            X_ext[c] = df[c].astype(float)
        try:
            model_ext = sm.OLS(y, X_ext).fit(cov_type="HC1")
            coefs = {}
            for c in X_ext.columns:
                coefs[c] = {
                    "coef": float(model_ext.params[c]) * PERCENTAGE_MULTIPLIER,
                    "std_err": float(model_ext.bse[c]) * PERCENTAGE_MULTIPLIER,
                    "p_value": float(model_ext.pvalues[c]),
                }
            results.append(
                RegressionResult(
                    window=window,
                    model_type="recommendation_type",
                    r_squared=float(model_ext.rsquared),
                    adj_r_squared=float(model_ext.rsquared_adj),
                    n_obs=int(model_ext.nobs),
                    coefficients=coefs,
                    notes="Heteroskedasticity-robust SE (HC1).",
                )
            )
        except Exception as e:
            results.append(
                RegressionResult(
                    window=window,
                    model_type="recommendation_type",
                    r_squared=0.0,
                    adj_r_squared=0.0,
                    n_obs=len(df),
                    coefficients={},
                    notes=f"Regression failed: {e}",
                )
            )

    return results


def _build_creator_alpha_table(
    event_df: pd.DataFrame, clean_df: pd.DataFrame
) -> list[CreatorAlpha]:
    if clean_df.empty or "event_id" not in clean_df.columns or "creator" not in clean_df.columns:
        return []
    merged = event_df.merge(clean_df[["event_id", "creator"]], on="event_id", how="left")
    merged["ar_1d"] = _safe_float(merged["abnormal_return_1d"])
    merged["ar_5d"] = _safe_float(merged["abnormal_return_5d"])
    merged = merged.dropna(subset=["ar_1d", "creator"])
    if merged.empty:
        return []

    alphas = []
    for creator, group in merged.groupby("creator"):
        n = len(group)
        if n < 3:
            continue
        mean_1d = float(group["ar_1d"].mean()) * PERCENTAGE_MULTIPLIER
        mean_5d = float(group["ar_5d"].mean()) * PERCENTAGE_MULTIPLIER
        median_car = float(group["ar_1d"].median()) * PERCENTAGE_MULTIPLIER
        win_rate = float((group["ar_1d"] > 0).mean()) * PERCENTAGE_MULTIPLIER
        se_1d = float(group["ar_1d"].std(ddof=1)) / np.sqrt(n) * PERCENTAGE_MULTIPLIER
        t_1d = mean_1d / se_1d if se_1d > 0 else 0.0
        p_1d = 2 * (1 - stats_t_cdf(abs(t_1d), n - 1)) if se_1d > 0 else 1.0
        se_5d = float(group["ar_5d"].std(ddof=1)) / np.sqrt(n) * PERCENTAGE_MULTIPLIER
        t_5d = mean_5d / se_5d if se_5d > 0 else 0.0
        p_5d = 2 * (1 - stats_t_cdf(abs(t_5d), n - 1)) if se_5d > 0 else 1.0
        flag = "***" if p_1d < 0.01 or p_5d < 0.01 else "**" if p_1d < 0.05 or p_5d < 0.05 else "*" if p_1d < 0.10 or p_5d < 0.10 else ""
        alphas.append(
            CreatorAlpha(
                creator=creator,
                n=n,
                mean_car_1d=mean_1d,
                mean_car_5d=mean_5d,
                median_car=median_car,
                win_rate_1d=win_rate,
                t_stat_1d=t_1d,
                p_value_1d=p_1d,
                t_stat_5d=t_5d,
                p_value_5d=p_5d,
                significance_flag=flag,
            )
        )
    alphas.sort(key=lambda x: x.mean_car_1d, reverse=True)
    return alphas


def _build_ticker_robustness(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    df = df.copy()
    df["ar_1d"] = _safe_float(df["abnormal_return_1d"])
    df = df.dropna(subset=["ar_1d"])
    for ticker, group in df.groupby("ticker"):
        n = len(group)
        if n < 3:
            continue
        mean_ar = float(group["ar_1d"].mean()) * PERCENTAGE_MULTIPLIER
        se = float(group["ar_1d"].std(ddof=1)) / np.sqrt(n) * PERCENTAGE_MULTIPLIER
        t_stat = mean_ar / se if se > 0 else 0.0
        p_value = 2 * (1 - stats_t_cdf(abs(t_stat), n - 1)) if se > 0 else 1.0
        rows.append(
            {
                "ticker": ticker,
                "n": n,
                "mean_ar_1d_pct": mean_ar,
                "t_stat": t_stat,
                "p_value": p_value,
                "significant_5pct": p_value < 0.05,
            }
        )
    return pd.DataFrame(rows).sort_values("mean_ar_1d_pct", ascending=False)


def stats_t_cdf(t: float, df: int) -> float:
    """Student's t CDF using scipy if available, else simple approximation."""
    try:
        from scipy import stats
        return float(stats.t.cdf(t, df))
    except Exception:
        # Very rough normal approximation for large df
        from math import erf, sqrt
        return 0.5 * (1 + erf(t / sqrt(2)))


def run_statistical_models(
    *,
    event_study_path: Path | None = None,
    clean_events_path: Path | None = None,
    output_dir: Path | None = None,
) -> StatisticalModelResult:
    event_study_path = event_study_path or EVENT_STUDY_RESULTS_PATH
    clean_events_path = clean_events_path or CLEAN_EVENTS_PATH
    output_dir = output_dir or STATISTICAL_MODELS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    notes.append("All returns are abnormal returns relative to SPY benchmark.")
    notes.append("yfinance data is prototype market data, not institutional-grade.")
    notes.append("Classifier labels are rule-generated pseudo-labels; no human ground truth yet.")
    notes.append("Event timing uncertainty: recommendations may not map precisely to event dates.")
    notes.append("Overlapping events are not adjusted for in standard SE calculations.")
    notes.append("No transaction costs, slippage, or shorting constraints modeled.")

    df_events = _read_csv(event_study_path)
    if df_events.empty:
        notes.append("WARNING: No event-study results found. All outputs are empty.")
        _write_empty_outputs(output_dir)
        return StatisticalModelResult(
            model_summary_path=output_dir / MODEL_SUMMARY_PATH.name,
            model_results_path=output_dir / MODEL_RESULTS_PATH.name,
            creator_alpha_path=output_dir / CREATOR_ALPHA_PATH.name,
            ticker_robustness_path=output_dir / TICKER_ROBUSTNESS_PATH.name,
            event_window_robustness_path=output_dir / EVENT_WINDOW_ROBUSTNESS_PATH.name,
            window_stats=[],
            regression_results=[],
            creator_alphas=[],
            notes=notes,
        )

    df_clean = _read_csv(clean_events_path)

    # Window stats
    window_stats = []
    for window, col in WINDOW_COLUMNS.items():
        if col not in df_events.columns:
            notes.append(f"Column {col} not found; skipping {window} stats.")
            continue
        ws = _calc_window_stats(df_events, window, col)
        window_stats.append(ws)

    # Regression results
    regression_results = []
    for window, col in WINDOW_COLUMNS.items():
        if col not in df_events.columns:
            continue
        regression_results.extend(_run_cross_sectional_regression(df_events, window, col))

    # Creator alpha
    creator_alphas = _build_creator_alpha_table(df_events, df_clean)

    # Ticker robustness
    ticker_robustness = _build_ticker_robustness(df_events)
    if not ticker_robustness.empty:
        ticker_robustness.to_csv(output_dir / TICKER_ROBUSTNESS_PATH.name, index=False)
    else:
        _write_empty_csv(output_dir / TICKER_ROBUSTNESS_PATH.name, ["ticker", "n", "mean_ar_1d_pct", "t_stat", "p_value", "significant_5pct"])

    # Event window robustness
    window_robustness = _build_window_robustness(df_events)
    if not window_robustness.empty:
        window_robustness.to_csv(output_dir / EVENT_WINDOW_ROBUSTNESS_PATH.name, index=False)
    else:
        _write_empty_csv(output_dir / EVENT_WINDOW_ROBUSTNESS_PATH.name, ["window", "n", "bootstrap_ci_lower_pct", "bootstrap_ci_upper_pct", "permutation_p_value", "method"])

    # Model results CSV
    model_results_rows = []
    for ws in window_stats:
        model_results_rows.append(
            {
                "model": "descriptive",
                "window": ws.window,
                "n": ws.n,
                "mean_ar_pct": ws.mean_ar,
                "median_ar_pct": ws.median_ar,
                "std_ar_pct": ws.std_ar,
                "t_stat": ws.t_stat,
                "p_value": ws.p_value,
                "win_rate_pct": ws.win_rate,
                "ci_lower_pct": ws.ci_lower,
                "ci_upper_pct": ws.ci_upper,
            }
        )
    for rr in regression_results:
        for var, coefs in rr.coefficients.items():
            model_results_rows.append(
                {
                    "model": rr.model_type,
                    "window": rr.window,
                    "variable": var,
                    "n": rr.n_obs,
                    "coef_pct": coefs["coef"],
                    "std_err_pct": coefs["std_err"],
                    "p_value": coefs["p_value"],
                    "r_squared": rr.r_squared,
                }
            )
    if model_results_rows:
        pd.DataFrame(model_results_rows).to_csv(output_dir / MODEL_RESULTS_PATH.name, index=False)
    else:
        _write_empty_csv(output_dir / MODEL_RESULTS_PATH.name, ["model", "window", "n", "mean_ar_pct", "p_value"])

    # Creator alpha CSV
    if creator_alphas:
        creator_rows = []
        for ca in creator_alphas:
            creator_rows.append(
                {
                    "creator": ca.creator,
                    "n": ca.n,
                    "mean_car_1d_pct": ca.mean_car_1d,
                    "mean_car_5d_pct": ca.mean_car_5d,
                    "median_car_pct": ca.median_car,
                    "win_rate_1d_pct": ca.win_rate_1d,
                    "t_stat_1d": ca.t_stat_1d,
                    "p_value_1d": ca.p_value_1d,
                    "t_stat_5d": ca.t_stat_5d,
                    "p_value_5d": ca.p_value_5d,
                    "significance_flag": ca.significance_flag,
                }
            )
        pd.DataFrame(creator_rows).to_csv(output_dir / CREATOR_ALPHA_PATH.name, index=False)
    else:
        _write_empty_csv(output_dir / CREATOR_ALPHA_PATH.name, ["creator", "n", "mean_car_1d_pct", "p_value_1d"])

    # Summary markdown
    _write_summary_md(
        output_dir / MODEL_SUMMARY_PATH.name,
        window_stats,
        regression_results,
        creator_alphas,
        notes,
    )

    return StatisticalModelResult(
        model_summary_path=output_dir / MODEL_SUMMARY_PATH.name,
        model_results_path=output_dir / MODEL_RESULTS_PATH.name,
        creator_alpha_path=output_dir / CREATOR_ALPHA_PATH.name,
        ticker_robustness_path=output_dir / TICKER_ROBUSTNESS_PATH.name,
        event_window_robustness_path=output_dir / EVENT_WINDOW_ROBUSTNESS_PATH.name,
        window_stats=window_stats,
        regression_results=regression_results,
        creator_alphas=creator_alphas,
        notes=notes,
    )


def _write_empty_csv(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()


def _write_empty_outputs(output_dir: Path) -> None:
    _write_empty_csv(output_dir / MODEL_RESULTS_PATH.name, ["model", "window", "n", "mean_ar_pct", "p_value"])
    _write_empty_csv(output_dir / CREATOR_ALPHA_PATH.name, ["creator", "n", "mean_car_1d_pct", "p_value_1d"])
    _write_empty_csv(output_dir / TICKER_ROBUSTNESS_PATH.name, ["ticker", "n", "mean_ar_1d_pct", "t_stat", "p_value", "significant_5pct"])
    _write_empty_csv(output_dir / EVENT_WINDOW_ROBUSTNESS_PATH.name, ["window", "n", "bootstrap_ci_lower_pct", "bootstrap_ci_upper_pct", "permutation_p_value", "method"])
    summary = output_dir / MODEL_SUMMARY_PATH.name
    summary.write_text("# Statistical Model Summary\n\nNo event-study results available.\n", encoding="utf-8")


def _write_summary_md(
    path: Path,
    window_stats: list[WindowStats],
    regression_results: list[RegressionResult],
    creator_alphas: list[CreatorAlpha],
    notes: list[str],
) -> None:
    lines = ["# Statistical Model Summary", ""]
    lines.append("## Descriptive Event-Window Results")
    lines.append("")
    lines.append("| Window | N | Mean AR% | Median AR% | Std AR% | t-stat | p-value | Win Rate% | 95% CI |")
    lines.append("|--------|---|----------|------------|---------|--------|---------|-----------|--------|")
    for ws in window_stats:
        ci = f"[{ws.ci_lower:.2f}, {ws.ci_upper:.2f}]"
        sig = "***" if ws.p_value < 0.01 else "**" if ws.p_value < 0.05 else "*" if ws.p_value < 0.10 else ""
        lines.append(
            f"| {ws.window} | {ws.n} | {ws.mean_ar:.3f}{sig} | {ws.median_ar:.3f} | "
            f"{ws.std_ar:.3f} | {ws.t_stat:.2f} | {ws.p_value:.4f} | {ws.win_rate:.1f} | {ci} |"
        )
    lines.append("")

    lines.append("## Regression Results")
    lines.append("")
    for rr in regression_results:
        lines.append(f"### {rr.model_type} — {rr.window}")
        lines.append(f"- N = {rr.n_obs}, R² = {rr.r_squared:.4f}, Adj R² = {rr.adj_r_squared:.4f}")
        lines.append("| Variable | Coef (%) | Std Err | p-value |")
        lines.append("|----------|----------|---------|---------|")
        for var, coefs in rr.coefficients.items():
            sig = "***" if coefs["p_value"] < 0.01 else "**" if coefs["p_value"] < 0.05 else "*" if coefs["p_value"] < 0.10 else ""
            lines.append(
                f"| {var} | {coefs['coef']:.4f}{sig} | {coefs['std_err']:.4f} | {coefs['p_value']:.4f} |"
            )
        lines.append(f"- Notes: {rr.notes}")
        lines.append("")

    lines.append("## Creator-Level Alpha (Top 20)")
    lines.append("")
    lines.append("| Creator | N | Mean CAR 1D% | Mean CAR 5D% | Win Rate% | t-stat 1D | p-value 1D | Flag |")
    lines.append("|---------|---|--------------|--------------|-----------|-----------|------------|------|")
    for ca in creator_alphas[:20]:
        lines.append(
            f"| {ca.creator} | {ca.n} | {ca.mean_car_1d:.3f} | {ca.mean_car_5d:.3f} | "
            f"{ca.win_rate_1d:.1f} | {ca.t_stat_1d:.2f} | {ca.p_value_1d:.4f} | {ca.significance_flag} |"
        )
    lines.append("")

    lines.append("## Limitations & Disclaimers")
    lines.append("")
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
