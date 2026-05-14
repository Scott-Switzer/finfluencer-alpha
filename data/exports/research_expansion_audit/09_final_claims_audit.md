# Final Claims Audit

## 1. Verified Dataset Facts
- Current RunPod DB videos: 11,922.
- Successful transcripts: 9,747.
- Strict usable transcripts (`full_text > 50`): 9,742.
## 2. Verified Event-Label Facts
- DB recommendation rows: 2,341.
- Conservative clean row-level pseudo-labels: 562.
- Corrected unique video/ticker/date events for returns: 473.
## 3. Verified Market-Data Facts
- Market data is yfinance prototype data, with supplemental yfinance benchmark/sector fetches where needed.
## 4. Verified Event-Window Findings
- 1D: N=471, mean SPY abnormal return=0.1332%, p=0.365.
- 1W: N=465, mean SPY abnormal return=0.3043%, p=0.275.
- 1M: N=430, mean SPY abnormal return=1.2265%, p=0.03779.
- 3M: N=367, mean SPY abnormal return=3.3994%, p=0.005208.
- 6M: N=277, mean SPY abnormal return=6.5903%, p=0.001543.
- 1Y: N=196, mean SPY abnormal return=19.3659%, p=2.5e-07.
- 2Y: N=101, mean SPY abnormal return=55.7215%, p=4.7e-06.
- PRE_1W: N=471, mean SPY abnormal return=-0.2562%, p=0.3632.
## 5. Verified Portfolio Findings
- price_target_only 63D: Sharpe=1.7829, total return=521.61%, N=49.
- price_target_only 126D: Sharpe=1.5272, total return=841.43%, N=40.
- buy_only 126D: Sharpe=1.2066, total return=831.53%, N=231.
- buy_only 63D: Sharpe=1.1236, total return=518.86%, N=314.
- buy_only 21D: Sharpe=1.1019, total return=288.33%, N=370.
## 6. Verified Benchmark Findings
- Benchmark-adjusted results are descriptive and sensitive to horizon, benchmark, and event deduplication.
## 7. Verified Classifier Limitations
- Labels are rules-based pseudo-labels. There is no human ground truth.
- AI audit artifacts are not human validation and filled AI labels are missing/synthetic.
## 8. Claims Supported
- The project can claim dataset size, transcript coverage, conservative pseudo-labeled event counts, and descriptive abnormal returns.
## 9. Claims Not Supported
- Do not claim causality or that finfluencers beat the market.
## 10. Claims Requiring Bloomberg
- Institutional-grade adjusted returns, intraday execution, delisting/survivorship checks.
## 11. Claims Requiring Human Validation
- Classifier accuracy, precision, recall, and false-positive rates.
## 12. Claims Requiring Out-of-Sample Testing
- Tradable alpha, strategy persistence, creator skill.
## 13. Final Recommended Thesis
- YouTube finfluencer recommendations show horizon-dependent descriptive abnormal returns in prototype data, but evidence is not sufficient for causal alpha claims after correcting event labels and duplicate mentions.
## 14. Exact Language To Use In The Paper
- "Using yfinance prototype market data and rule-generated pseudo-labels..."
- "Descriptive benchmark-adjusted event-window returns..."
- "Conservative clean events are deduplicated at the video/ticker/date level for return tests."
## 15. Exact Language To Avoid
- "Finfluencers beat the market."
- "Causal impact."
- "Human-validated labels."
- "Bloomberg-grade returns."
