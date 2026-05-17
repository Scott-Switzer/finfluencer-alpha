"""Calendar-time daily portfolio returns vs Kenneth French factors with HAC (Newey-West) SEs."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_factor_adjusted_alpha as factor_base  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "calendar_time_factor_regressions"
HOLDING_DAYS = (5, 21, 63)
CAP_WEIGHT_MAX = 0.10
MODELS: dict[str, list[str]] = {
    "CAPM": ["Mkt-RF"],
    "FF3": ["Mkt-RF", "SMB", "HML"],
    "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "Carhart": ["Mkt-RF", "SMB", "HML", "MOM"],
    "FF5_MOM": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
}

STRATEGIES = [
    "long_all_buy",
    "short_non_top_buys_diagnostic",
    "long_top5_buys_only",
    "equal_weighted_event_direction",
    "duplicate_collapsed_direction",
    "low_lookahead_direction",
]


def market_daily_returns(market: dict[str, list[dict[str, Any]]], ticker: str) -> dict[date, float]:
    rows = market.get(ticker, [])
    out: dict[date, float] = {}
    for idx in range(1, len(rows)):
        p0 = rows[idx - 1]["adjusted_close"]
        p1 = rows[idx]["adjusted_close"]
        if p0:
            out[rows[idx]["date"]] = (p1 / p0) - 1.0
    return out


def next_entry_index(rows: list[dict[str, Any]], effective_date: date | None) -> int | None:
    if effective_date is None:
        return None
    entry_base = base.first_on_or_after(rows, effective_date)
    if entry_base is None:
        return None
    idx = entry_base + 1
    return idx if 0 <= idx < len(rows) else None


def strategy_params(event: base.EventRecord, strategy: str) -> tuple[int | None, float]:
    top5 = event.ticker in base.TOP5_TICKERS
    buy = event.recommendation_type == "buy"
    if strategy == "long_all_buy":
        return (1, 1.0) if buy else (None, 0.0)
    if strategy == "short_non_top_buys_diagnostic":
        return (-1, 1.0) if buy and not top5 else (None, 0.0)
    if strategy == "long_top5_buys_only":
        return (1, 1.0) if buy and top5 else (None, 0.0)
    if strategy == "equal_weighted_event_direction":
        return (1 if buy else -1), 1.0
    if strategy == "duplicate_collapsed_direction":
        return (1 if buy else -1), 1.0
    if strategy == "low_lookahead_direction":
        if event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS:
            return (1 if buy else -1), 1.0
        return None, 0.0
    return None, 0.0


def build_positions(
    events: list[base.EventRecord],
    market: dict[str, list[dict[str, Any]]],
    strategy: str,
    holding: int,
    first_ids: set[int],
) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for event in events:
        if strategy == "duplicate_collapsed_direction" and event.event_id not in first_ids:
            continue
        side, w0 = strategy_params(event, strategy)
        if side is None or w0 == 0:
            continue
        rows = market.get(event.data_ticker, [])
        idx = next_entry_index(rows, event.weekday_adjusted_date)
        if idx is None or idx + holding >= len(rows):
            continue
        entry_date = rows[idx]["date"]
        exit_date = rows[idx + holding]["date"]
        positions.append(
            {
                "ticker": event.data_ticker,
                "side": side,
                "entry": entry_date,
                "exit": exit_date,
            }
        )
    return positions


def cap_weights(weights: list[float], cap: float) -> list[float]:
    if not weights:
        return weights
    w = np.array(weights, dtype=float)
    for _ in range(len(w) * 2):
        over = w > cap
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        free = ~over
        if not free.any() or excess <= 0:
            break
        w[free] += excess / free.sum()
    s = float(w.sum())
    return (w / s).tolist() if s > 0 else weights


def daily_portfolio_series(
    positions: list[dict[str, Any]],
    market: dict[str, list[dict[str, Any]]],
    trading_dates: list[date],
    weight_mode: str,
) -> dict[date, float]:
    ticker_returns = {t: market_daily_returns(market, t) for t in {p["ticker"] for p in positions}}
    out: dict[date, float] = {}
    for d in trading_dates:
        active = [p for p in positions if p["entry"] < d <= p["exit"]]
        if not active:
            out[d] = 0.0
            continue
        rets = []
        for p in active:
            r = ticker_returns.get(p["ticker"], {}).get(d)
            if r is None:
                continue
            rets.append(float(p["side"]) * float(r))
        if not rets:
            out[d] = 0.0
            continue
        if weight_mode == "equal":
            out[d] = float(np.mean(rets))
        else:
            w = cap_weights([1.0] * len(rets), CAP_WEIGHT_MAX)
            out[d] = float(np.dot(np.array(rets), np.array(w)))
    return out


def calendar_dates_for_positions(
    positions: list[dict[str, Any]], market: dict[str, list[dict[str, Any]]]
) -> list[date]:
    if not positions:
        return []
    tickers = {p["ticker"] for p in positions}.union({"SPY"})
    all_d: set[date] = set()
    for t in tickers:
        for row in market.get(t, []):
            all_d.add(row["date"])
    tmin = min(p["entry"] for p in positions)
    tmax = max(p["exit"] for p in positions)
    return sorted(d for d in all_d if tmin <= d <= tmax)


def hac_alpha_table(
    y: pd.Series, factors: pd.DataFrame, model_cols: list[str]
) -> dict[str, Any] | None:
    df = pd.concat([y.rename("y"), factors[model_cols + ["RF"]]], axis=1, join="inner").dropna()
    if len(df) < max(60, len(model_cols) * 3):
        return None
    y_exc = df["y"] - df["RF"]
    X = sm.add_constant(df[model_cols])
    model = sm.OLS(y_exc, X)
    try:
        res = model.fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    except Exception:
        return None
    alpha = float(res.params.get("const", float("nan")))
    se = float(res.bse.get("const", float("nan")))
    tval = float(res.tvalues.get("const", float("nan")))
    pval = float(res.pvalues.get("const", float("nan")))
    ann = ""
    if alpha > -1:
        ann = utils.fmt(((1.0 + alpha) ** 252) - 1.0)
    return {
        "n_days": int(res.nobs),
        "alpha_daily": utils.fmt(alpha),
        "alpha_ann_approx": ann,
        "alpha_hac_se": utils.fmt(se),
        "alpha_t_hac": utils.fmt(tval, 4),
        "alpha_p_value": utils.fmt(pval, 6),
        "r_squared": utils.fmt(float(res.rsquared)),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    factors, status_rows = factor_base.load_factors()
    utils.table_pair(OUT_DIR / "00_factor_download_status", status_rows, "Factor Download Status")
    if factors.empty:
        utils.write_md(
            OUT_DIR / "README.md",
            "Calendar-Time Factor Regressions",
            "French factors unavailable; skipped.",
        )
        return 0

    market = base.load_market_data()
    events = base.fetch_events(market)
    first_ids = {e.event_id for e in base.first_per_cluster(events)}

    regression_rows: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        for holding in HOLDING_DAYS:
            positions = build_positions(events, market, strategy, holding, first_ids)
            if not positions:
                continue
            trading_dates = calendar_dates_for_positions(positions, market)
            if not trading_dates:
                continue
            for wmode, wlabel in [("equal", "ew"), ("capped", "capped")]:
                series = daily_portfolio_series(positions, market, trading_dates, wmode)
                y = pd.Series({d: series[d] for d in trading_dates}).sort_index()
                y = y.loc[y.index.isin(factors.index)]
                for model_name, cols in MODELS.items():
                    if any(c not in factors.columns for c in cols + ["RF"]):
                        continue
                    reg = hac_alpha_table(y, factors, cols)
                    if reg is None:
                        continue
                    regression_rows.append(
                        {
                            "strategy": strategy,
                            "holding_trading_days": holding,
                            "weighting": wlabel,
                            "model": model_name,
                            **reg,
                        }
                    )

    cols = (
        list(regression_rows[0].keys())
        if regression_rows
        else [
            "strategy",
            "holding_trading_days",
            "weighting",
            "model",
            "n_days",
            "alpha_daily",
        ]
    )
    utils.write_csv(OUT_DIR / "01_calendar_time_hac_regressions.csv", regression_rows, cols)
    utils.write_md(
        OUT_DIR / "01_calendar_time_hac_regressions.md",
        "Calendar-Time HAC Regressions",
        utils.md_table(regression_rows) if regression_rows else "No regression rows computed.",
    )
    utils.write_md(
        OUT_DIR / "02_methodology.md",
        "Calendar-Time Methodology",
        "Daily portfolio returns equal-weight or capped (10% max sleeve, renormalized) across open event "
        "positions; next-day entry after effective trading date; holding horizon in trading days. "
        "Dependent variable: portfolio excess return vs RF. "
        "Factors from Kenneth French daily files. OLS with Newey-West HAC covariance (maxlags=5).",
    )
    print(f"Calendar-time factor regressions: {len(regression_rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
