from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_long_horizon_returns as lh  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
REGIME_DIR = OUT_DIR / "regime"
REGIME_DIR.mkdir(parents=True, exist_ok=True)
HORIZONS = ["5D", "21D", "63D", "126D", "252D"]


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:100], columns)
    )


def t(values: pd.Series) -> dict[str, Any]:
    stats = base.t_test([float(v) for v in values.dropna()])
    return {
        "n": stats["n"],
        "mean_spy_bhar": lh.format_float(stats["mean"]),
        "t_stat": lh.format_float(stats["t"], 3),
        "p_value": lh.format_float(stats["p"], 6),
        "win_rate": lh.format_float(stats["win_rate"], 4),
    }


def load_panel() -> pd.DataFrame:
    df = pd.read_csv(OUT_DIR / "long_horizon" / "01_v2_long_horizon_event_returns.csv")
    forward = df[
        (df["window_type"] == "forward")
        & (df["horizon"].isin(HORIZONS))
        & (df["status"] == "computed")
    ].copy()
    pre = df[(df["window_type"] == "pre") & (df["horizon"] == "pre_-21_-1")][
        ["event_id", "spy_bhar", "realized_volatility"]
    ].rename(columns={"spy_bhar": "pre21_spy_bhar", "realized_volatility": "pre21_volatility"})
    forward = forward.merge(pre, on="event_id", how="left")
    forward["spy_bhar"] = pd.to_numeric(forward["spy_bhar"], errors="coerce")
    forward["pre21_spy_bhar"] = pd.to_numeric(forward["pre21_spy_bhar"], errors="coerce")
    forward["pre21_volatility"] = pd.to_numeric(forward["pre21_volatility"], errors="coerce")
    forward["event_month"] = (
        pd.to_datetime(forward["event_date"], errors="coerce").dt.to_period("M").astype(str)
    )
    forward["pre_momentum_bucket"] = pd.qcut(
        forward["pre21_spy_bhar"], 4, labels=["q1_low", "q2", "q3", "q4_high"], duplicates="drop"
    )
    forward["pre_volatility_bucket"] = pd.qcut(
        forward["pre21_volatility"], 4, labels=["q1_low", "q2", "q3", "q4_high"], duplicates="drop"
    )
    forward["top5_bool"] = forward["top5_flag"].astype(str).eq("True")
    forward["sec_confounded_bool"] = forward["sec_confounded_flag"].astype(str).eq("True")
    forward["low_lookahead_bool"] = forward["low_lookahead_flag"].astype(str).eq("True")
    forward["duplicate_bool"] = ~forward["duplicate_collapsed_flag"].astype(str).eq("True")
    forward["buy_bool"] = forward["recommendation_type"].eq("buy")
    return forward


def add_market_regime(panel: pd.DataFrame) -> pd.DataFrame:
    frames = lh.market_frames()
    regime_map = {}
    for ticker, frame in frames.items():
        bench = frame["benchmark_adjusted_close"]
        trend = bench > bench.rolling(200, min_periods=80).mean()
        vol = frame["daily_spy_return"].rolling(21, min_periods=10).std()
        for idx, row in frame.iterrows():
            regime_map[(ticker, row["date"].isoformat())] = {
                "spy_200d_trend": "bull_proxy"
                if bool(trend.iloc[idx])
                else "bear_or_unformed_proxy",
                "spy_volatility_21d": vol.iloc[idx],
            }
    panel["spy_200d_trend"] = [
        regime_map.get((row["data_ticker"], row["effective_trading_event_date"]), {}).get(
            "spy_200d_trend", "unknown"
        )
        for row in panel.to_dict("records")
    ]
    panel["spy_volatility_21d"] = [
        regime_map.get((row["data_ticker"], row["effective_trading_event_date"]), {}).get(
            "spy_volatility_21d", math.nan
        )
        for row in panel.to_dict("records")
    ]
    panel["spy_vol_bucket"] = pd.qcut(
        panel["spy_volatility_21d"], 4, labels=["q1_low", "q2", "q3", "q4_high"], duplicates="drop"
    )
    return panel


def bucket_summary(panel: pd.DataFrame, bucket_col: str) -> list[dict[str, Any]]:
    rows = []
    for (horizon, bucket), group in panel.groupby(["horizon", bucket_col], dropna=False):
        rows.append(
            {
                "horizon": horizon,
                "bucket_variable": bucket_col,
                "bucket": str(bucket),
                **t(group["spy_bhar"]),
            }
        )
    return rows


def regression_rows(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for horizon in HORIZONS:
        df = panel[panel["horizon"].eq(horizon)].dropna(subset=["spy_bhar"]).copy()
        if len(df) < 50:
            continue
        base_cols = pd.DataFrame(
            {
                "intercept": 1.0,
                "top5": df["top5_bool"].astype(float),
                "pre_momentum": df["pre21_spy_bhar"].fillna(0.0),
                "sec_confounded": df["sec_confounded_bool"].astype(float),
                "low_lookahead": df["low_lookahead_bool"].astype(float),
                "duplicate": df["duplicate_bool"].astype(float),
                "buy": df["buy_bool"].astype(float),
                "top5_x_pre_momentum": df["top5_bool"].astype(float)
                * df["pre21_spy_bhar"].fillna(0.0),
            }
        )
        ticker_fe = pd.get_dummies(df["ticker"], prefix="ticker", drop_first=True, dtype=float)
        month_fe = pd.get_dummies(df["event_month"], prefix="month", drop_first=True, dtype=float)
        x = pd.concat([base_cols, ticker_fe, month_fe], axis=1)
        y = df["spy_bhar"].astype(float).to_numpy()
        try:
            beta = np.linalg.lstsq(x.to_numpy(), y, rcond=None)[0]
        except np.linalg.LinAlgError:
            continue
        residuals = y - x.to_numpy().dot(beta)
        dof = max(1, len(y) - x.shape[1])
        sigma2 = float((residuals @ residuals) / dof)
        try:
            cov = sigma2 * np.linalg.pinv(x.to_numpy().T @ x.to_numpy())
            se = np.sqrt(np.diag(cov))
        except np.linalg.LinAlgError:
            se = np.full(len(beta), np.nan)
        for name in [
            "top5",
            "pre_momentum",
            "sec_confounded",
            "low_lookahead",
            "duplicate",
            "buy",
            "top5_x_pre_momentum",
        ]:
            idx = list(x.columns).index(name)
            t_stat = beta[idx] / se[idx] if se[idx] and not np.isnan(se[idx]) else math.nan
            p_value = (
                2 * (1 - base.normal_cdf(abs(float(t_stat))))
                if not math.isnan(t_stat)
                else math.nan
            )
            rows.append(
                {
                    "horizon": horizon,
                    "coefficient": name,
                    "estimate": lh.format_float(beta[idx]),
                    "standard_error": lh.format_float(se[idx]),
                    "t_stat": lh.format_float(t_stat, 3),
                    "p_value": lh.format_float(p_value, 6),
                    "fixed_effects": "ticker and event-month",
                    "notes": "OLS diagnostic, not causal identification",
                }
            )
    return rows


def main() -> int:
    panel = add_market_regime(load_panel())
    regime_rows = bucket_summary(panel, "spy_200d_trend") + bucket_summary(panel, "spy_vol_bucket")
    momentum_rows = bucket_summary(panel, "pre_momentum_bucket") + bucket_summary(
        panel, "pre_volatility_bucket"
    )
    regressions = regression_rows(panel)
    write_table(REGIME_DIR / "01_regime_bucket_summary", regime_rows, "Regime Bucket Summary")
    write_table(REGIME_DIR / "02_momentum_bucket_summary", momentum_rows, "Momentum Bucket Summary")
    write_table(REGIME_DIR / "03_interaction_regressions", regressions, "Interaction Regressions")
    text = """# Regime and Momentum Interpretation

The regime layer buckets events by SPY trend, SPY volatility, ticker pre-event
momentum, and ticker pre-event volatility. The interaction regressions include
ticker and event-month fixed effects, so the top5 coefficient is interpreted as
within-period residual heterogeneity, not causal impact.

Missing VIX data is documented by omission; no paid source was used.
"""
    base.write_md(REGIME_DIR / "04_regime_interpretation.md", text)
    print(f"V2 market regime and momentum complete: regression_rows={len(regressions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
