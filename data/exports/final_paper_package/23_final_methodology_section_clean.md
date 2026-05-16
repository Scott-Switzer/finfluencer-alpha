# Final Methodology Section

This study utilizes a reproducible NLP and event-study pipeline to analyze the association between YouTube-based financial recommendations and short-term stock returns.

## Sample Construction
The sample consists of **8,994** English-language transcripts collected from 35 prominent financial creators. From these, a classifier identified **1,554** distinct recommendation events where a specific ticker and a directional stance (bullish or bearish) were supported by transcript evidence. The sample covers 23 unique tickers, primarily concentrated in large-cap technology names.

## Event Window and Price Data
Abnormal returns are computed using local daily adjusted closing prices. The "effective trading date" is defined as the first available trading day on or after the YouTube upload timestamp. The primary event windows are 1-day (AR_0_1) and 5-day (AR_0_5).

## Robustness Layers
To ensure a consistent audit, the results are subjected to six layers of robustness:
1. **Timing Buckets**: Segregating upload timestamps into "low-lookahead" buckets (before-open, weekends) to minimize the risk of same-day price moves predating the public video.
2. **Duplicate Clustering**: Collapsing multiple mentions by the same creator on the same day into a single observation to avoid over-weighting repetitive content.
3. **SEC-Clean Filtering**: Identifying and excluding events that overlap with material SEC filings (8-K, 10-Q, etc.) to isolate the social media signal from official corporate news.
4. **Factor Adjustment**: Controlling for broad market risk, size, value, profitability, and investment factors using the Fama-French 5-factor model.
5. **Momentum Decomposition**: Adjusting for pre-event momentum to distinguish between "alpha" and the amplification of existing trends.
6. **Calendar-Time Portfolios**: Constructing hypothetical portfolios to test the statistical persistence of the association over time.

## Limitations of Data Sources
This analysis relies on free market data and automated SEC filing metadata. Bloomberg data is treated as a future validation layer for total-return pricing and comprehensive non-SEC news controls.
