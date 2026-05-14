# X Recollection Strategy

Generated: 2026-05-14T16:50:00Z

## Decision

- Do not spend the remaining ~$7 now.
- Historical date filtering is not proven.
- The existing accessible DB/raw artifacts cannot salvage the overnight X run for historical analysis.
- More X collection remains blocked until a tiny proof run demonstrates that the actor returns actual historical timestamps and the strict ticker sample is credible.

## Tiny Historical Actor Test Plan

Budget cap: no more than $1 total, including all actors tested. Use very small per-run caps and stop early once a failure pattern is clear.

Required date-window test cases:

| Window | Purpose |
|---|---|
| 2020 or 2021 window | Proves old archive retrieval, not recent-only behavior. |
| 2022 or 2023 window | Tests mid-sample historical coverage. |
| 2024 or 2025 window | Tests recent historical coverage before the collection date. |
| Very recent window | Confirms the actor still returns expected current results. |

Recommended windows:

| Test | Example date range | Example source |
|---|---|---|
| Old | 2020-07-01 to 2020-07-07 | one high-volume cashtag such as `$TSLA` |
| Middle | 2022-11-01 to 2022-11-07 | one likely creator profile and one cashtag |
| Recent historical | 2024-08-01 to 2024-08-07 | one likely creator profile and one cashtag |
| Very recent | 2026-05-01 to 2026-05-07 | same actor/source pattern |

## Required Proof

Before spending more than the $1 test cap, each successful actor/source/window must produce:

- raw item JSON with explicit timestamp fields such as `created_at`, `createdAt`, `createdAtIso`, `date`, or `timestamp`;
- timestamps with explicit years, not relative strings like `2h` or no-year strings like `May 14`;
- parsed UTC ISO `created_at` values inside the requested window;
- post-import date coverage spanning the requested historical windows, not just 2026-05-14;
- strict `$CASHTAG`-only seed-universe event counts after uppercase false-positive suppression;
- source-level finance relevance and duplicate-rate diagnostics.

## Actor Choice

- The current selected actor, `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`, can be included in the $1 proof test, but it must not be trusted based on successful run status alone.
- Try a different Apify actor if the selected actor returns same-day/current results for old windows, ignores `startDate`/`endDate`, or emits unparseable/relative dates.
- `scraper_one/x-profile-posts-scraper` should only be retested with `profileUrls`, because the earlier profile input used the wrong field.

## Official X API Consideration

Official X API full-archive search is worth considering if the project can obtain appropriate access. The local count-error payloads show full-archive count requests returning access unavailable/403 in this environment, so it is not currently available as a turnkey replacement. If access is granted, it is methodologically cleaner than unverified scraping actors because date-window semantics and timestamp fields are explicit.

## Minimum Viable X Dataset For The Final Paper

A final-paper X extension should have at least:

- verified historical date coverage across 2020-01-01 through 2026-05-13, or a clearly documented narrower historical window;
- explicit `$CASHTAG` seed-universe events only;
- enough strict events for descriptive tables by year and ticker after excluding market controls and broad search noise;
- separate source buckets for verified/likely creator profiles, market-control accounts, and cashtag/search attention sources;
- documented duplicate rate, actor failure rate, and ticker precision diagnostics;
- no raw X text in committed outputs.

## Exact Gate For `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1`

Set `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1` only after the $1 test produces successful, raw-inspected, parsed-in-window results in all four required date windows, with at least one older window before 2022 and no same-day-only collapse.

## Exact Gate For Spending The Remaining ~$7

Spend the remaining ~$7 only if:

- historical filtering is proven in raw and parsed fields;
- strict ticker filtering produces a credible nontrivial sample;
- duplicate rate remains close to the prior 0.46% baseline and does not rise materially;
- source relevance is acceptable after separating creator, market-control, and search sources;
- the continuation plan is updated with a hard cap no higher than $25 total X spend;
- the run uses checkpoints after each ~$1 of additional spend;
- a human intentionally authorizes the continuation after reviewing the proof.

## Stop Conditions

Stop immediately if any of these occur:

- duplicate rate rises materially;
- finance relevance deteriorates;
- classifier false positives dominate strict events;
- Apify costs exceed the approved cap;
- actor failures repeat;
- returned dates do not match requested historical windows;
- raw timestamps are relative/no-year strings or cannot be UTC-normalized;
- source mix becomes mostly broad search/control attention rather than creator recommendation evidence.
