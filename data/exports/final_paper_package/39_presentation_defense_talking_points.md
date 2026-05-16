# 60-Second Defense Memo: FIN 496 Capstone

**Objective**: Summarize the empirical defense package for the professor.

**1. The "What"**:
We analyzed 8,994 YouTube transcripts from 35 financial influencers, identifying 1,554 recommendation events. Our goal was to determine if these recommendations are associated with short-term abnormal returns.

**2. The "Headline"**:
In our primary 16-ticker baseline, we find a statistically significant 5-day abnormal return of **0.52% (p=0.001)**. This result holds even when we filter for upload timing and exclude events near official SEC filings (SEC-clean n=716, mean=0.80%).

**3. The "Fragility"**:
The signal is not broad-market alpha. It is highly concentrated in "Top 5" tech tickers (NVDA, TSLA, AAPL, AMD, AMZN). When these are removed, the association reverses (**-0.68%, p=0.002**), suggesting a "pump and fade" dynamic for the broader market.

**4. The "Verdict"**:
The phenomenon is **attention amplification**. Social media creators synchronize with and amplify existing momentum in mega-cap technology stocks. While the statistical association is real, high transaction costs (decays at 25 bps) make it unlikely to be a source of tradable idiosyncratic alpha.

**5. Ready for Bloomberg**:
The package is "Bloomberg Ready." We have prepared CSV templates to replace our free yfinance/SEC data with professional terminal data for final validation of non-SEC news and total returns.
