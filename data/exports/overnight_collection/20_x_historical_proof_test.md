# X Historical Proof Test

Generated: 2026-05-14T17:34:52Z

## Executive Conclusion

- Result: **FAIL**.
- Total actor runs started: 1.
- Total returned posts inspected in memory: 20.
- Valid historical posts inside requested windows: 0.
- Same-day/current-date collapse observed: yes.
- Stop reason: stopped because 2020 historical returned out-of-window/current-date results.

## Budget

- Starting known budget condition: existing `.env` exposes Apify token variables and project caps; no keys were added or modified.
- Per-run `maxTotalChargeUsd`: $0.2000.
- Planned hard ceiling for this proof: about $1.0000.
- Approximate spend reported by Apify run metadata: $0.0011.
- Stayed under about $1: yes.
- Apify manager safe summary: token_count=5, labels=['apify_main', 'apify_key_2', 'apify_key_3', 'apify_key_4', 'apify_key_5'], global_spend_from_local_ledger=0.26.

## Actor And Source Tested

- Actor: `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`.
- Source type: explicit cashtag search only.
- Max items per window: 10.
- Input fields used: `queries`, `maxItems`, `lang`, `startDate`, `endDate`.
- Date filters sent to actor: yes, via both query `since:`/`until:` syntax and actor-level date fields where supported by the selected actor schema.
- First run query sent: `$TSLA since:2020-08-01 until:2020-08-08 lang:en -filter:retweets` with `startDate=2020-08-01` and `endDate=2020-08-07`.
- Actor appeared to respect date filters: no / not proven.

## Window-By-Window Results

| Requested window | Query | Returned posts | Posts with raw timestamp | Posts with valid parsed timestamp | Posts inside requested window | Posts outside requested window | Explicit cashtag posts | Seed-universe ticker matches | Approx cost | Conclusion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2020-08-01 to 2020-08-07 | `$TSLA` | 20 | 20 | 20 | 0 | 20 | 0 | 0 | $0.0011 | FAIL: no parsed timestamps inside requested window |
| 2022-05-23 to 2022-05-30 | `$NVDA` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | $0.0000 | NOT_RUN |
| 2024-02-01 to 2024-02-07 | `$AAPL` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | $0.0000 | NOT_RUN |
| 2026-05-01 to 2026-05-13 | `$MSFT` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | $0.0000 | NOT_RUN |

## Timestamp Diagnosis

- Raw timestamp fields found: `createdAt`.
- Raw timestamp sample values: createdAt: ['Thu May 14 17:34:41 +0000 2026', 'Thu May 14 17:34:41 +0000 2026', 'Thu May 14 17:34:41 +0000 2026'].
- Parser behavior: existing `_normalize_created_at()` was used; ISO, epoch, and Twitter legacy dates normalize to UTC ISO, while relative/no-year dates are rejected.
- Parsed date range observed: 2026-05-14 to 2026-05-14.
- Dates collapsed to 2026-05-14/current-day-only: 2026-05-14.
- True historical timestamps exist in returned proof items: no.
- Actor returned 20 items despite `maxItems=10`; this reinforces that successful actor status is not enough to trust requested controls.
- Duplicate indicator: no duplicate IDs/URLs were observed within the returned proof batch.

## Ticker Diagnosis

- Explicit `$CASHTAG` post count: 0.
- Inferred uppercase ticker count after current extractor: 0.
- Accepted seed ticker count from strict cashtag filter: 0.
- False-positive examples after current suppression: none observed.

## Decision

- Is current Apify/X setup capable of historical collection? not proven.
- Can `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1` be set? no.
- Should we spend the new $10-$20 on X? no.
- Should X remain blocked/diagnostic-only? yes.
- Should we shift spend to YouTube transcripts instead? yes, YouTube transcripts are higher-value until X proof passes.

## Safety Notes

- `.env` was not modified.
- API keys were not printed.
- Raw Apify JSON was fetched only in memory for summary inspection and was not saved by this proof script.
- Full raw post text is intentionally omitted.
- DB tables were not written by this proof script.
