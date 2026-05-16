# Final Limitations Section (v2)

This study identifies a statistical association but does not claim causality. Several critical limitations must be acknowledged:

1. **Information Confounding**: The current "Free-News Clean" specification is a simulated diagnostic scaffold rather than an empirical GDELT or Alpha Vantage news-control layer. Institutional-grade isolation from Bloomberg headlines, specific analyst actions, or unfiled press releases is not yet achieved.
2. **Sample Lock**: The 1,554-event final panel is reproducible from committed manifests, but the 8,994 transcript count is a historical locked-package count that is not reconstructible from the current live RunPod DB. The expanded live DB has 9,992 transcript rows and 2,341 recommendation-event rows that require a separate lock before use.
3. **Timing Approximation**: YouTube upload timestamps are proxies for recommendation release. We do not account for private "Premiere" sharing or recording-to-upload latencies.
4. **Data Window Constraints**: yfinance intraday coverage is only available for recent events, which prevents a full-sample high-frequency analysis.
5. **Execution and Liquidity**: The calendar-time portfolio model does not account for market impact, bid-ask spreads, or the borrow costs associated with short positions.
6. **Sample Selection**: The creator sample is limited to 35 prominent influencers, which may introduce survivorship or selection bias.
