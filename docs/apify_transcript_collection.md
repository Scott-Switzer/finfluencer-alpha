# Apify Transcript Collection

This document describes how to use the Apify provider to collect YouTube video transcripts for the FIN496CAPSTONE finfluencer event-study project.

## Overview

Apify is added as a transcript provider alongside the existing pipeline (youtube_transcript_api, paid transcript APIs). It is NOT a replacement for the whole pipeline. The provider order is:

1. Paid provider (YouTubeTranscript.dev / TranscriptAPI.com) if credits available
2. Apify transcript actor
3. youtube_transcript_api (native package)
4. yt-dlp subtitle fallback (planned tier)

## Getting Your APIFY_TOKEN

1. Create an account at https://console.apify.com
2. Go to Account > Integrations: https://console.apify.com/account#/integrations
3. Copy your API token
4. Add it to your `.env` file:

```bash
APIFY_TOKEN=your_token_here
```

Never commit your `.env` file. The token is read via `os.environ` and silently resolved by the provider. It is never printed in logs or CLI output.

## Supported Actors

- `scrape-creators/best-youtube-transcripts-scraper`
- `seemuapps/youtube-transcript-scraper`
- `curious_coder/youtube-transcript-scraper`
- `muhammad_noman_riaz/youtube-video-transcript-super-scraper`
- `powerai/youtube-transcript-scraper`
- `pintostudio/youtube-transcript-scraper`
- `supreme_coder/youtube-transcript-scraper`
- `hgservices/youtube-transcript-scraper`

The collector keeps actor-specific input builders and output normalizers separate. Stored transcript provenance now includes the Apify actor ID and the provider run ID, in addition to transcript text, language, timestamps when present, and collection timestamps.

## Dry Run

A dry run selects videos and shows the plan without making any Apify calls or database writes:

```bash
python3 -m finfluencer_alpha collect-apify-transcripts \
  --dry-run \
  --max-videos 50 \
  --start-date 2020-01-01 \
  --end-date 2026-05-12
```

Output includes:
- Videos in range and already available counts
- Selected videos by creator and year
- A table of selected video IDs, creators, years, and titles

No APIFY_TOKEN is required for dry runs.

## 5-Video Smoke Test

```bash
python3 -m finfluencer_alpha collect-apify-transcripts \
  --actor-id supreme_coder/youtube-transcript-scraper \
  --max-videos 5 \
  --batch-size 5 \
  --max-total-charge-usd 1.00
```

This tests the full pipeline with minimal cost. The batch size equals the video count to make a single API call.

## 50-Video Pilot

```bash
python3 -m finfluencer_alpha collect-apify-transcripts \
  --actor-id supreme_coder/youtube-transcript-scraper \
  --max-videos 50 \
  --batch-size 25 \
  --max-total-charge-usd 1.00
```

## Scaling to 250 / 1000 Videos

For larger collections, increase `--max-videos` and `--batch-size`. Each batch is a separate Apify actor run:

```bash
# 250 videos
python3 -m finfluencer_alpha collect-apify-transcripts \
  --max-videos 250 \
  --batch-size 50

# 1000 videos
python3 -m finfluencer_alpha collect-apify-transcripts \
  --max-videos 1000 \
  --batch-size 100
```

The `--max-total-charge-usd` parameter is passed to the Apify API on every live actor run. Omit it for no cap, or set a low value (e.g., 1.00) for initial testing.

## Benchmarking Fallback Actors

Use the benchmark command before promoting a new fallback actor:

```bash
python3 -m finfluencer_alpha benchmark-apify-transcript-actors \
  --actors seemuapps/youtube-transcript-scraper \
  curious_coder/youtube-transcript-scraper \
  muhammad_noman_riaz/youtube-video-transcript-super-scraper \
  powerai/youtube-transcript-scraper \
  pintostudio/youtube-transcript-scraper \
  --only-missing-transcripts \
  --start-date 2024-01-01 \
  --end-date 2026-05-12 \
  --max-videos-per-actor 10 \
  --batch-size 10 \
  --max-total-charge-usd 0.50
```

The benchmark is measurement-only: it does not import transcripts into the SQLite dataset. It writes a CSV and Markdown report under `data/exports/transcripts/` with success rate, malformed output counts, timestamp availability, price signal, actor cost, and cost per success.

## Filtering Options

| Option | Description |
|--------|-------------|
| `--start-date YYYY-MM-DD` | Earliest video publish date |
| `--end-date YYYY-MM-DD` | Latest video publish date |
| `--creator NAME` | Limit to a specific channel_title |
| `--year YYYY` | Limit to a specific publish year |
| `--max-videos N` | Maximum videos to collect |
| `--batch-size N` | Videos per Apify API call |
| `--retry-permanent` | Retry videos previously marked disabled/unavailable |

## Queue Selection

The queue selection algorithm:
1. Queries `raw_youtube_videos` for seed-sourced videos (non-empty `seed_source` column)
2. Excludes videos already in `youtube_transcripts` with status='available' and non-empty full_text
3. Excludes permanently unavailable videos (`disabled`, `unavailable`) unless `--retry-permanent` is passed
4. Filters by date range, creator, and year as specified
5. Stratifies selection in round-robin fashion across creators for balanced representation
6. Caps at `--max-videos`

## Statuses

Each video processed receives one of these statuses:

| Status | Meaning |
|--------|---------|
| `available` | Transcript successfully collected and stored |
| `no_transcript` | No captions available for this video |
| `unavailable` | Video is age-restricted, private, or removed |
| `blocked` | Request was blocked by YouTube |
| `error` | Provider failure or malformed output |
| `missing` | Apify run completed but did not return a result |

## Avoiding Duplicate Transcripts

The system automatically:
- Skips videos that already have `status='available'` with non-empty `full_text` in `youtube_transcripts`
- Records each attempt in `transcript_collection_attempts` and `transcript_collection_runs`
- Updates `transcript_fetch_queue` status on successful import

Do NOT manually run the same batch twice without `--retry-permanent` or without first checking existing coverage.

## Raw Transcripts Are Not Committed

Raw provider responses are stored in `data/raw/apify/` which is gitignored (covered by the `data/raw/` ignore pattern). Transcript text is stored in the SQLite database (`youtube_transcripts.full_text`). The database file itself is also gitignored.

## How This Supports the Event-Study Design

1. **Deterministic**: Queue selection uses hash-based stratification; no LLM-based classification
2. **Auditable**: Every run is recorded in `transcript_collection_runs` with counts and statuses
3. **Reproducible**: Fixed seed creators, date ranges, and deterministic selection
4. **Sampling validity**: Round-robin stratification balances by creator and year
5. **Cost-controlled**: `--max-total-charge-usd` and `--max-videos` cap both spend and volume
6. **Non-destructive**: Dry run confirms selection before any calls; existing transcripts are never overwritten

## Fallback Routing

The `transcript_fallback.py` module defines the provider chain:

```python
PROVIDER_ORDER = [
    ProviderTier.PAID_API,     # YouTubeTranscript.dev / TranscriptAPI.com
    ProviderTier.APIFY,         # Apify actor
    ProviderTier.NATIVE_PACKAGE, # youtube_transcript_api
    ProviderTier.YT_DLP,        # yt-dlp subtitle fallback (planned)
]
```

Each tier is attempted in order for videos missing transcripts. The `resolve_provider_chain()` function checks which providers are configured (via environment variables) and automatically skips unconfigured tiers.

## Raw Data Location

Raw Apify responses are saved to `data/raw/apify/` with filenames like:
```
20260512T120000Z_supreme_coder_youtube-transcript-scraper_test_run_123.json
```

These files are gitignored and should not be committed. They exist for audit and debugging purposes.
