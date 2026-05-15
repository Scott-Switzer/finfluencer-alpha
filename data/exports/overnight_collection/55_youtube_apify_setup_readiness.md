# YouTube Apify setup readiness

Generated (UTC): `2026-05-15T00:22:00Z`

- Setup ready: `yes (dry-run validated; live run still gated by canary pass)`
- Selected provider: `supreme_coder/youtube-transcript-scraper`
- Estimated videos currently in queue: `5000`
- Broad X in main study: `excluded`
- Paid calls during setup: `no`

## Estimated cost per 1,000 transcripts

`supreme_coder/youtube-transcript-scraper` metadata did not expose a clear public unit price in this setup run.  
Using nearby repo-known transcript actor pricing signals as a provisional bound, planning estimate is:

- Lower bound: `~$0.10 / 1,000` (best-case comparable actor pricing)
- Upper bound: `~$0.30 / 1,000` (conservative comparable actor pricing)
- Planning midpoint used for guardrails: `~$0.20 / 1,000` (provisional until live canary returns actual usage)

## Exact dry-run commands used

```bash
python scripts/build_youtube_transcript_expansion_queue.py
python scripts/plan_youtube_apify_transcript_drain.py
python scripts/canary_youtube_apify_transcript_provider.py
YOUTUBE_APIFY_SELECTED_PROVIDER="supreme_coder/youtube-transcript-scraper" python scripts/run_youtube_apify_transcript_overnight.py
python scripts/summarize_youtube_transcript_expansion.py
```

## Exact canary command to run next (tiny paid)

```bash
RUN_YOUTUBE_APIFY_TRANSCRIPT_CANARY=1 YOUTUBE_APIFY_SELECTED_PROVIDER="supreme_coder/youtube-transcript-scraper" YOUTUBE_APIFY_CANARY_MAX_VIDEOS=10 YOUTUBE_APIFY_CANARY_CAP_USD=0.10 python scripts/canary_youtube_apify_transcript_provider.py
```

## Exact overnight command (run only after canary passes)

```bash
RUN_YOUTUBE_APIFY_OVERNIGHT=1 YOUTUBE_APIFY_SELECTED_PROVIDER="supreme_coder/youtube-transcript-scraper" YOUTUBE_APIFY_TARGET_SPEND_USD=5.0 YOUTUBE_APIFY_MAX_TOTAL_SPEND_USD=10.0 YOUTUBE_APIFY_BATCH_SIZE=10 YOUTUBE_APIFY_MAX_VIDEOS=200 YOUTUBE_APIFY_MIN_REMAINING_USD_PER_TOKEN=0.25 YOUTUBE_APIFY_STOP_ON_LOW_SUCCESS_RATE=1 YOUTUBE_APIFY_SUCCESS_RATE_FLOOR=0.10 YOUTUBE_APIFY_ACCEPTED_EVENT_RATE_FLOOR=0.00 python scripts/run_youtube_apify_transcript_overnight.py
```
