# Final Claims Guardrail

| Safe claim | Claim to avoid |
|---|---|
| In the prototype sample, 132 clean events were identified and 131 matched to market data. | The dataset is complete and fully representative of all finfluencer recommendations. |
| In this prototype run, mean abnormal returns are slightly positive at 1D/5D and negative at 20D. | Finfluencer recommendations reliably lose money over time. |
| 20-day abnormal return and 20-day CAR are statistically significant at roughly the 5% level in this sample. | The results are universally statistically robust and final. |
| Results are benchmark-adjusted relative to SPY and should be read as relative, not absolute, performance. | The analysis measures absolute investment skill with no benchmark dependence. |
| The event-study design here is associational and does not identify causal effects. | The study proves finfluencers cause investor gains or losses. |
| One unmatched event (`event_id=420`, `SQ`) was transparently diagnosed as `no ticker data`. | The unmatched event means the whole pipeline is invalid. |
| Ticker alias support (for example `SQ -> XYZ`) improves symbol continuity while preserving original event tickers for auditability. | Alias mapping eliminates all ticker-history and matching issues. |
| The current market data is yfinance prototype data and Bloomberg replacement is required for final inference. | yfinance prototype outputs are equivalent to final Bloomberg-quality results. |
| Sample composition is concentrated in a few tickers and creators, which may influence pooled averages. | The sample composition has no meaningful effect on the conclusions. |
| These outputs are a strong prototype foundation for a final Bloomberg rerun and robustness checks. | No further validation or rerun is needed before final submission. |
