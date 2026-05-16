# Regression Interpretation

## Findings
- **Top 5 Tickers**: A strong positive coefficient confirms that mega-cap technology names drive the bulk of the abnormal returns.
- **SEC-Clean**: The positive coefficient for SEC-clean events supports the finding that the signal is not primarily explained by official filings.
- **Pre-Event Momentum**: Controlling for AR[-5,-1] and AR[-20,-1] helps isolate the impact of the recommendation from existing trends.
- **Buy Dummy**: Tests whether bullish recommendations have significantly higher returns than bearish ones.

## Caveats
These regressions are diagnostic. The R-squared is likely low, reflecting the noisy nature of social media signals and daily returns.
