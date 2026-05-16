from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
PORT_DIR = OUT_DIR / "portfolio"
FIG_DIR = OUT_DIR / "figures_data"
PORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = [1, 2, 5, 10, 20]
COSTS = [0, 5, 10, 25, 50, 100]


def event_idx(event: base.EventRecord, market: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], int | None]:
    rows = market.get(event.data_ticker, [])
    if not rows or event.weekday_adjusted_date is None:
        return rows, None
    return rows, base.first_on_or_after(rows, event.weekday_adjusted_date)


def raw_return(event: base.EventRecord, horizon: int, market: dict[str, list[dict[str, Any]]]) -> float | None:
    rows, idx = event_idx(event, market)
    if idx is None:
        return None
    return base.market_return(rows, idx, horizon, "adjusted_close")


def strategy_sign_weight(event: base.EventRecord, strategy: str) -> tuple[int | None, float]:
    top5 = event.ticker in base.TOP5_TICKERS
    buy = event.recommendation_type == "buy"
    if strategy == "long_all_buy":
        return (1, 1.0) if buy else (None, 0.0)
    if strategy == "short_all_sell":
        return (-1, 1.0) if not buy else (None, 0.0)
    if strategy == "long_buy_short_sell":
        return (1 if buy else -1), 1.0
    if strategy == "long_top5_buys_only":
        return (1, 1.0) if buy and top5 else (None, 0.0)
    if strategy == "short_non_top_buys_diagnostic":
        return (-1, 1.0) if buy and not top5 else (None, 0.0)
    if strategy == "equal_weighted_event_direction":
        return (1 if buy else -1), 1.0
    if strategy == "creator_weighted_direction":
        return (1 if buy else -1), 1.0
    if strategy == "quality_weighted_direction":
        score = event.actionability_score if event.actionability_score is not None else 50
        return (1 if buy else -1), max(score, 1) / 100.0
    if strategy == "duplicate_collapsed_direction":
        return (1 if buy else -1), 1.0
    if strategy == "low_lookahead_direction":
        return (1 if buy else -1), 1.0 if event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS else 0.0
    return None, 0.0


def max_drawdown(returns: list[float]) -> float:
    value = 1.0
    peak = 1.0
    worst = 0.0
    for ret in returns:
        value *= 1.0 + ret
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def summarize_trades(
    strategy: str,
    horizon: int,
    cost_bps: int,
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    returns = [float(t["net_return"]) for t in trades]
    gross = [float(t["gross_signed_return"]) for t in trades]
    n = len(returns)
    if not returns:
        return {
            "strategy": strategy,
            "holding_days": horizon,
            "cost_bps": cost_bps,
            "trade_count": 0,
            "average_trade_return": "",
            "cumulative_return": "",
            "annualized_return": "",
            "volatility": "",
            "sharpe": "",
            "max_drawdown": "",
            "hit_rate": "",
            "turnover": "",
            "trades_per_year": "",
            "breakeven_transaction_cost_bps": "",
            "status": "no_trades",
        }
    cumulative = math.prod(1.0 + ret for ret in returns) - 1.0
    days = max((max(t["event_date"] for t in trades) - min(t["event_date"] for t in trades)).days, 1)
    trades_per_year = n / (days / 365.25)
    avg = sum(returns) / n
    std = pd.Series(returns).std(ddof=1) if n > 1 else 0.0
    volatility = std * math.sqrt(trades_per_year) if std else 0.0
    annualized = (1.0 + cumulative) ** (365.25 / days) - 1.0 if cumulative > -1 else -1.0
    sharpe = annualized / volatility if volatility else ""
    gross_avg = sum(gross) / len(gross)
    breakeven = max(gross_avg * 10000.0 / 2.0, 0.0)
    return {
        "strategy": strategy,
        "holding_days": horizon,
        "cost_bps": cost_bps,
        "trade_count": n,
        "average_trade_return": base.fmt(avg),
        "cumulative_return": base.fmt(cumulative),
        "annualized_return": base.fmt(annualized),
        "volatility": base.fmt(volatility),
        "sharpe": base.fmt(sharpe, 3) if sharpe != "" else "",
        "max_drawdown": base.fmt(max_drawdown(returns)),
        "hit_rate": base.fmt(sum(ret > 0 for ret in returns) / n),
        "turnover": base.fmt(n * 2),
        "trades_per_year": base.fmt(trades_per_year, 2),
        "breakeven_transaction_cost_bps": base.fmt(breakeven, 2),
        "status": "diagnostic_event_trade_sequence",
    }


def main() -> int:
    market = base.load_market_data()
    events = base.fetch_events(market)
    first_ids = {event.event_id for event in base.first_per_cluster(events)}
    creator_counts = pd.Series([event.creator for event in events]).value_counts().to_dict()
    strategies = [
        "long_all_buy",
        "short_all_sell",
        "long_buy_short_sell",
        "long_top5_buys_only",
        "short_non_top_buys_diagnostic",
        "equal_weighted_event_direction",
        "creator_weighted_direction",
        "quality_weighted_direction",
        "duplicate_collapsed_direction",
        "low_lookahead_direction",
    ]
    summary_rows = []
    drawdown_rows = []
    curve_rows = []
    attribution_rows = []
    for strategy in strategies:
        for horizon in HORIZONS:
            raw_by_event = {event.event_id: raw_return(event, horizon, market) for event in events}
            for cost in COSTS:
                trades = []
                for event in events:
                    if strategy == "duplicate_collapsed_direction" and event.event_id not in first_ids:
                        continue
                    sign, weight = strategy_sign_weight(event, strategy)
                    if sign is None or weight == 0:
                        continue
                    if strategy == "creator_weighted_direction":
                        weight = 1.0 / max(creator_counts.get(event.creator, 1), 1)
                    ret = raw_by_event[event.event_id]
                    if ret is None or event.event_date is None:
                        continue
                    gross = sign * ret * weight
                    net = gross - (2.0 * cost / 10000.0)
                    trades.append(
                        {
                            "event_id": event.event_id,
                            "event_date": event.event_date,
                            "ticker": event.ticker,
                            "top5": event.ticker in base.TOP5_TICKERS,
                            "gross_signed_return": gross,
                            "net_return": net,
                        }
                    )
                trades.sort(key=lambda row: (row["event_date"], row["event_id"]))
                summary = summarize_trades(strategy, horizon, cost, trades)
                summary_rows.append(summary)
                if trades:
                    top5_sum = sum(t["net_return"] for t in trades if t["top5"])
                    total_sum = sum(t["net_return"] for t in trades)
                    attribution_rows.append(
                        {
                            "strategy": strategy,
                            "holding_days": horizon,
                            "cost_bps": cost,
                            "trade_count": len(trades),
                            "top5_net_return_sum": base.fmt(top5_sum),
                            "non_top_net_return_sum": base.fmt(total_sum - top5_sum),
                            "top5_contribution_share": base.fmt(
                                None if total_sum == 0 else top5_sum / total_sum
                            ),
                        }
                    )
                if horizon == 5 and cost in {0, 25} and trades:
                    value = 1.0
                    peak = 1.0
                    for idx, trade in enumerate(trades, start=1):
                        value *= 1.0 + trade["net_return"]
                        peak = max(peak, value)
                        curve_rows.append(
                            {
                                "strategy": strategy,
                                "cost_bps": cost,
                                "step": idx,
                                "event_date": trade["event_date"].isoformat(),
                                "equity": base.fmt(value),
                            }
                        )
                        drawdown_rows.append(
                            {
                                "strategy": strategy,
                                "cost_bps": cost,
                                "step": idx,
                                "event_date": trade["event_date"].isoformat(),
                                "drawdown": base.fmt(value / peak - 1.0),
                            }
                        )
    columns = list(summary_rows[0])
    base.write_csv(PORT_DIR / "01_v2_strategy_return_table.csv", summary_rows, columns)
    base.write_md(
        PORT_DIR / "01_v2_strategy_return_table.md",
        "# V2 Strategy Return Table\n\n" + base.markdown_table(summary_rows, columns),
    )
    cost_rows = [
        row
        for row in summary_rows
        if row["holding_days"] == 5
        and row["strategy"] in {"long_all_buy", "long_top5_buys_only", "short_non_top_buys_diagnostic"}
    ]
    base.write_csv(PORT_DIR / "02_v2_transaction_cost_sensitivity.csv", cost_rows, columns)
    base.write_md(
        PORT_DIR / "02_v2_transaction_cost_sensitivity.md",
        "# V2 Transaction Cost Sensitivity\n\n" + base.markdown_table(cost_rows, columns),
    )
    base.write_csv(PORT_DIR / "03_v2_portfolio_drawdowns.csv", drawdown_rows, list(drawdown_rows[0]))
    base.write_md(
        PORT_DIR / "03_v2_portfolio_drawdowns.md",
        "# V2 Drawdown Curves\n\nFull curve data are in the CSV.",
    )
    turnover_rows = [
        {
            "strategy": row["strategy"],
            "holding_days": row["holding_days"],
            "cost_bps": row["cost_bps"],
            "trade_count": row["trade_count"],
            "turnover": row["turnover"],
            "trades_per_year": row["trades_per_year"],
            "breakeven_transaction_cost_bps": row["breakeven_transaction_cost_bps"],
        }
        for row in summary_rows
    ]
    base.write_csv(PORT_DIR / "04_v2_turnover_and_capacity.csv", turnover_rows, list(turnover_rows[0]))
    base.write_md(
        PORT_DIR / "04_v2_turnover_and_capacity.md",
        "# V2 Turnover and Capacity\n\n" + base.markdown_table(turnover_rows[:40], list(turnover_rows[0])),
    )
    base.write_csv(PORT_DIR / "05_v2_concentration_attribution.csv", attribution_rows, list(attribution_rows[0]))
    base.write_md(
        PORT_DIR / "05_v2_concentration_attribution.md",
        "# V2 Concentration Attribution\n\n"
        + base.markdown_table(attribution_rows[:40], list(attribution_rows[0])),
    )
    best = max(
        (row for row in summary_rows if row["cost_bps"] == 25 and row["holding_days"] == 5 and row["average_trade_return"] != ""),
        key=lambda row: float(row["average_trade_return"]),
    )
    worst = min(
        (row for row in summary_rows if row["cost_bps"] == 25 and row["holding_days"] == 5 and row["average_trade_return"] != ""),
        key=lambda row: float(row["average_trade_return"]),
    )
    base.write_md(
        PORT_DIR / "06_v2_portfolio_interpretation.md",
        f"""# V2 Portfolio Interpretation

At 25 bps per side, the best 5-day diagnostic strategy is `{best['strategy']}`
with average trade return `{best['average_trade_return']}` and Sharpe
`{best['sharpe']}`. The worst is `{worst['strategy']}` with average trade return
`{worst['average_trade_return']}`.

These are event-trade diagnostics, not executable proof of tradable alpha.
Capacity, slippage, intraday timing, borrow availability, and realistic order
placement are not validated. If strategies die after costs or depend on top-5
tickers, the paper should say so directly.
""",
    )
    base.write_csv(FIG_DIR / "v2_portfolio_equity_curves.csv", curve_rows, list(curve_rows[0]))
    base.write_csv(FIG_DIR / "v2_transaction_cost_sensitivity.csv", cost_rows, columns)
    base.write_csv(FIG_DIR / "v2_drawdown_curves.csv", drawdown_rows, list(drawdown_rows[0]))
    print("V2 portfolio analysis complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
