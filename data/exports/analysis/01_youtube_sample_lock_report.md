# YouTube Locked Sample Report

- Generated UTC: `2026-05-15T23:52:34Z`
- Branch: `x-youtube-full-research-expansion`
- HEAD: `42e5d878ed1ff0d64e338aca7300bab275e7d6b9`

## Locked Counts

- Transcripts (locked): `9992`
- Accepted recommendation events (locked): `1554`
- Local `transcript_recommendation_events` rows observed now: `1554`

## Why X Is Excluded From Main Sample

- Historical X coverage is not sufficient for defensible final historical event-study inference.
- Readiness documentation marks X-only studies as blocked/future work and positions YouTube as the primary historical sample.
- Existing guidance treats any current X overlap as diagnostic rather than final-causal evidence.

## Why Apify Collection Stopped

- Controlled recovery did not add new transcripts or accepted events under tested provider/token pairs.
- The lock rationale states collection should stop absent new paid capacity or truly new provider paths.
- Capacity failures (credits/rental/provider-start constraints) made additional runs low expected value.

## What This Locked Sample Supports

- YouTube-only descriptive summaries of recommendations across creators, tickers, and time.
- Provisional yfinance-based event-study evidence with explicit non-causal framing.
- A Bloomberg handoff plan for final market-data quality and inference hardening.
