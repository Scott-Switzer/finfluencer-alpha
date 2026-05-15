# YouTube-Only Pivot Methodology

## Why X is excluded from the main historical sample

Historical X/Twitter collection is currently excluded from the main empirical sample.  
In repeated capped probes, candidate Apify actors either required manual full-permission approval, returned no usable historical rows, or failed strict importability checks.

Because the active `APIFY_TOKEN_N` slots are tied to multiple accounts and cannot be reliably approved on demand, the X historical path is not reproducible enough for the primary FIN 496 design.

## Primary event source for the study

The main historical event source is now:

- YouTube videos
- with transcript-backed recommendation evidence
- mapped to ticker/company mentions
- and classified into auditable recommendation candidate windows

This keeps the empirical question intact:

> Do finfluencer recommendations generate abnormal/excess returns, or do they mainly amplify attention to already-moving stocks?

## Data governance and reproducibility constraints

- Full transcript text remains local-only (SQLite and ignored raw paths).
- Committed outputs should contain derived variables, counts, confidence flags, and short evidence windows.
- Raw provider payloads, raw transcript dumps, secrets, and account credentials are never committed.

## Market-data caveat

- yfinance-based return outputs remain provisional for development and setup checks.
- Bloomberg (or equivalent licensed institutional feed) is the preferred/final market-data layer for the final event-study estimates.

## Practical implication for overnight jobs

- Do not launch broad X historical collection in the core pipeline unless a provider later achieves strict research validation under reproducible account constraints.
- Optimize overnight spend for accepted transcript-backed recommendation events per dollar, not raw transcript volume.
