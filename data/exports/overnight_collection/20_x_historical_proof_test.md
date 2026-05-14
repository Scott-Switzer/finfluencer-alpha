# X Historical Proof Test

Generated: 2026-05-14T17:34:52Z

**Status update (2026-05-14, multi-window confirmation):** The executive conclusion in the next section describes the **pre-schema-fix** proof that used deprecated query fields. The authoritative result for historical date filtering is under **Multi-window confirmation test** near the end of this document.

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

## Follow-up schema diagnosis

Generated: 2026-05-14T17:53:25Z

### Live schema findings

- Actor inspected: `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`.
- Schema source: Apify actor OpenAPI page, because the direct `/input-schema` API endpoint returned 404 while the actor metadata and OpenAPI definition were available.
- Pricing shown by Apify: `$0.25 / 1,000 tweets`; actor metadata also reports `PRICE_PER_DATASET_ITEM` / pay-per-event pricing at `$0.00025` per tweet.
- Exact accepted input field names found in the OpenAPI input schema:
  - `tweetIDs`
  - `twitterContent`
  - `searchTerms`
  - `maxItems`
  - `queryType`
  - `lang`
  - `from`
  - `to`
  - `@`
  - `list`
  - `filter:blue_verified`
  - `near`
  - `within`
  - `geocode`
  - `since_time`
  - `until_time`
  - `since_id`
  - `max_id`
  - `filter:nativeretweets`
  - `include:nativeretweets`
  - `filter:replies`
  - `conversation_id`
  - `filter:quote`
  - `quoted_tweet_id`
  - `quoted_user_id`
  - `card_name`
  - `filter:has_engagement`
  - `min_retweets`
  - `min_faves`
  - `min_replies`
  - `-min_retweets`
  - `-min_faves`
  - `-min_replies`
  - `filter:media`
  - `filter:twimg`
  - `filter:images`
  - `filter:videos`
  - `filter:native_video`
  - `filter:vine`
  - `filter:consumer_video`
  - `filter:pro_video`
  - `filter:spaces`
  - `filter:links`
  - `filter:mentions`
  - `filter:news`
  - `filter:safe`
  - `filter:hashtags`
  - `url`
- Fields of interest:
  - `since_time`: present.
  - `until_time`: present.
  - `searchTerms`: present.
  - `twitterContent`: present.
  - `maxItems`: present; schema minimum is `1`, but the description says the practical minimum is `20` and the returned count can exceed the requested count.
  - `queryType`: present; accepted values include `Latest`, `Top`, `Photos`, `Videos`.
  - `lang`: present.
  - `query`, `queries`, `keywords`, `sort`, `language`, `startDate`, `endDate`: not present in the live schema.
- Documentation warning found: the actor README change log says `since` / `until` filters are no longer reliable and recommends `since_time` / `until_time` UNIX timestamps instead. It also warns pagination is unreliable and recommends smaller time windows.

### Kaito UNIX timestamp proof

- Test input fields used: `searchTerms`, `maxItems`, `queryType`, `lang`, `since_time`, `until_time`.
- Query string used: `$TSLA since_time:1596240000 until_time:1596844799`.
- Actor-level timestamp fields used: `since_time=1596240000`, `until_time=1596844799`.
- Requested UTC window: `2020-08-01 00:00:00` through `2020-08-07 23:59:59`.
- Max items requested: `20`.
- Per-run `maxTotalChargeUsd`: `$0.0500`.
- Returned count: `20`.
- Raw timestamp field names present: `createdAt`.
- Parsed timestamps:
  - `2020-08-07T23:58:01Z`
  - `2020-08-07T23:56:44Z`
  - `2020-08-07T23:56:27Z`
  - `2020-08-07T23:53:58Z`
  - `2020-08-07T23:53:35Z`
  - `2020-08-07T23:52:59Z`
  - `2020-08-07T23:51:12Z`
  - `2020-08-07T23:51:12Z`
  - `2020-08-07T23:49:40Z`
  - `2020-08-07T23:46:29Z`
  - `2020-08-07T23:46:26Z`
  - `2020-08-07T23:44:09Z`
  - `2020-08-07T23:41:08Z`
  - `2020-08-07T23:40:16Z`
  - `2020-08-07T23:39:49Z`
  - `2020-08-07T23:38:39Z`
  - `2020-08-07T23:37:21Z`
  - `2020-08-07T23:34:55Z`
  - `2020-08-07T23:31:17Z`
  - `2020-08-07T23:30:42Z`
- Number inside requested window: `20`.
- Number outside requested window: `0`.
- Number with explicit `$TSLA`: `20`.
- Number with extracted `TSLA`: `20`.
- Dates collapsed to 2026-05-14/current day: no.
- Result: **PASS for this single Kaito historical window using UNIX timestamp filters**.

### Follow-up decision

- Literal `since:2020-08-01 until:2020-08-07` advanced-search query test: not run because the UNIX timestamp test passed.
- Alternative actor smoke test: not run because the same Kaito actor passed with the corrected schema.
- Code patch decision: patch repo Kaito input construction to use `searchTerms` plus UNIX `since_time` / `until_time`, and remove the previous Kaito `queries` / `startDate` / `endDate` path.
- Can `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1` be set now: no. This is one passing historical window only; require at least three different historical windows before setting the proof flag. **Update:** the multi-window section below satisfies that multi-window date-filter bar; setting the env flag remains a manual operator decision after ledger and budget review.
- Broad X collection decision: do not run broad collection yet.
- New API keys needed: no.
- Follow-up spend estimate: Apify run metadata reported `$0`; at listed pricing, 20 returned tweets imply about `$0.005`, well under the `$1` follow-up ceiling.

## Multi-window confirmation test

Generated: 2026-05-14T18:07:00Z

Environment: RunPod `/workspace/FIN496CAPSTONE`, branch `x-youtube-full-research-expansion`, commit `518ce27` (post-`git pull`). Apify token presence: `APIFY_API_TOKEN` absent, `APIFY_TOKEN` present (values not logged). Raw Apify JSON was held in memory only for this confirmation; nothing from this batch was committed as raw payload files.

### 1. Summary conclusion

- Result: **PASS** (conservative historical-date criterion).
- Rationale: The prior **2020-08-01 to 2020-08-07 `$TSLA`** Kaito window already passed with `searchTerms` plus actor-level `since_time` / `until_time` (documented above). This session adds **three additional disjoint historical windows** (`$NVDA` 2022-05, `$AAPL` 2024-02, `$MSFT` 2026-05). For each core window, all returned items carried **valid parsed timestamps inside the requested UTC bounds**, with **no current-day collapse** relative to the run date (2026-05-14 UTC), and **explicit seed cashtags on every returned tweet**. Optional `$GME` 2021-01 stress window: `19` posts normalized (one item lacked a usable timestamp row after normalization); treat as diagnostic only, not required for the three-window rule.
- First-mention ticker extraction nuance: a quick strict count using only the **first** `extract_x_ticker_mentions()` hit under-counts multi-ticker posts. A follow-up **dataset re-read** (no new actor charges) confirmed **`any`-mention seed ticker match = 20 / 20 / 20 / 19** for NVDA / AAPL / MSFT / GME respectively. This is a **ranking / extraction presentation** issue, not evidence that Kaito ignored `since_time` / `until_time`.

### 2. Window-by-window table

| Query | Requested UTC window | since_time | until_time | Returned posts | Valid parsed timestamps | Inside-window posts | Outside-window posts | Explicit cashtag posts | Strict first-hit extracted ticker matches | Any-mention seed ticker matches | Same-day / current-day collapse | Result |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `$NVDA` | 2022-05-23 00:00:00 UTC through 2022-05-30 23:59:59 UTC | 1653264000 | 1653955199 | 20 | 20 | 20 | 0 | 20 | 7 | 20 | no | **PASS** (historical bounds) |
| `$AAPL` | 2024-02-01 00:00:00 UTC through 2024-02-07 23:59:59 UTC | 1706745600 | 1707350399 | 20 | 20 | 20 | 0 | 20 | 20 | 20 | no | **PASS** |
| `$MSFT` | 2026-05-01 00:00:00 UTC through 2026-05-13 23:59:59 UTC | 1777593600 | 1778716799 | 20 | 20 | 20 | 0 | 20 | 14 | 20 | no | **PASS** (historical bounds) |
| `$GME` (optional) | 2021-01-25 00:00:00 UTC through 2021-01-31 23:59:59 UTC | 1611532800 | 1612137599 | 20 | 19 | 19 | 0 | 19 | 5 | 19 | no | **PARTIAL** (optional only; one post not normalized) |

Actor input construction matched `build_x_actor_input()` for Kaito: `searchTerms` (cashtag + `lang:en -filter:retweets` + embedded `since_time` / `until_time` in the query string per existing helper), top-level `since_time` / `until_time` as strings, `maxItems`, `queryType`, `lang`. Disallowed fields (`query`, `queries`, `keywords`, `startDate`, `endDate`, `since`, `until`, `language`, `sort`) were not used as actor input keys.

### 3. Timestamp diagnosis

- **Kaito vs. `since_time` / `until_time`:** Across NVDA, AAPL, MSFT, and GME batches, parsed `createdAt` values stayed strictly inside the UNIX window implied by the requested calendar span. Min/max UTC by window (from normalized posts): NVDA `2022-05-30T22:55:52Z` to `2022-05-30T23:58:49Z`; AAPL `2024-02-07T23:19:53Z` to `2024-02-07T23:59:12Z`; MSFT `2026-05-13T23:30:36Z` to `2026-05-13T23:58:59Z`; GME `2021-01-31T23:58:05Z` to `2021-01-31T23:59:56Z` (19-parse subset). This pattern is consistent with **Latest-query ordering up against the `until_time` bound**, not with “everything is today.”
- **Current-day collapse:** None observed for these windows on run date 2026-05-14 UTC (no mass assignment to 2026-05-14 while claiming historical ranges).

### 4. Ticker diagnosis

- **Explicit cashtag posts:** 20 / 20 / 20 for the three required windows; 19 / 20 for optional GME (aligned with parseable rows).
- **Extracted ticker posts:** Strict “first extracted mention equals seed” under-counts when multiple tickers appear; **any-mention seed match** counts are the better fit for “does the tweet actually discuss the seed cashtag search?” and were 20 / 20 / 20 / 19 respectively (dataset re-read, no new scrapes).
- **False positives for date filtering:** No evidence of systematic out-of-window timestamps in these samples. This is **not** a claim of tradable alpha or human-labeled recommendation quality.

### 5. Decision

- **Kaito historical collection with corrected UNIX fields:** Supported by **four** independent passes: legacy `$TSLA` 2020 window (above) plus three new windows in this section.
- **Repo actor input construction:** Matches the live Kaito schema expectations documented in the follow-up schema section (`searchTerms`, `since_time`, `until_time`, `maxItems`, optional `queryType` / `lang` / `twitterContent` only when required).
- **`X_APIFY_HISTORICAL_DATE_FILTER_PROVEN`:** Do **not** flip automatically in code. After you review this audit, you may set `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN=1` intentionally in `.env` if you accept that operational gates (budget caps, ledger headroom on RunPod) remain binding.
- **New API keys:** Not required for this milestone.
- **Targeted ~$5 X expansion:** Conditionally justified **only** with hard per-run `maxTotalChargeUsd`, explicit cashtag queries, narrow event windows, checkpoints every ~$1, and **no** raw X payloads committed. See `24_targeted_x_collection_plan_after_proof.md`. Spend for this confirmation batch was approximately **`$0.013`** aggregate Apify usage (sum of run metadata costs for the four calls), well under the `$1` ceiling.

This section is descriptive audit evidence only. It does **not** authorize broad overnight scraping, causal marketing claims, or final X-only inference prior to a post-collection quality audit.
