# X Date Parsing And Actor Input Audit

Generated: 2026-05-14T17:30:00Z

## Scope

- Repo commit audited: `1127dc178d0eb498a9fce58098b895d638c3328e`.
- Selected actor from `selected_x_actor.txt`: `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`.
- Existing RunPod audit counts from `10_x_source_classifier_quality_audit.md`: 6,936 X posts, 5,605 ticker mentions, 1,462 X recommendation events, 317 Apify runs, $17.9563 spend.
- Local limitation: the transferred checkout contains the audit markdown/ledgers, but not the RunPod `x_posts` table or raw `data/raw/apify/x` item JSON. The local SQLite DB has only the older `raw_x_posts` table with 0 rows. Exact raw timestamp value samples must be recomputed on the RunPod DB/raw files before any salvage decision is final.

## X Source Configuration

| Source list | Rows | Collection role |
|---|---:|---|
| `config/x_sources/profiles_verified.txt` | 0 | verified creator profiles |
| `config/x_sources/profiles_likely.txt` | 15 | likely creator/X-native finance profiles |
| `config/x_sources/market_control_accounts.txt` | 13 | market/news/control attention sources |
| `config/x_sources/cashtags.txt` | 33 | configured seed cashtag universe |
| `config/x_sources/search_queries.txt` | 10 | broad cashtag/search expansion queries |
| `config/x_sources/profiles_unverified_candidates.txt` | 29 | explicitly excluded from main high-spend profile collection |

Observed RunPod source mix:

| Source bucket | Posts |
|---|---:|
| verified creator profiles | 0 |
| likely profiles | 1,635 |
| market-control posts | 1,394 |
| cashtag/search posts | 3,907 |

## Actor Input Schema Used

The source query builder sent both query-level date syntax and actor-level date fields.

For profile sources:

```json
{
  "queries": [
    "from:<handle> since:2020-01-01 until:2026-05-14 lang:en -filter:retweets"
  ],
  "maxItems": 250,
  "lang": "en",
  "startDate": "2020-01-01",
  "endDate": "2026-05-13"
}
```

For cashtag sources:

```json
{
  "queries": [
    "$TSLA since:2020-01-01 until:2026-05-14 lang:en -filter:retweets"
  ],
  "maxItems": 250,
  "lang": "en",
  "startDate": "2020-01-01",
  "endDate": "2026-05-13"
}
```

For search sources, the same `queries`, `maxItems`, `lang`, `startDate`, and `endDate` keys were used with the configured boolean search string plus `since:`/`until:`.

Other actor branches inspected:

| Actor | Payload date keys | Bakeoff result |
|---|---|---|
| `apidojo/tweet-scraper` | `start`, `end` plus query `since:`/`until:` | Failed with input/charge validation. Its configured input did not prove schema compatibility. |
| `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest` | `startDate`, `endDate` plus query `since:`/`until:` | Succeeded, but returned same-day parsed coverage only. |
| `scraper-engine/twitter-x-posts-scraper` | `startDate`, `endDate` plus query `since:`/`until:` | Not evaluated for date support because actor rental failed. |
| `scraper_one/x-profile-posts-scraper` | previously `usernames`, now fixed to `profileUrls`; date fields remain `startDate`, `endDate` | Bakeoff showed the previous profile field name was wrong. Date support is still unproven. |

## Date Fields Sent To The Selected Actor

- Query string lower bound: `since:2020-01-01`.
- Query string upper bound: `until:2026-05-14`.
- Actor payload lower bound: `startDate: 2020-01-01`.
- Actor payload upper bound: `endDate: 2026-05-13`.

The selected actor accepted the run payload syntactically because runs succeeded. Acceptance is not evidence that `startDate` and `endDate` were honored. The resulting parsed coverage shows they were ineffective for the intended historical window.

## Raw Timestamp Column Inventory

The importer searched these raw item paths for post timestamps, in order:

1. `created_at`
2. `createdAt`
3. `createdAtIso`
4. `date`
5. `timestamp`

The local checkout does not include the RunPod raw Apify item JSON, so exact raw value examples cannot be sampled here without the excluded raw files.

## Parsed Timestamp Column Inventory

| Table | Column | Meaning | Prior behavior |
|---|---|---|---|
| `x_posts` | `created_at` | normalized/imported post timestamp | accepted any non-empty timestamp text, including non-ISO/no-year strings |
| `x_recommendation_events` | `event_datetime` | copied from `x_posts.created_at` | inherited any raw timestamp issue |
| `x_recommendation_events` | `event_date` | first 10 chars of `event_datetime` | unsafe when `event_datetime` was not ISO-normalized |

## Date Collapse Finding

The RunPod audit reported parsed X post date coverage of `2026-05-14` to `2026-05-14`, across one calendar day, instead of the intended `2020-01-01` to `2026-05-13`.

Exact reason:

- The selected actor was run with `startDate`/`endDate` and query `since:`/`until:` filters, but the returned/imported records did not cover the requested historical date range.
- The pipeline did not validate post-import date coverage before building recommendation events or event-study inputs.
- The old timestamp normalizer returned arbitrary timestamp strings unchanged. If an actor returned relative or no-year display dates, downstream parsing could collapse them to the collection date/current year instead of rejecting them.
- Because the transferred checkout lacks RunPod raw item JSON, this audit cannot prove whether true historical dates exist in unparsed raw fields. The observed committed evidence is sufficient to conclude the current imported X events are not historical.

## Salvage Assessment

- Existing imported X recommendation events cannot be used for final historical event studies.
- They can only be used as same-day diagnostic examples, and only when explicitly marked diagnostic.
- Salvage is possible only if the RunPod raw Apify files contain explicit historical timestamp fields that were ignored or parsed incorrectly. That must be verified from raw item JSON before reimport.
- If raw files contain only same-day/current tweets, the data are not salvageable for historical analysis.

## Required Strategy Before More X Collection

- Do not resume Apify collection until a short proof run demonstrates that the selected actor, or a replacement actor, returns explicit historical timestamps across known old dates.
- Require actor input schema proof, not just successful run status.
- Require post-import validation that parsed `created_at` spans the requested historical window.
- Reject no-year and relative date strings during import.
- Keep the current actor/source outputs out of final event studies unless a diagnostic override is explicitly set.

## Fixes Added In This Pass

- Timestamp normalization now converts explicit ISO, epoch, and Twitter legacy timestamps to UTC ISO.
- Timestamp normalization rejects no-year/relative display dates such as `May 14` or `2h`.
- X collection is blocked unless `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1` is set after external proof.
- X event-study output construction refuses same-day-only X date coverage unless `X_ALLOW_DIAGNOSTIC_SAME_DAY_EVENT_STUDY=1` is set.
- `scraper_one/x-profile-posts-scraper` profile payload construction now uses `profileUrls`, matching the bakeoff validation error.
