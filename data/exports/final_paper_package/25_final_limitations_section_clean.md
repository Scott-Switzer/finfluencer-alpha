# Final Limitations Section

The findings of this study are subject to several critical limitations that preclude a causal or trade-ready interpretation.

## Observational Design
This study is observational and does not identify a causal relationship. We report an **association** between social media activity and price moves; it remains possible that creators are reacting to price trends that are not fully captured by the daily momentum controls.

## Timing and Execution Risks
- **Timestamp Accuracy**: YouTube upload timestamps are used as a proxy for information release. However, videos may be recorded hours or days before upload, and "Premiere" or private-sharing features could introduce timing discrepancies.
- **Execution Lag**: The analysis assumes entry at the adjusted close of the effective trading day. Real-world execution of these signals would involve significant latency and slippage.

## Data and Coverage Gaps
- **News Coverage**: SEC EDGAR flags only capture official filings. A significant portion of market-moving news (press releases, analyst actions) is not captured in this free-data build and requires Bloomberg-grade validation.
- **Intraday Data**: Free intraday coverage is limited to the most recent period, preventing a full-sample high-frequency diagnostic.
- **Market Data**: All returns are based on free yfinance daily prices, which may not account for the total return (dividends/splits) as accurately as licensed Bloomberg data.

## Portfolio Feasibility
- **Transaction Costs**: Calendar-time portfolios demonstrate that the apparent alpha disappears when transaction costs reach 25 basis points.
- **Liquidity**: The strategy assumes the ability to execute large positions in both long and short directions without market impact, which is unrealistic for many of the smaller-cap tickers in the broader sample.
