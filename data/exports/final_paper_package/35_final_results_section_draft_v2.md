# Final Results Section (v2)

## Headline Findings
YouTube recommendations are associated with a mean 5-day abnormal return of **0.52% (p=0.001)** in the canonical 16-ticker baseline. This result is robust to timing filters, with the low-lookahead sample showing a 5-day AR of **0.71% (p=0.003)**.

## SEC-Only Robustness
When events with nearby material SEC filings are excluded, the 5-day abnormal return **increases to 0.80% (p=0.000)**. This suggests that the signal is not a mere byproduct of official filings, although other news sources (Bloomberg) are not yet controlled.

## Deeper Heterogeneity and Stress Tests
- **Concentration Risk**: The positive association disappears when the "Top 5" technology tickers are removed. The remaining sample shows a significantly **negative** association (-0.68%, p=0.002), suggesting a "pump and fade" dynamic for less-covered stocks.
- **Duplicate Robustness**: Collapsing multiple mentions reduces the 1-day significance, indicating that repetitive content contributes to the headline momentum.
- **Factor Adjustment**: Alpha survives several factor models (FF5) in the low-lookahead sample but is not robust across all specifications, particularly when duplicates are collapsed.

## Regression Evidence
Cross-sectional OLS models confirm that the **Top 5 ticker dummy** and **SEC-clean status** are the strongest predictors of positive abnormal returns, even after controlling for pre-event momentum.
