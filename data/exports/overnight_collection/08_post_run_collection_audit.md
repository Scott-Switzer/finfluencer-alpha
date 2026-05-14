# Post-Run Collection Audit

Generated: 2026-05-14T15:57:09Z

## Collection Outcome
- Final X posts imported: 6,936
- Final X ticker mentions: 5,605
- Final X recommendation events: 1,462
- Final Apify collection runs: 317
- Total spend from apify_collection_runs: $17.9563
- Duplicates: 32
- Duplicate rate: 0.46%
- Cost per imported item: $0.0026
- Configured X target: 50,000
- Target reached: no
- Remaining to target: 43,064

## Spend By Key

| Key Label | Runs | Imported | Duplicates | Spend |
|---|---:|---:|---:|---:|
| apify_key_2 | 63 | 1443 | 0 | $3.6647 |
| apify_key_3 | 63 | 1374 | 32 | $3.6050 |
| apify_key_4 | 62 | 1314 | 0 | $3.4597 |
| apify_key_5 | 64 | 1389 | 0 | $3.6058 |
| apify_main | 65 | 1416 | 0 | $3.6209 |

## Recent Actor Success/Failure Status

| Actor | Status | Runs | Imported | Duplicates | Cost | Last Finished |
|---|---|---:|---:|---:|---:|---|
| kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest | SUCCEEDED | 317 | 6936 | 32 | $17.9563 | 2026-05-14T05:57:40Z |

## Ledger Status
- X collection ledger rows: 308
- Ledger status counts: {'SUCCEEDED': 305, 'FAILED': 2, 'budget_exhausted': 1}
- Ledger source type counts: {'profile': 135, 'cashtag': 132, 'search': 40, '': 1}
- Last ledger row status: budget_exhausted
- Last ledger row source: /

## Target And Resume Assessment
- Whether the 50,000 target was reached: no
- Why it was not reached: the X cost cap was reached before the configured post target. The stop was budget-driven, not a dedupe or schema failure.
- Whether collection can safely resume: yes_with_new_explicit_budget_and_checkpoint. Do not resume without a new manual checkpoint, fresh budget cap, and source-quality review.
- Whether more collection is worth it: not now; audit quality and run event studies first. The current sample is already large enough for exploratory X-only and YouTube+X overlap analysis; additional spend should be justified by source-quality gaps.
- Whether event studies can proceed: yes, exploratory event-study construction can proceed after this reporting fix; final conclusions still require quality checks.

## Crash Explanation
- The overnight pipeline crashed after collection in `build_event_study_placeholders()` because it grouped returns by `benchmark_ticker`.
- The audited returns file is wide-format and contains `abnormal_return_SPY`, `abnormal_return_QQQ`, and `abnormal_return_IWM`, but does not contain a long-format `benchmark_ticker` column.
- The crash did not affect the imported X posts, ticker mentions, recommendation events, or Apify collection ledger.

## Exact Fix Applied
- Added `_normalize_event_returns_for_summary()` to convert long-format returns or wide `abnormal_return_*` columns into a safe summary input.
- Added `_safe_event_window_summary()` so missing optional columns produce audit warnings and empty/partial summaries instead of crashing.
- Added `_safe_group_count()` so missing optional integrated-table columns produce empty grouped outputs plus warnings.
- Added regression tests for missing `benchmark_ticker`, empty returns, and normal long-format returns with `benchmark_ticker`.

## Guardrails
- No collection was restarted for this audit.
- No Apify calls were made for this audit.
- Raw X data, DB files, logs, secrets, caches, and backups should not be committed.
