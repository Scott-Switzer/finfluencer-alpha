# 81 Slot-attributed provider probe decision

## Slots and providers tested
- Slots tested: `[6, 7, 8, 9, 10, 11]`
- Providers tested (11):
  - `akash9078/youtube-transcript-extractor`
  - `curious_coder/youtube-transcript-scraper`
  - `insight_api_labs/youtube-transcript`
  - `johnvc/YoutubeTranscripts`
  - `optimus-fulcria/youtube-transcript-extractor`
  - `scrape-creators/best-youtube-transcripts-scraper`
  - `seemuapps/youtube-transcript-scraper`
  - `starvibe/youtube-video-transcript`
  - `supreme_coder/youtube-transcript-scraper`
  - `topaz_sharingan/Youtube-Transcript-Scraper-1`
  - `zerohour/yt-transcript`

## Verification
- token_slot_number populated in every row: `True`
- Only token slots 6-11 tested: `True`
- Fallback token skipped: `True`

## Provider x slot table

| Provider | Slot | Decision | Run status | HTTP | Importable | Reason |
|---|---:|---|---|---:|---:|---|
| `akash9078/youtube-transcript-extractor` | 6 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `akash9078/youtube-transcript-extractor` | 7 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `akash9078/youtube-transcript-extractor` | 8 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `akash9078/youtube-transcript-extractor` | 9 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `akash9078/youtube-transcript-extractor` | 10 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `akash9078/youtube-transcript-extractor` | 11 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `curious_coder/youtube-transcript-scraper` | 6 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `curious_coder/youtube-transcript-scraper` | 7 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `curious_coder/youtube-transcript-scraper` | 8 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `curious_coder/youtube-transcript-scraper` | 9 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `curious_coder/youtube-transcript-scraper` | 10 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `curious_coder/youtube-transcript-scraper` | 11 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `insight_api_labs/youtube-transcript` | 6 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/f |
| `insight_api_labs/youtube-transcript` | 7 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/f |
| `insight_api_labs/youtube-transcript` | 8 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/f |
| `insight_api_labs/youtube-transcript` | 9 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/f |
| `insight_api_labs/youtube-transcript` | 10 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/f |
| `insight_api_labs/youtube-transcript` | 11 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/f |
| `johnvc/YoutubeTranscripts` | 6 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.youtube_url is required |
| `johnvc/YoutubeTranscripts` | 7 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.youtube_url is required |
| `johnvc/YoutubeTranscripts` | 8 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.youtube_url is required |
| `johnvc/YoutubeTranscripts` | 9 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.youtube_url is required |
| `johnvc/YoutubeTranscripts` | 10 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.youtube_url is required |
| `johnvc/YoutubeTranscripts` | 11 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.youtube_url is required |
| `optimus-fulcria/youtube-transcript-extractor` | 6 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.urls.0 must be string |
| `optimus-fulcria/youtube-transcript-extractor` | 7 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.urls.0 must be string |
| `optimus-fulcria/youtube-transcript-extractor` | 8 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.urls.0 must be string |
| `optimus-fulcria/youtube-transcript-extractor` | 9 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.urls.0 must be string |
| `optimus-fulcria/youtube-transcript-extractor` | 10 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.urls.0 must be string |
| `optimus-fulcria/youtube-transcript-extractor` | 11 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.urls.0 must be string |
| `scrape-creators/best-youtube-transcripts-scraper` | 6 | `RUN_FAILED` | `FAILED` | 201 | 0 | run_status_FAILED |
| `scrape-creators/best-youtube-transcripts-scraper` | 7 | `RUN_FAILED` | `FAILED` | 201 | 0 | run_status_FAILED |
| `scrape-creators/best-youtube-transcripts-scraper` | 8 | `RUN_FAILED` | `FAILED` | 201 | 0 | run_status_FAILED |
| `scrape-creators/best-youtube-transcripts-scraper` | 9 | `RUN_FAILED` | `FAILED` | 201 | 0 | run_status_FAILED |
| `scrape-creators/best-youtube-transcripts-scraper` | 10 | `RUN_FAILED` | `FAILED` | 201 | 0 | run_status_FAILED |
| `scrape-creators/best-youtube-transcripts-scraper` | 11 | `RUN_FAILED` | `FAILED` | 201 | 0 | run_status_FAILED |
| `seemuapps/youtube-transcript-scraper` | 6 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.videoUrls is required |
| `seemuapps/youtube-transcript-scraper` | 7 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.videoUrls is required |
| `seemuapps/youtube-transcript-scraper` | 8 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.videoUrls is required |
| `seemuapps/youtube-transcript-scraper` | 9 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.videoUrls is required |
| `seemuapps/youtube-transcript-scraper` | 10 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.videoUrls is required |
| `seemuapps/youtube-transcript-scraper` | 11 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.videoUrls is required |
| `starvibe/youtube-video-transcript` | 6 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `starvibe/youtube-video-transcript` | 7 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `starvibe/youtube-video-transcript` | 8 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `starvibe/youtube-video-transcript` | 9 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `starvibe/youtube-video-transcript` | 10 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `starvibe/youtube-video-transcript` | 11 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Property input.urls is not allowed. |
| `supreme_coder/youtube-transcript-scraper` | 6 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `supreme_coder/youtube-transcript-scraper` | 7 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `supreme_coder/youtube-transcript-scraper` | 8 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `supreme_coder/youtube-transcript-scraper` | 9 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `supreme_coder/youtube-transcript-scraper` | 10 | `PROVIDER_PASS` | `SUCCEEDED` | 201 | 2 | importable_transcripts_found |
| `supreme_coder/youtube-transcript-scraper` | 11 | `RUN_FAILED` | `HTTP_502` | 201 | 0 | run_status_HTTP_502 |
| `topaz_sharingan/Youtube-Transcript-Scraper-1` | 6 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.startUrls is required |
| `topaz_sharingan/Youtube-Transcript-Scraper-1` | 7 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.startUrls is required |
| `topaz_sharingan/Youtube-Transcript-Scraper-1` | 8 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.startUrls is required |
| `topaz_sharingan/Youtube-Transcript-Scraper-1` | 9 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.startUrls is required |
| `topaz_sharingan/Youtube-Transcript-Scraper-1` | 10 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.startUrls is required |
| `topaz_sharingan/Youtube-Transcript-Scraper-1` | 11 | `START_FAILED_SCHEMA` | `nan` | 400 | 0 | Input is not valid: Field input.startUrls is required |
| `zerohour/yt-transcript` | 6 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/c |
| `zerohour/yt-transcript` | 7 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/c |
| `zerohour/yt-transcript` | 8 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/c |
| `zerohour/yt-transcript` | 9 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/c |
| `zerohour/yt-transcript` | 10 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/c |
| `zerohour/yt-transcript` | 11 | `START_FAILED_RENTAL_REQUIRED` | `nan` | 403 | 0 | You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/c |

## Fresh probe passing provider-slot pairs
- `curious_coder/youtube-transcript-scraper` slot `6`
- `curious_coder/youtube-transcript-scraper` slot `7`
- `curious_coder/youtube-transcript-scraper` slot `8`
- `curious_coder/youtube-transcript-scraper` slot `9`
- `curious_coder/youtube-transcript-scraper` slot `10`
- `curious_coder/youtube-transcript-scraper` slot `11`
- `supreme_coder/youtube-transcript-scraper` slot `6`
- `supreme_coder/youtube-transcript-scraper` slot `7`
- `supreme_coder/youtube-transcript-scraper` slot `8`
- `supreme_coder/youtube-transcript-scraper` slot `9`
- `supreme_coder/youtube-transcript-scraper` slot `10`

## Controlled recovery across fresh passing pairs
- Attempts: `11`
- Imported transcripts: `0`
- Mean success rate: `0.000`
- Pair outcomes:
  - `curious_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"curious_coder/youtube-transcript-scraper::10": "EXHAUSTED_credit_or_rental"}`
  - `curious_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"curious_coder/youtube-transcript-scraper::11": "EXHAUSTED_credit_or_rental"}`
  - `curious_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"curious_coder/youtube-transcript-scraper::6": "EXHAUSTED_credit_or_rental"}`
  - `curious_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"curious_coder/youtube-transcript-scraper::7": "EXHAUSTED_credit_or_rental"}`
  - `curious_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"curious_coder/youtube-transcript-scraper::8": "EXHAUSTED_credit_or_rental"}`
  - `curious_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"curious_coder/youtube-transcript-scraper::9": "EXHAUSTED_credit_or_rental"}`
  - `supreme_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"supreme_coder/youtube-transcript-scraper::10": "EXHAUSTED_credit_or_rental"}`
  - `supreme_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"supreme_coder/youtube-transcript-scraper::6": "EXHAUSTED_credit_or_rental"}`
  - `supreme_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"supreme_coder/youtube-transcript-scraper::7": "EXHAUSTED_credit_or_rental"}`
  - `supreme_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"supreme_coder/youtube-transcript-scraper::8": "EXHAUSTED_credit_or_rental"}`
  - `supreme_coder/youtube-transcript-scraper` -> imported `0`, success `0.000`, spend `0.000`, stop `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, pair_status `{"supreme_coder/youtube-transcript-scraper::9": "EXHAUSTED_credit_or_rental"}`

## Failure category assessment
- credit_limit: `False`
- actor_rental_or_subscription: `True`
- actor_eligibility: `True`
- platform_monthly_hard_limit: `False`
- schema: `True`
- provider_failure: `True`

## Decision
- **Stop collection and lock sample; move to analysis.**
