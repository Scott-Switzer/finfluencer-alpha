# Final Methods Section

## Event Study Framework
We employ a standard event-study methodology using a [0, +1] and [0, +5] trading-day window. The "event date" is defined as the first available trading day on or after the YouTube upload timestamp. Abnormal returns (AR) are calculated as the raw stock return minus the benchmark (SPY) return.

## Robustness Specifications
To isolate the social media association, we implement six layers of robustness:
1. **Timing Lookahead**: Segregation of "low-lookahead" buckets (before-open, weekends) where the video likely predates the first trade.
2. **Duplicate-Cluster Collapse**: Aggregation of multiple mentions by the same creator on the same day into a single observation to avoid over-counting repetitive content.
3. **SEC-Only Robustness**: Filtering out events near official SEC filings to ensure the signal is not primarily explaining corporate reports.
4. **Factor-Alpha Models**: Adjustment for Fama-French 5-factors and Momentum to test for idiosyncratic alpha.
5. **Concentration Stress Tests**: Exclusion of the "Top 5" mega-cap technology tickers to test for broad-sample validity.
6. **Cross-Sectional Regressions**: OLS models with creator and ticker fixed effects to identify the drivers of the abnormal return.

## Statistical Controls
T-stats and p-values are computed for all means, with Benjamini-Hochberg q-values applied to control for the False Discovery Rate across multiple specifications.
