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
- Multi-provider public-news master: `news_confound_master/`; current `multi_source_clean` n = 0, so clean-news claims remain prohibited
- Market-implied screen: `market_implied_confounds/` (not news-clean)

## Factor and portfolio methods

- Kenneth French **daily** factors
- Calendar-time portfolios with **HAC / Newey-West** standard errors
- Beta-estimated factor alpha tables (supporting diagnostics)

## Falsification and mechanism

- Date-shift and random-date placebos
- Creator cross-ticker placebos
- Research-frontier modules: selection, attention, reversal, predictive holdouts
- **Information environment:** analyst relay (FMP/Finnhub preferred; yfinance diagnostic gap-fill), Bloomberg validation, yfinance analyst diagnostic layer, market sentiment, narrative relay, originality taxonomy, incremental predictive value
- Analyst stance mapping is conservative: interpretable grade strings are normalized to bullish / neutral / bearish; ambiguous provider action strings stay unknown and are audited
- yfinance current snapshots are diagnostic only; dated pre-event yfinance rows can support exploratory event-time splits, but do not establish causality
- Current snapshots are not event-time evidence; event-time claims require dated pre-event records
- Multiple-testing audit (BH FDR, Holm) on collected p-values; tier hierarchy in `PRIMARY_SECONDARY_EXPLORATORY_HIERARCHY.md`

## Long-horizon discipline

- **504D** reported only with explicit censoring / thin-n caveats — **diagnostic**, not a primary claim

## Data inputs (student-grade)

- Event-study returns are generated from the repo market-data pipeline; Bloomberg-derived fields are a separate validation/mechanism layer
- yfinance analyst metadata remains diagnostic; Bloomberg validation is included but does not establish causality, public-news-clean alpha, creator skill, or tradability
- Transcript-supported events from automated classification with proxy QA

## May 2026 — news layer and claim discipline (RunPod)

- **No broad tradable YouTube alpha**; heterogeneity and salience matter more than uniform creator skill.
- **Top-5 raw positives** reflect concentration, consensus relay, and attention—not causal creator skill.
- **Non-top weakness** is **not** automatically public-news-clean; **unknown_news_coverage is never clean**.
- **multi_source_clean** is strict (may be zero); provider failures, **403/429**, missing keys, and shallow history are **not** “no news.”
- **FNSPID** adds historical *media* coverage (not official disclosure) through about 2023 but does not cover every recent event window.
- **Marketaux, EODHD, Alpaca/Benzinga, Massive/Polygon, NewsAPI** are free-tier **diagnostic** supplements; **NewsAPI** developer tiers are not a historical backbone.
- **yfinance** analyst snapshots in this repo are **diagnostic only** unless dated pre-event rows exist; they are **not** Bloomberg-grade validation.
- Report **news sensitivity bounds** because public-news identification remains incomplete; frame conclusions as **mechanism-consistent**, not causal.


