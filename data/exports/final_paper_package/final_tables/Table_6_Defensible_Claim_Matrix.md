# Defensible Claim Matrix

| Claim | Supported now? | Evidence / caveat |
| --- | --- | --- |
| YouTube recommendations are associated with short-window abnormal returns. | Yes for canonical yfinance baseline | Canonical 5D p=0.001396; expanded sample weakens. |
| The signal survives low-lookahead filtering. | Yes, with timing caveat | Low-lookahead 5D p=0.003063; upload timestamp is approximate. |
| The signal survives duplicate-collapsed filtering. | Partially | Duplicate-collapsed 5D p=0.029023; 1D weaker. |
| The signal survives non-top-ticker filtering. | No | Non-top 5D mean=-0.004901; result flips negative. |
| The signal survives high-quality-only filtering. | No | A/B 5D p=0.758519. |
| The signal survives SEC filing exclusion. | Computed as SEC-only robustness | SEC-clean max n=716; SEC filings are not full news controls. |
| The signal survives Bloomberg news controls. | No | Bloomberg CSV ingestion is scaffolded; no Bloomberg data has been applied. |
| The signal survives factor adjustment. | Computed | Uses free Kenneth French factors when available; still provisional until Bloomberg total returns. |
| The signal survives intraday reaction testing. | Recent diagnostic only | Intraday reaction rows=1224; yfinance intraday limited to recent coverage. |
| The signal represents tradable alpha. | No | Calendar-time portfolio is a free-data diagnostic and does not support a tradable-alpha claim. |
| The signal is causal. | No | Observational event study with timing/news/momentum caveats. |
| The signal is better interpreted as attention/momentum amplification. | Yes | Concentration, lookahead, and momentum decomposition favor this interpretation. |
