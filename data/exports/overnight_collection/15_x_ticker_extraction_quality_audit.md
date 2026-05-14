# X Ticker Extraction Quality Audit

Generated: 2026-05-14T17:30:00Z

## Scope

- Repo commit audited: `1127dc178d0eb498a9fce58098b895d638c3328e`.
- Existing RunPod audit counts: 6,936 X posts, 5,605 X ticker mentions, 1,462 X recommendation events.
- Configured cashtag seed universe: 33 tickers from `config/x_sources/cashtags.txt`.
- Local limitation: the transferred checkout does not include the RunPod `x_posts`, `x_post_ticker_mentions`, or `x_recommendation_events` tables, nor the raw Apify item JSON. Exact explicit-cashtag versus inferred-uppercase recounts must be recomputed on the RunPod DB. This file records the committed audit evidence and the code-level cause/fix.

## Core Finding

Ticker extraction was too broad for final X event studies:

- Seed-universe mentions: 629 of 5,605, or 11.2%.
- Seed-universe recommendation events: 46 of 1,462, or 3.1%.
- Common-word or non-equity-looking tokens appeared in 1,129 ticker mentions and 452 recommendation events before filtering.

The low seed-universe match rate means the unfiltered 1,462 X recommendation events are not credible research events.

## Why It Happened

The X-specific extractor accepted three ticker sources:

1. explicit cashtags, such as `$TSLA`;
2. company-name aliases, such as `Tesla` -> `TSLA`;
3. plain uppercase tokens when a broad finance context word was nearby.

The third path was the failure mode. Broad uppercase extraction turned ordinary words, abbreviations, macro labels, crypto symbols, index-like labels, and action words into apparent equity tickers.

The project also has a broader `ticker_aliases` and ticker extraction layer for transcripts/market data. That layer was not the immediate source of the X event contamination. The X event contamination came from the X recommendation event builder using broad X mentions without a strict cashtag and seed-universe filter.

## Top False-Positive Ticker Strings

From the existing `10_x_source_classifier_quality_audit.md` top recommendation-event table:

| Token | X recommendation events | False-positive reason |
|---|---:|---|
| `AI` | 30 | common topic abbreviation; not reliable as C3.ai without explicit cashtag/seed proof |
| `US` | 23 | country/common word |
| `BUY` | 20 | action word, not ticker evidence |
| `LONG` | 19 | position/action word |
| `THE` | 19 | common word |
| `IN` | 15 | common word |
| `MC` | 15 | abbreviation |
| `AND` | 14 | common word |
| `WTS` | 14 | abbreviation/noise |
| `YOU` | 14 | common word/high-risk ticker collision |
| `TO` | 13 | common word |
| `DM` | 11 | abbreviation/noise |
| `IT` | 11 | common word |
| `NOT` | 11 | common word |
| `BTC` | 10 | crypto symbol, outside configured equity seed universe |
| `CA` | 10 | abbreviation/location |
| `HOLD` | 10 | action word |
| `WITH` | 10 | common word |
| `ALL` | 9 | common word/high-risk ticker collision |
| `OF` | 9 | common word |
| `IS` | 8 | common word |
| `SELL` | 8 | action word |
| `THAT` | 8 | common word |
| `SO` | 7 | common word/high-risk ticker collision |

These examples show that market index symbols, abbreviations, crypto tickers, action words, and common words leaked into tickers through the broad uppercase-token path.

## Accepted Seed-Universe Tickers Visible In The Existing Audit

The existing audit only preserved the unfiltered top-event table, not a strict-cashtag recount. Visible seed-universe tickers in that table included:

| Ticker | Unfiltered X recommendation events visible in audit |
|---|---:|
| `AAPL` | 7 |
| `NVDA` | 6 |
| `AMZN` | 5 |
| `GOOGL` | 4 |

The complete seed-universe event total from the committed audit was 46 of 1,462. The strict `$CASHTAG`-only count is not recoverable from the committed markdown alone and must be recomputed from `x_post_ticker_mentions.mention_type` on the RunPod DB.

## Required Counts For Final Recount

| Count | Status from committed artifacts |
|---|---|
| Events using explicit cashtags | Not available in transferred DB/artifacts; must be recomputed on RunPod DB |
| Events using inferred uppercase tickers | Not available in transferred DB/artifacts; must be recomputed on RunPod DB |
| Events matching configured seed universe | 46 of 1,462 |
| Mentions matching configured seed universe | 629 of 5,605 |

The code has been updated so future X recommendation event construction can compute these counts cleanly from `source_method` and `mention_type`.

## Conservative Ticker Rules For Final Analysis

Use these rules for final X event-study inputs:

1. Keep only explicit `$CASHTAG` mentions for X recommendation events.
2. Require ticker membership in `config/x_sources/cashtags.txt` or another frozen, documented investable equity universe.
3. Exclude common uppercase false positives before event construction.
4. Treat company-name aliases and plain uppercase tokens as diagnostic attention signals only, not final X recommendation-event tickers.
5. Exclude crypto symbols, market/macro abbreviations, country/location abbreviations, action words, and high-risk common-word ticker collisions unless manually validated.
6. Rebuild X events after filtering and report the cashtag-only event count before running any event study.

## Fixes Added In This Pass

- `extract_x_ticker_mentions()` now supports `strict_cashtag_only=True`.
- X recommendation event import now defaults to strict cashtag events filtered to the configured seed ticker universe.
- Common uppercase false positives such as `THE`, `US`, `BUY`, `LONG`, `HOLD`, `SELL`, `BTC`, `ETH`, `AI`, and similar tokens are suppressed from plain-uppercase extraction.
- X recommendation event `source_method` now records strict seed construction as `x_rules_v1_strict_cashtag_seed`.
- Regression tests cover strict cashtag extraction, seed-universe filtering, false-positive suppression, and strict event construction.

## Final Decision

The existing 1,462 unfiltered X recommendation events should not be used for final event studies. Rebuild a strict, seed-filtered X event set from normalized timestamps and explicit cashtags only after date filtering has been proven historically.
