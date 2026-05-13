# Final Presentation Talking Points

## 5-Minute Version
1. Research question: Do finfluencer recommendations generate alpha or attention?
2. Data: 11K videos, 6.4K transcripts, 2.1K events, 22 tickers.
3. Method: NLP rule extraction + event study + portfolio backtest.
4. Key finding: Short-term abnormal returns are mixed; portfolio alpha is weak after costs.
5. Caveat: yfinance prototype data, rule labels, no causal claim.

## 10-Minute Version
Add:
6. Sample design robustness: results hold across capped and balanced samples.
7. AI-assisted classifier audit: disagreement rate quantified.
8. Robust stats: bootstrap CIs, permutation tests, FDR correction.
9. Benchmark comparison: SPY, QQQ, IWM, sector ETFs.
10. Next steps: Bloomberg data, human validation, final paper.

## Likely Professor Questions

**Q: Is this causal?**
A: No. This is descriptive event-study correlation. Causality would require an instrument or natural experiment.

**Q: Is this alpha or attention?**
A: We cannot distinguish cleanly. Short-term price moves could be attention-driven. Medium-term persistence would suggest alpha, but we do not observe strong persistence.

**Q: Are labels reliable?**
A: Labels are deterministic rule-based pseudo-labels. An AI-assisted audit was conducted, but human validation is still the gold standard and has not been done.

**Q: Why yfinance?**
A: yfinance is free and sufficient for prototype analysis. All outputs are explicitly labeled as prototype-grade. Bloomberg would improve dividend/split precision and survivorship bias.

**Q: Why not human labels?**
A: Manual labeling of 2,147 events is infeasible in the timeline. The AI-assisted audit provides a reproducible robustness check.

**Q: Does this survive benchmarks?**
A: Abnormal returns are computed vs. SPY, QQQ, IWM, and sector ETFs. Some horizons show positive abnormal returns, but statistical significance is mixed after FDR correction.

**Q: Is it tradable?**
A: The portfolio backtest uses next-trading-day execution and includes 10 bps transaction costs. Sharpe ratios are modest. Real-world slippage and short constraints could further reduce returns.

**Q: What would Bloomberg change?**
A: More accurate adjusted prices, better handling of delistings/renamings, intraday data for precise execution, and institutional credibility.