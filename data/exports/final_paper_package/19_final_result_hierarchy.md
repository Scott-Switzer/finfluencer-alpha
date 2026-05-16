# Final Result Hierarchy (Evidence Ladder)

This hierarchy tracks the strength and persistence of the abnormal return signal across increasingly strict specifications.

Sample-lock note: the evidence ladder is based on the committed locked artifact
package. The event panel is manifest-supported at 1,554 events; the associated
8,994 transcript count is historical and not reconstructible from the current
expanded RunPod DB.

## The Evidence Ladder

| Level | Specification | 1D Return | 1D p-value | 5D Return | 5D p-value | Significance |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Headline** | Canonical baseline (16-ticker) | 0.27% | 0.001 | 0.52% | 0.001 | Strong |
| **2. Timing** | Low-lookahead risk | 0.20% | 0.036 | 0.71% | 0.003 | Robust |
| **3. News** | SEC-clean (Expanded) | 0.15% | 0.078 | 0.80% | 0.000 | **Strengthened** |
| **4. Cluster** | Duplicate-collapsed | 0.13% | 0.165 | 0.40% | 0.029 | Weak (1D) / Modest (5D) |
| **5. Alpha** | Factor-adjusted (FF5) | 0.24% | 0.002 | 0.29% | 0.054 | Mixed |
| **6. Stress** | Non-top-ticker (Ex-Top 5) | -0.68% | 0.002 | -0.49% | 0.061 | **Reverses** |

## Key Interpretations
- **Persistence**: The association is more robust at the 5-day horizon than the 1-day horizon across most specifications.
- **SEC-Only Robustness**: Removing events with nearby official SEC filings increases the 5-day return, suggesting the YouTube signal is not primarily explained by these official filings. However, this specification does not cover Bloomberg headlines, analyst actions, earnings timestamps, press releases, or macro/sector news.
- **Concentration Risk**: The positive association is heavily driven by the "Top 5" tickers (NVDA, TSLA, AAPL, AMD, AMZN). In the broader sample, the signal disappears or reverses, suggesting it may be an "attention amplification" effect specific to high-momentum stocks.
- **Duplicate Robustness**: Collapsing multiple mentions into a single cluster reduces the 1D significance, indicating that "recap" or "echo" videos contribute to the aggregate headline result.
