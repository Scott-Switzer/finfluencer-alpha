# Final Results Section

The empirical analysis reveals a statistically significant positive association between YouTube recommendations and short-term abnormal returns in the headline sample, though the effect is sensitive to ticker concentration and transaction costs.

## Headline Association
In the canonical 16-ticker baseline, recommendations are associated with a mean 1-day abnormal return of **0.27% (p=0.001)** and a 5-day abnormal return of **0.52% (p=0.001)**.

## Robustness and Stress Testing
The association remains robust in the **low-lookahead** timing specification, which shows a 5-day abnormal return of **0.71% (p=0.003)**. This supports the hypothesis that the observation is not merely an artifact of same-day upload timing.

When controlling for official corporate news via **SEC-clean filtering**, the 5-day abnormal return **increases to 0.80% (p=0.000)**, suggesting that the YouTube signal is strongest when not confounded by material corporate filings.

## Points of Fragility
However, the signal fades or reverses under more stringent conditions:
1. **Duplicate Clustering**: Collapsing multiple mentions reduces the 1-day significance, indicating that the aggregate headline result is partially driven by repetitive "echo" content.
2. **Non-Top Tickers**: When excluding the "Top 5" tickers (NVDA, TSLA, AAPL, AMD, AMZN), the association for the remaining sample becomes **significantly negative (-0.68%, p=0.002)**. This implies that for smaller or less-covered tickers, YouTube recommendations are associated with immediate mean reversion or "pump and fade" dynamics.
3. **Factor Adjustment**: While alpha survives in several factor models for the low-lookahead sample, it vanishes in the duplicate-collapsed sample, suggesting that broad social media attention (volume) is the primary driver of the excess return.

## Summary
The evidence is consistent with **attention amplification** rather than idiosyncratic alpha. YouTube recommendations appear to amplify existing momentum in mega-cap technology stocks but fail to provide a consistent or tradable signal for the broader market.
