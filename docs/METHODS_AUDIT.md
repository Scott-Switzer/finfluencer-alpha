# Methods audit

## Sample versioning

| Package | Role |
| --- | --- |
| `final_paper_package_v2_expanded/` | **Primary** empirical sample (2,341 events) |
| `final_paper_package/` | Historical v1 benchmark |

## Event-study conventions

- SPY-adjusted BHAR/CAR from daily prices
- Right-censoring flags on long horizons
- Overlap documented; duplicate-collapsed and low-lookahead slices available

## Confound handling

- **Clean / confounded / unknown** coding for public news and SEC/earnings
- **Unknown public-news states are never coded as clean**
- Master panel: `confounds_expanded/`
- Market-implied screen: `market_implied_confounds/` (not news-clean)

## Factor and portfolio methods

- Kenneth French **daily** factors
- Calendar-time portfolios with **HAC / Newey-West** standard errors
- Beta-estimated factor alpha tables (supporting diagnostics)

## Falsification and mechanism

- Date-shift and random-date placebos
- Creator cross-ticker placebos
- Research-frontier modules: selection, attention, reversal, predictive holdouts
- **Information environment:** analyst relay (FMP/Finnhub preferred; yfinance diagnostic gap-fill), yfinance analyst diagnostic layer, market sentiment, narrative relay, originality taxonomy, incremental predictive value
- Analyst stance mapping is conservative: interpretable grade strings are normalized to bullish / neutral / bearish; ambiguous provider action strings stay unknown and are audited
- yfinance current snapshots are diagnostic only; dated pre-event yfinance rows can support exploratory event-time splits, but do not establish causality
- Multiple-testing audit (BH FDR, Holm) on collected p-values; tier hierarchy in `PRIMARY_SECONDARY_EXPLORATORY_HIERARCHY.md`

## Long-horizon discipline

- **504D** reported only with explicit censoring / thin-n caveats — **diagnostic**, not a primary claim

## Data inputs (student-grade)

- yfinance-derived prices; not Bloomberg
- yfinance analyst metadata is not Bloomberg-grade validation; Bloomberg remains the planned higher-quality validation layer
- Transcript-supported events from automated classification with proxy QA
