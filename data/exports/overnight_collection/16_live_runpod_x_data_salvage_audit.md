# Live RunPod X Data Salvage Audit

Generated: 2026-05-14T16:50:00Z

## Scope And Access Check

- Requested DB path in the prompt: `/workspace/FIN496CAPSTONE/data/finfluencer_alpha.db`.
- Accessible DB path in this Codex session: `data/finfluencer_alpha.db` in `/Users/scottthomasswitzer/Desktop/FIN496CAPSTONE`.
- `/workspace/FIN496CAPSTONE` is not mounted in this session.
- The accessible DB was inspected read-only for this audit; no raw data was mutated and no Apify calls were made.
- Conclusion on access: the populated live RunPod X DB described in the prompt is not available in this session. This audit validates the accessible DB and the committed/local generated artifacts, and treats the live salvage question as unproven until the populated RunPod DB or raw Apify item JSON is supplied.

## DB Table Inventory

| Table | Exists in accessible DB | Rows |
|---|---:|---:|
| `x_posts` | no | not present |
| `x_post_ticker_mentions` | no | not present |
| `x_recommendation_events` | no | not present |
| `raw_x_posts` | yes | 0 |
| legacy `ticker_mentions` where platform=`x` | yes | 0 |
| legacy `recommendation_candidates` where platform=`x` | yes | 0 |

## `x_posts` Columns

The `x_posts` table does not exist in the accessible DB, so no live `x_posts` columns can be inspected here. The code schema expects these columns when `apply_x_youtube_schema()` has been run:

`post_id`, `author_handle`, `author_name`, `author_id`, `text`, `created_at`, `url`, `like_count`, `repost_count`, `reply_count`, `quote_count`, `view_count`, `language`, `scraped_at`, `apify_actor`, `apify_key_label`, `source_query`, `source_type`, `raw_json_path`, `normalized_text_hash`.

## Raw Timestamp Field Inventory

Accessible DB `raw_x_posts` columns:

| Column | Type | Timestamp/date role |
|---|---|---|
| `post_id` | `TEXT` | not a timestamp field |
| `creator_handle` | `TEXT` | not a timestamp field |
| `author_id` | `TEXT` | not a timestamp field |
| `created_at` | `TEXT` | raw/imported post timestamp |
| `text` | `TEXT` | not a timestamp field |
| `lang` | `TEXT` | not a timestamp field |
| `like_count` | `INTEGER` | not a timestamp field |
| `repost_count` | `INTEGER` | not a timestamp field |
| `reply_count` | `INTEGER` | not a timestamp field |
| `quote_count` | `INTEGER` | not a timestamp field |
| `impression_count` | `INTEGER` | not a timestamp field |
| `url` | `TEXT` | not a timestamp field |
| `raw_json` | `TEXT` | may contain raw post fields, but there are 0 rows here |
| `collected_at` | `TEXT` | import time |

Importer raw item timestamp paths, in order: `created_at`, `createdAt`, `createdAtIso`, `date`, `timestamp`.

Local raw artifact inventory:

| Artifact area | Files | Timestamp usefulness |
|---|---:|---|
| `data/raw/apify/x/**/*.json` | 0 | Expected raw Apify item JSON; absent here. |
| `data/raw/x_posts/**/*.json` | 0 | No raw X post JSON files present. |
| `data/raw/x/counts/*.json` | 220 | Official X count-request error payloads; include request `start_time`/`end_time`, not post timestamps. |

## Sample Timestamp Values

No sample X post timestamps can be shown from the accessible DB because `x_posts` is absent and `raw_x_posts` has 0 rows. The only local X JSON files are count-error payloads, whose date fields are request windows rather than returned post timestamps, for example historical count requests around `2020-01-01T00:00:00Z` to `2020-02-01T00:00:00Z` that returned `403 Forbidden`/access unavailable.

## Prior Committed Audit Evidence

| Metric from committed audit markdown | Value |
|---|---:|
| X posts | 6,936 |
| X ticker mentions | 5,605 |
| X recommendation events | 1,462 |
| Apify collection runs | 317 |
| Spend | $17.9563 |
| Duplicate rate | 0.46% |
| Parsed X date coverage | 2026-05-14 to 2026-05-14 across 1 calendar day |
| Mentions in seed universe | 629 of 5,605 (11.2%) |
| Recommendation events in seed universe | 46 of 1,462 (3.1%) |

The committed audit evidence is enough to block final X event studies, but it is not enough to salvage the raw data because the raw item timestamps are not present here.

## Parsed Timestamp Validation Results

| Validation target | Result |
|---|---|
| Accessible `x_posts.created_at` coverage | Not computable; `x_posts` absent. |
| Accessible `raw_x_posts.created_at` coverage | Not computable; 0 rows. |
| Historical dates before 2026-05-14 in accessible DB | 0 observed. |
| True historical dates in raw/imported X post fields | Not proven; raw Apify item JSON is absent. |
| Prior committed parsed coverage | Same-day only: 2026-05-14 to 2026-05-14 across 1 calendar day. |

## Cause Assessment

The exact root cause cannot be proven from this accessible checkout because the populated `x_posts` table and raw Apify item JSON are unavailable. The plausible failure modes remain:

- actor/date filter not honored by `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`;
- actor returned relative or no-year display dates that the old importer accepted instead of rejecting;
- source/search design favored latest results despite historical `since:`/`until:` query syntax;
- selected actor lacks reliable historical support for these inputs.

Current evidence does not support calling this only a parser bug. It should be treated as actor/source/date-support unproven until raw timestamps prove otherwise.

## Strict Diagnostic X Sample Rebuild

Using existing accessible data only:

| Strict filter count | Result |
|---|---:|
| Total X posts in accessible `x_posts` | not present |
| Total X posts in accessible legacy `raw_x_posts` | 0 |
| Posts with valid parsed timestamps | 0 |
| Posts with historical dates before 2026-05-14 | 0 |
| Posts with explicit cashtags | 0 |
| Posts matching configured seed universe | 0 |
| Strict X recommendation events after filters | 0 |
| Strict events by source type | none |
| Strict events by ticker | none |
| Strict events by date range | none |

This is not evidence that the overnight run had zero strict events; it is evidence that the live populated X rows needed to rebuild the strict sample are not available in this session. The prior unfiltered audit reported only 46 of 1,462 seed-universe matches, and explicit `$CASHTAG` strict counts still require the populated DB/raw items.

## Salvage Decision

- Current X data is not salvageable from the accessible checkout.
- True historical timestamps are not proven.
- Same-day-only coverage remains a blocking quality failure for final historical event-study claims.
- X-only event studies are blocked for final inference and allowed only as explicitly labeled diagnostics if a same-day diagnostic override is set.
- More Apify collection should remain blocked.

## Exact Proof Required Before `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1`

1. Run a capped historical actor test outside the final collection path.
2. Save raw item JSON locally for inspection, but do not commit it.
3. For each requested historical window, show raw item timestamp fields with explicit years and UTC-normalizable values.
4. Prove parsed `created_at` dates fall inside each requested window after import.
5. Rebuild strict `$CASHTAG`-only, seed-universe-filtered events and show nontrivial counts by source, ticker, and date.
6. Confirm duplicate rate, finance relevance, and classifier precision are acceptable before spending beyond the test cap.
7. Only then set `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1` intentionally for a bounded continuation.
