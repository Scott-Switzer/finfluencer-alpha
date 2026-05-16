# Professor One-Page Update (Audit Final)

The repository has been audited for consistency and the final empirical defense package is ready. The results are based on the **locked sample of 8,994 transcripts** and **1,554 recommendation events**.

## Key Empirical Findings
- **Headline Persistence**: The 5D abnormal return (**0.52%, p=0.001**) is robust to timing filters.
- **News Isolation**: Removing events with SEC filings **increases** the 5D return to **0.80%**, indicating the signal is distinct from corporate filings.
- **Factor Sensitivity**: Alpha survives FF5 and Momentum controls in the low-lookahead sample but disappears when duplicates are collapsed, suggesting "volume of attention" is a key driver.
- **Stress Test Failure**: The signal **reverses to negative** when the Top 5 tech tickers are excluded, highlighting extreme concentration risk.

## Audit Reconciliation
- **Transcript Count**: Reconciled from previous estimates (9,992) to the current database truth (**8,994**).
- **Evidence Hierarchy**: A "Hierarchy of Evidence" has been created to guide the final paper's claims, from the headline result to the most conservative stress tests.

## Next Steps (Bloomberg Terminal)
The package is "Bloomberg Ready." At school, we can:
1. Replace yfinance prices with Bloomberg total-return data.
2. Populate the prepared CSV templates for full News, Earnings, and Analyst controls.
3. Rerun the script to generate the final, terminal-validated tables.

The current findings support a claim of **"attention amplification"** rather than "causal alpha."
