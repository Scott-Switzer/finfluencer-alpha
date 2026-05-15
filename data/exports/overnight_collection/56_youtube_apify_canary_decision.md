# YouTube Apify canary decision

Generated (UTC): `2026-05-15T01:30:00Z`

- Selected provider: `supreme_coder/youtube-transcript-scraper`
- Canary command executed: `RUN_YOUTUBE_APIFY_TRANSCRIPT_CANARY=1 ... YOUTUBE_APIFY_CANARY_MAX_VIDEOS=10 ...`
- Result: `FAIL`
- Overnight allowed: `no`

## Exact failure reason

The provider run failed at actor start with schema validation:

- `HTTP 400 invalid-input`
- Message: `Field input.urls is required`

This is a provider-input schema mismatch in the current adapter path for `supreme_coder/youtube-transcript-scraper`.

## Failure category

- Primary category: `schema`
- Not observed as auth failure, spend overrun, queue failure, or transcript import duplication.

## Canary outcome details

- Videos targeted from queue: `10`
- Successful transcripts imported: `0`
- Failure counts by type:
  - `SchemaMismatch`: `1` run-level start failure
  - `TranscriptNotFound`: `0`
  - `AgeRestricted`: `0`
  - `VideoUnavailable`: `0`
  - `IpBlocked`: `0`
  - `Timeout`: `0`
  - `EmptyTranscript`: `0`
  - `UnknownError`: `0`
- Observed spend: `0.00 USD` (no new youtube rows recorded in `apify_key_usage_ledger.csv`)

## Decision: fix adapter or switch provider

Recommended immediate path: `switch provider for next canary` to unblock collection, because `curious_coder/youtube-transcript-scraper` has prior success in repo history.

Secondary follow-up: patch `supreme_coder` input builder in `apify_transcripts.py` to include `urls` schema field and re-test later.

## Exact next corrective command

```bash
RUN_YOUTUBE_APIFY_TRANSCRIPT_CANARY=1 \
YOUTUBE_APIFY_SELECTED_PROVIDER="curious_coder/youtube-transcript-scraper" \
YOUTUBE_APIFY_CANARY_MAX_VIDEOS=10 \
YOUTUBE_APIFY_CANARY_CAP_USD=0.10 \
python scripts/canary_youtube_apify_transcript_provider.py
```
