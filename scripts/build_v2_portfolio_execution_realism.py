from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "portfolio_execution_realism"
HORIZONS = [5, 21, 63, 126, 252]
COSTS = [0, 5, 10, 25, 50, 100]
DELAYS = ["next_close", "one_day_delay"]


def strategy_mask(frame: pd.DataFrame, strategy: str) -> tuple[pd.Series, int]:
    top5 = frame["top5_flag"].astype(str).str.lower().eq("true")
    buy = frame["recommendation_type"].eq("buy")
    sell = frame["recommendation_type"].eq("sell")
    if strategy == "long_all_buys":
        return buy, 1
    if strategy == "long_top5_buys":
        return buy & top5, 1
    if strategy == "avoid_non_top_buys":
        return buy & ~top5, 0
    if strategy == "short_non_top_buys_diagnostic":
        return buy & ~top5, -1
    if strategy == "long_buy_short_sell":
        return buy | sell, 1
    return pd.Series(False, index=frame.index), 0


def max_drawdown(returns: list[float]) -> float:
    value = 1.0
    peak = 1.0
    worst = 0.0
    for ret in returns:
        value *= 1.0 + ret
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def summarize(strategy: str, horizon: int, cost: int, delay: str, trades: pd.DataFrame, sign: int) -> dict[str, object]:
    if trades.empty or sign == 0:
        return {
            "strategy": strategy,
            "holding_days": horizon,
            "cost_bps": cost,
            "signal_timing": delay,
            "trade_count": len(trades),
            "status": "avoidance_not_trade" if sign == 0 else "no_trades",
        }
    gross = trades["raw_return"].astype(float) * sign
    if strategy == "long_buy_short_sell":
        side = trades["recommendation_type"].map({"buy": 1, "sell": -1}).fillna(0)
        gross = trades["raw_return"].astype(float) * side
    net = gross - (2 * cost / 10000.0)
    if delay == "one_day_delay":
        net = net - 0.0005
    n = len(net)
    avg = float(net.mean())
    med = float(net.median())
    std = float(net.std(ddof=1)) if n > 1 else 0.0
    years = max((pd.to_datetime(trades["event_date"]).max() - pd.to_datetime(trades["event_date"]).min()).days / 365.25, 0.1)
    annualized = (1.0 + avg) ** (252 / max(horizon, 1)) - 1.0 if avg > -1 else -1.0
    vol = std * math.sqrt(252 / max(horizon, 1)) if std else 0.0
    return {
        "strategy": strategy,
        "holding_days": horizon,
        "cost_bps": cost,
        "signal_timing": delay,
        "trade_count": n,
        "average_trade_return": utils.fmt(avg),
        "median_trade_return": utils.fmt(med),
        "annualized_return_proxy": utils.fmt(annualized),
        "annualized_volatility_proxy": utils.fmt(vol),
        "sharpe_proxy": utils.fmt(annualized / vol, 3) if vol else "",
        "max_drawdown_sequence": utils.fmt(max_drawdown(net.tolist())),
        "hit_rate": utils.fmt(float((net > 0).mean())),
        "top5_event_share": utils.fmt(float(trades["top5_flag"].astype(str).str.lower().eq("true").mean())),
        "ticker_concentration_top_share": utils.fmt(float(trades["ticker"].value_counts(normalize=True).iloc[0])) if n else "",
        "years_spanned": utils.fmt(years, 2),
        "status": "diagnostic_not_tradability_proof",
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = utils.forward_panel([f"{h}D" for h in HORIZONS])
    rows = []
    for horizon in HORIZONS:
        hframe = panel[panel["horizon"].eq(f"{horizon}D") & panel["status"].eq("computed")].copy()
        for strategy in [
            "long_all_buys",
            "long_top5_buys",
            "avoid_non_top_buys",
            "short_non_top_buys_diagnostic",
            "long_buy_short_sell",
        ]:
            mask, sign = strategy_mask(hframe, strategy)
            trades = hframe[mask].copy()
            for cost in COSTS:
                for delay in DELAYS:
                    rows.append(summarize(strategy, horizon, cost, delay, trades, sign))
    utils.table_pair(OUT_DIR / "01_execution_realism_strategy_summary", rows, "Execution Realism Strategy Summary")
    utils.table_pair(OUT_DIR / "02_cost_and_delay_grid", rows, "Cost And Delay Grid")
    concentration = []
    for horizon in HORIZONS:
        hframe = panel[panel["horizon"].eq(f"{horizon}D")]
        for ticker, group in hframe.groupby("ticker"):
            concentration.append({"horizon": f"{horizon}D", "ticker": ticker, "event_share": utils.fmt(len(group) / len(hframe))})
    utils.write_csv(OUT_DIR / "03_exposure_concentration.csv", concentration)
    drawdowns = [row for row in rows if row.get("max_drawdown_sequence", "") != ""]
    utils.write_csv(OUT_DIR / "04_drawdown_diagnostics.csv", drawdowns)
    utils.write_md(
        OUT_DIR / "05_portfolio_execution_realism_interpretation.md",
        "Portfolio Execution Realism Interpretation",
        "Portfolio outputs are diagnostic. A strategy is not tradable unless it survives delay, cost, drawdown, concentration, overlap, and shorting constraints. Avoiding non-top recommendations is distinct from shorting them.",
    )
    print("Portfolio execution realism complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
