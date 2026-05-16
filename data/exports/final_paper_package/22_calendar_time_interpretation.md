# Calendar-Time Interpretation

## Strategy Performance Diagnostics
The calendar-time portfolio analysis tests whether an investor could have earned alpha by following all buy/sell recommendations in real-time.

### Best-Performing Configuration
The **1-day holding period (Buy-only)** strategy yields a Sharpe ratio of **2.93** with an annualized return of **126%**, assuming **zero transaction costs**.

### Sensitivity to Costs
The strategy is extremely fragile to transaction costs:
- **0 bps**: Sharpe 2.93 (Buy-only, 1D)
- **10 bps**: Sharpe 1.76 (Buy-only, 1D)
- **25 bps**: Sharpe **0.48** (Buy-only, 1D)

Alpha effectively vanishes at a 25 basis point (bps) cost per trade. Given that YouTube-driven trades often involve high-turnover portfolios (118% average turnover for 1D holding), even modest commissions and bid-ask spreads would eliminate the excess return.

## Risk and Drawdown
- **Max Drawdown**: The 5-day Long/Short strategy experienced a max drawdown of **-38%**, and the 5-day Buy-only strategy reached **-54%**.
- **Hit Rate**: The daily hit rate (percentage of days with positive returns) hover around **53-54%**, which is only slightly better than a coin flip, despite the high annualized return.

## Why this is not "Tradable Alpha"
1. **Turnover**: 118% daily turnover implies the entire portfolio is replaced every day, which is operationally complex and costly.
2. **Execution Lag**: The model assumes entry at the adjusted close of the "effective trading day." Real-world delays in transcript processing and signal execution would likely erode the remaining small margin.
3. **Liquidity**: The calendar-time model does not account for market impact. Executing large trades on the "Long/Short" signals (especially the short side) would be difficult and expensive.
4. **Conclusion**: These results should be viewed as **diagnostic proof of association** rather than a viable investment strategy.
