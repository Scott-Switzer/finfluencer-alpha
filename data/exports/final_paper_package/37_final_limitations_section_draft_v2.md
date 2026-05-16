# Final Limitations Section (v2)

This study identifies a statistical association but does not claim causality. Several critical limitations must be acknowledged:

1. **Information Confounding**: While our "Free-News Clean" specification incorporates GDELT and Alpha Vantage proxies, it remains a subset of total public news. Institutional-grade isolation from Bloomberg headlines, specific analyst actions, or unfiled press releases is not fully achieved.
2. **Timing Approximation**: YouTube upload timestamps are proxies for recommendation release. We do not account for private "Premiere" sharing or recording-to-upload latencies.
3. **Data Window Constraints**: yfinance intraday coverage is only available for recent events, which prevents a full-sample high-frequency analysis.
4. **Execution and Liquidity**: The calendar-time portfolio model does not account for market impact, bid-ask spreads, or the borrow costs associated with short positions.
5. **Sample Selection**: The creator sample is limited to 35 prominent influencers, which may introduce survivorship or selection bias.
