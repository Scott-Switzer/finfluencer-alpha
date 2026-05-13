# Current State Audit Summary

## Dataset Overview

| Metric | Count |
|--------|-------|
| Total YouTube videos in DB | 11,922 |
| Videos with transcripts (full_text > 50 chars) | 6,384 |
| Transcript coverage | 53.5% |
| Transcript recommendation events (DB) | 2,147 |
| Candidate events (recommendation_candidates) | 2,307 |

## Event Pipeline Bottleneck

The current clean-event pipeline is severely bottlenecked:

1. `build-event-validation-sample` extracts a **150-event sample** from the DB.
2. `auto-label-event-validation` labels only those **150 events**.
3. `build-clean-auto-labeled-events` merges the labeled sample with the full event export.
4. Result: only **113 clean events** in `clean_auto_labeled_events.csv`.

**Root cause:** The pipeline treats the 150-event validation sample as the entire universe instead of labeling all 2,147 DB events.

## Event Study Coverage

| Metric | Count |
|--------|-------|
| Clean events CSV | 113 |
| Event-study matched rows | 131 |
| Valid 1D abnormal returns | ~131 |
| Valid 5D abnormal returns | ~130 |
| Unique tickers in events (DB) | 22 |
| Unique tickers with market data | 16 |
| Missing market-data tickers | AMC, SHOP, SQ, GME, HOOD, SMCI, COIN |

**Critical finding:** 6 tickers with events have no yfinance market data, causing event-study dropout.

## Market Data

- **Source:** yfinance (prototype-grade, clearly labeled)
- **File:** `data/imports/market_data/yfinance_market_data.csv`
- **Rows:** 26,151
- **Date range:** 2019-09-19 to 2026-05-13
- **Benchmark:** SPY only
- **Missing benchmarks:** QQQ, IWM, sector ETFs

## Classifier Status

- **Version:** transcript_rules_v2
- **Method:** Rules-based deterministic pseudo-labeling
- **Human validation:** None
- **AI-assisted adjudication:** Not yet implemented
- **Stance distribution (DB):**
  - Bullish/bullish_recommendation: 1,652
  - Bearish/bearish_recommendation: 495

## Creator Coverage

- 524 unique videos with events
- Top creators by event volume need further profiling
- No explicit 250-per-creator cap found in current code

## Main Bottlenecks

1. **Validation sample bottleneck:** Only 150 events are labeled → 113 clean events.
2. **Missing market data:** 6 tickers lack prices → ~200+ events cannot be matched.
3. **Single benchmark:** Only SPY; no QQQ, IWM, or sector adjustment.
4. **Short horizons:** Only 1D and 5D returns computed.
5. **No portfolio tests:** Event averages only; no investable portfolio backtests.
6. **No robust stats:** Bootstrap and permutation tests exist but only for 1D/5D.
7. **No AI classifier audit:** Labels are unvalidated.

## Files Used by Current Event Study

1. `data/exports/validation/clean_auto_labeled_events.csv` — clean events (113 rows)
2. `data/imports/market_data/yfinance_market_data.csv` — market data (26,151 rows)
3. `data/seeds/ticker_aliases.csv` — ticker alias mappings
4. `src/finfluencer_alpha/event_study.py` — event-study engine
5. `src/finfluencer_alpha/statistical_models.py` — statistical inference

## Next Steps

- Build clean events from **all 2,147 DB events** using deterministic rules.
- Fetch yfinance data for missing tickers.
- Expand to multi-benchmark, multi-horizon returns.
- Add portfolio backtests with transaction costs.
- Add AI-assisted classifier audit.
- Run robust statistics with FDR correction.

