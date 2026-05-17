# Market Sentiment Summary

# Market sentiment regime layer

- VIX source: **cboe_csv**
- AAII: **skipped_no_cache** (optional local cache at `_aaii_compact.csv`)
- Events tagged: **2322**

## Required reading
Sentiment regimes are **conditioning variables** for heterogeneity — not causal identification of finfluencer skill.

### Non-top underperformance by regime
Inspect `returns_by_market_sentiment_regime.csv` for `sample=non_top` and `horizon=21D`.

Market-implied quiet (separate layer): non-top + market_quiet 21D SPY BHAR ≈ **-0.56%** — sensitivity only, **not** public-news-clean.
