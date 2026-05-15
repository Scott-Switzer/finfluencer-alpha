# YouTube credit-exhaustion runbook

Generated (UTC): `2026-05-15T01:35:30Z`

## Canary status

- Provider: `supreme_coder/youtube-transcript-scraper`
- Canary result: `PASS`
- Videos attempted: `10`
- Transcripts imported: `9`
- Observed spend: `0.0055 USD`
- Observed success rate: `0.90`
- Overnight eligibility: `allowed`

## Expanded queue status

- Queue build mode: `exhaustive`
- Config used: `YOUTUBE_TRANSCRIPT_QUEUE_MAX_ROWS=50000`
- Current queued rows: `5196`

## Recommended next step (safer first full run)

Run a capped larger batch first, validate quality and success rate, then move to exhaustion mode.

```bash
RUN_YOUTUBE_APIFY_OVERNIGHT=1 \
YOUTUBE_APIFY_SELECTED_PROVIDER="supreme_coder/youtube-transcript-scraper" \
YOUTUBE_APIFY_TARGET_SPEND_USD=2.00 \
YOUTUBE_APIFY_MAX_TOTAL_SPEND_USD=2.50 \
YOUTUBE_APIFY_BATCH_SIZE=100 \
YOUTUBE_APIFY_MAX_VIDEOS=5000 \
YOUTUBE_APIFY_MIN_REMAINING_USD_PER_TOKEN=0.05 \
YOUTUBE_APIFY_STOP_ON_LOW_SUCCESS_RATE=1 \
YOUTUBE_APIFY_SUCCESS_RATE_FLOOR=0.10 \
YOUTUBE_APIFY_ACCEPTED_EVENT_RATE_FLOOR=0.00 \
python scripts/run_youtube_apify_transcript_overnight.py
```

## Exhaustion-mode command (after successful capped full run)

```bash
RUN_YOUTUBE_APIFY_OVERNIGHT=1 \
YOUTUBE_APIFY_EXHAUST_ALL_KEYS=1 \
YOUTUBE_APIFY_STOP_WHEN_ALL_KEYS_EXHAUSTED=1 \
YOUTUBE_APIFY_SELECTED_PROVIDER="supreme_coder/youtube-transcript-scraper" \
YOUTUBE_APIFY_TARGET_SPEND_USD=9999 \
YOUTUBE_APIFY_MAX_TOTAL_SPEND_USD=9999 \
YOUTUBE_APIFY_BATCH_SIZE=100 \
YOUTUBE_APIFY_MAX_VIDEOS=0 \
YOUTUBE_APIFY_MIN_REMAINING_USD_PER_TOKEN=0.05 \
YOUTUBE_APIFY_STOP_ON_LOW_SUCCESS_RATE=1 \
YOUTUBE_APIFY_SUCCESS_RATE_FLOOR=0.10 \
YOUTUBE_APIFY_ACCEPTED_EVENT_RATE_FLOOR=0.00 \
python scripts/run_youtube_apify_transcript_overnight.py
```

## Recommendation

1. Run the `$2.50` capped full run first.
2. Confirm transcript quality and import success remain acceptable.
3. Only then execute exhaustion mode to drain remaining credits safely.
