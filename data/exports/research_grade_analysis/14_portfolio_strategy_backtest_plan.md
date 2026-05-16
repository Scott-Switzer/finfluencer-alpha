# Portfolio Strategy Backtest Plan

## Status

This plan ships with a *headline* in-sample provisional backtest using
SPY-adjusted abnormal returns over the 5-trading-day post-event window. These
are *event-level* returns aggregated equal-weight; a calendar-time portfolio
backtest (proper overlapping-event handling, daily P&L, turnover and cost
modeling) is scheduled for Bloomberg-day. The point estimates below are
provisional, not investable, and inherit every caveat from the yfinance
provisional baseline.

## Provisional Headline Summary (AR_0_5, equal-weight, no costs)

| Strategy | n | mean | median | hit rate | event Sharpe | max drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| Long-buy (1,209 buys) | 1193 | 0.0054 | -0.0003 | 49.79% | 0.081 | -0.34% |
| Short-sell (345 sells, return sign flipped) | 343 | 0.0041 | -0.0004 | 49.85% | 0.053 | -0.83% |
| Long-buy + short-sell | 1536 | 0.0051 | -0.0003 | 49.80% | 0.074 | -0.21% |
| High-quality (tier A/B) long-buy | 734 | 0.0041 | -0.0006 | 49.46% | 0.066 | -0.39% |

These numbers aggregate close-to-close event-study returns as if each event
were a self-contained equal-weight trade proxy. They do not use executable open
or intraday prices and are not adjusted for overlapping holdings, capital
usage, transaction costs, or slippage. `max drawdown` is reported on an
equal-capital additive pseudo-equity stream (each event gets `1/n` of capital,
contributions are added rather than compounded) ordered by
`calendar_event_date`; that pseudo-equity is not a calendar-time NAV and should
be replaced with the calendar-time backtest in section "Calendar-Time Portfolio
Construction" below at Bloomberg-day.

## Full Backtest Specification

### Strategies

1. **Long-buy**: open long position on `effective_trading_event_date + 1`
   close (next-day execution to avoid same-day lookahead), close on
   `effective_trading_event_date + 5` close.
2. **Short-sell**: same horizon, short position on sell-classified events.
3. **Long-buy + short-sell**: combine 1 and 2; equal-weight per event.
4. **High-quality only**: filter to tier A/B events.
5. **Duplicate-collapsed**: one event per `(creator, ticker, weekday-adjusted
   date)` cluster.
6. **Momentum-neutral**: residualize event AR on pre-event AR_-20_-1 before
   accumulating; report the residual portfolio.
7. **News-confounded-excluded**: drop events with
   `news_confounded_event_flag = True` after Bloomberg-day rerun.

### Weighting Schemes

- Equal-weight per event (baseline).
- Volatility-scaled (target 1% per-event vol using trailing 60-day stock
  volatility).
- Market-neutral (long position - SPY short with matching dollar exposure).

### Trading Costs / Slippage

- Per-side commission: 5 bps (conservative for retail; 1 bp institutional).
- Slippage: 10 bps for high-cap (top 10 tickers by market cap), 25 bps for
  small-cap.
- Borrow cost for shorts: 0 bps for top-cap, 200 bps annualized otherwise.

### Metrics To Report

- Mean and median per-event return.
- Hit rate.
- Sharpe (per-event and annualized assuming 252/horizon).
- Sortino (downside semi-deviation in denominator).
- Maximum drawdown of cumulative equal-weight stream.
- Turnover and average days-in-trade.
- Cost-adjusted return (gross minus costs).
- CAPM, FF3, Carhart, FF5 alpha against the daily portfolio return series
  (after Bloomberg-day French factor fetch).

## Calendar-Time Portfolio Construction

For each trading day t, compute the daily portfolio return as the equal-weight
average across all events whose holding period contains t. Aggregate this
daily return series and run standard factor regressions on it. This avoids
the n inflation problem of treating overlapping holdings as independent.

## Pseudo-code

```python
import pandas as pd

def calendar_portfolio(events_df: pd.DataFrame, prices_df: pd.DataFrame,
                       entry_offset: int = 1, exit_offset: int = 5) -> pd.Series:
    daily = []
    for d in pd.bdate_range(prices_df.index.min(), prices_df.index.max()):
        active = events_df[(events_df["entry_date"] <= d) & (d <= events_df["exit_date"])]
        if active.empty:
            daily.append((d, 0.0))
            continue
        per_event = []
        for _, ev in active.iterrows():
            prev_px = prices_df.loc[d - pd.Timedelta(days=1), ev["ticker"]]
            this_px = prices_df.loc[d, ev["ticker"]]
            ret = (this_px / prev_px) - 1.0
            if ev["side"] == "short":
                ret = -ret
            per_event.append(ret)
        daily.append((d, sum(per_event) / len(per_event)))
    return pd.Series(dict(daily)).sort_index()
```

## Acceptance Criteria

- Cost-adjusted Sharpe of the headline strategy positive.
- High-quality cut delivers higher Sharpe than the headline, otherwise the
  quality score is not informative.
- Long-short Sharpe exceeds long-only Sharpe (sells contain information).
- Portfolio survives news-confounded-exclusion with stable factor-adjusted
  return estimates and no mechanically large drawdown.
