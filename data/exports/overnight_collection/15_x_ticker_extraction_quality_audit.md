# X Ticker Extraction Quality Audit

Generated: 2026-05-14T16:50:00Z

## Scope

- Current branch audit after guardrail commit `0f204344f20aa4cc1b61aef7484682c49a7996da`.
- Configured cashtag seed universe: 33 tickers from `config/x_sources/cashtags.txt`.
- No Apify calls were made.
- The populated live X tables/raw Apify items are not available in this Codex session, so strict counts are reported from accessible data plus prior committed audit evidence.

## Prior Unfiltered Audit Evidence

| Metric | Value |
|---|---:|
| X posts | 6,936 |
| X ticker mentions | 5,605 |
| X recommendation events | 1,462 |
| Parsed X date coverage | 2026-05-14 to 2026-05-14 across 1 calendar day |
| Mentions in configured seed universe | 629 of 5,605 (11.2%) |
| Recommendation events in configured seed universe | 46 of 1,462 (3.1%) |

Only 46 of 1,462 prior unfiltered recommendation events matched the configured seed universe, so the original 1,462 events are not credible enough for final X event studies.

## Accessible Strict Recount Status

| Count | Result |
|---|---:|
| Accessible `x_posts` rows | not present |
| Accessible `raw_x_posts` rows | 0 |
| Events using explicit cashtags | 0 computable from accessible DB |
| Events using inferred uppercase tickers | 0 computable from accessible DB |
| Events matching configured seed universe | 0 computable from accessible DB; prior committed audit reported 46 of 1,462 before strict `$CASHTAG` recount |
| Strict `$CASHTAG` seed-filtered recommendation events | 0 computable from accessible DB |

These zeroes are an access/data-availability result, not a validated recount of the overnight RunPod dataset. A populated `x_posts`/`x_post_ticker_mentions`/`x_recommendation_events` DB or raw Apify item JSON is required for a real strict recount.

## Top False-Positive Ticker Strings

From the prior unfiltered audit, the highest-risk recommendation-event ticker strings were:

| Token | Prior unfiltered X recommendation events | False-positive reason |
|---|---:|---|
| `AI` | 30 | topic abbreviation; not reliable as C3.ai without explicit cashtag proof |
| `US` | 23 | country/common word |
| `BUY` | 20 | action word |
| `LONG` | 19 | action word |
| `THE` | 19 | common word |
| `IN` | 15 | common word |
| `MC` | 15 | abbreviation/noise |
| `AND` | 14 | common word |
| `WTS` | 14 | abbreviation/noise |
| `YOU` | 14 | common word/high-risk ticker collision |
| `TO` | 13 | common word |
| `DM` | 11 | abbreviation/noise |
| `IT` | 11 | common word |
| `NOT` | 11 | common word |
| `BTC` | 10 | crypto symbol outside configured equity seed universe |
| `HOLD` | 10 | action word |
| `SELL` | 8 | action word |

## Top Accepted Tickers After Strict Cashtag Filtering

A true top-accepted strict ticker table cannot be recomputed from the accessible DB because the populated X tables/raw item JSON are absent. The only accepted seed-universe tickers visible in the prior committed examples were `AAPL`, `NVDA`, `AMZN`, and `GOOGL`; that example list is not a full strict ranking.

## Recommended Strict Ticker Rules For Final Analysis

1. Use only explicit `$CASHTAG` mentions for X recommendation events.
2. Require membership in `config/x_sources/cashtags.txt` or another frozen documented investable universe.
3. Suppress uppercase false positives before event construction.
4. Exclude company-name aliases and plain uppercase tokens from final X event studies unless manually validated.
5. Exclude crypto symbols, macro/location abbreviations, action words, and high-risk common-word collisions.
6. Report strict counts by source type, ticker, and date before running any X event-study output.

## Credibility Decision

- The strict sample is not currently credible enough for X-only event studies because it cannot be rebuilt from the accessible data and historical date coverage is unproven.
- X should be used only as a diagnostic/future-work extension until a populated DB/raw-item audit proves historical dates and strict ticker precision.
- Final papers must not use the 1,462 unfiltered X recommendation events as final research events.
