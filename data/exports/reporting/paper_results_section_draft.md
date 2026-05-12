# Results

The prototype event-study sample includes 132 clean recommendation events derived from transcript-based event construction and strict rules-based filtering. Of these 132 events, 131 were successfully matched to market data, yielding a 99.24% match rate. One event remained unmatched (`event_id=420`, `SQ`, published 2020-12-07), with diagnostics indicating `no ticker data` for that case.

Abnormal return is defined as the event stock return minus the SPY benchmark return over the same horizon. Cumulative abnormal return (CAR) is the sum of daily abnormal returns across the selected horizon. We report results for 1-day (1D), 5-day (5D), and 20-day (20D) post-event windows.

In the matched sample (`n=131`), mean abnormal return is positive at short horizons but negative at the medium horizon. Specifically, mean abnormal return is 0.004285 at 1D and 0.003410 at 5D, then declines to -0.026388 at 20D. CAR follows a similar pattern: mean CAR is 0.002668 at 5D and -0.026894 at 20D. This pattern is consistent with a short-run positive association followed by weaker medium-run performance.

Statistical tests should be interpreted cautiously. The 20D abnormal return estimate shows a negative t-statistic (`t=-2.044981`) with a two-sided p-value of 0.042973, and 20D CAR similarly shows `t=-2.139741`, `p=0.034335`. In contrast, short-horizon tests are not statistically significant (`p=0.241103` for abnormal return 1D; `p=0.641155` for abnormal return 5D; `p=0.715009` for CAR 5D). Accordingly, the strongest statistical signal in this prototype appears at the 20-day horizon, not at 1D/5D.

The composition of the sample is concentrated in a small set of tickers, especially TSLA (41 events), AAPL (20), and NVDA (18), with additional weight in AMD (14) and AMZN (10). This concentration implies that pooled estimates partly reflect large-cap, high-attention names and may not generalize to a broader equity universe.

Grouped summaries further show heterogeneity by creator, ticker, year, recommendation type, and direction. For example, creator-level and ticker-level 20D means vary substantially in sign and magnitude, indicating that aggregate averages mask meaningful subgroup differences. These subgroup patterns are informative for interpretation but should not be over-read given uneven group sizes.

These findings are associational and should not be interpreted as causal effects of finfluencer content on investor outcomes. The current market-data source is interim yfinance/Yahoo prototype data, and Bloomberg replacement is required before final inference claims are made.
