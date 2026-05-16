# V2 Portfolio Interpretation

At 25 bps per side, the best 5-day diagnostic strategy is `long_top5_buys_only`
with average trade return `0.001836` and Sharpe
`-0.160`. The worst is `short_all_sell` with average trade return
`-0.007125`.

These are event-trade diagnostics, not executable proof of tradable alpha.
Capacity, slippage, intraday timing, borrow availability, and realistic order
placement are not validated. If strategies die after costs or depend on top-5
tickers, the paper should say so directly.
