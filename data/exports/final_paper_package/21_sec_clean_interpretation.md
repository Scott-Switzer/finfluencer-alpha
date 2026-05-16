# SEC-Clean Interpretation

## Definition
"SEC-Clean" refers to a subset of the recommendation sample where no material SEC filings (8-K, 10-Q, 10-K, S-1, 424B) were identified within a ±5-day window of the YouTube upload.

## Analysis of Results
| Sample | 5D Abnormal Return | p-value | Interpretation |
| --- | --- | --- | --- |
| **Headline Baseline** | 0.52% | 0.001 | Base association |
| **SEC-Clean Expanded** | 0.80% | 0.00018 | **Stronger** |
| **SEC-Clean Low-Lookahead**| 1.25% | 0.000057 | **Strongest** |

### Strengthening of the Result
Surprisingly, removing events with nearby SEC filings **strengthens** the 5-day abnormal return result. This suggests that:
1. YouTube recommendations are not merely summarizing or "front-running" official company filings.
2. The presence of a social media recommendation (absent nearby official filings) is associated with higher short-term abnormal returns, potentially due to the absence of the "sell the news" effect often seen after official filings.

## Limitations and Need for Bloomberg
While SEC-clean filters capture material corporate events, they do **not** capture:
- Unfiled press releases (e.g., new product announcements).
- Analyst upgrades/downgrades.
- General sector news or macroeconomic events.
- Intraday price movements that occur *between* the filing and the upload.

For a true "causal" claim of social media impact, the Bloomberg future validation layer (capturing non-SEC news) is still required to confirm that these remaining events are not confounded by other public information.
