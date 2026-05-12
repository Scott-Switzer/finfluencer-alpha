# Manual Transcript Collection Packet

- Source queue: `data/exports/transcripts/slow_youtube_transcript_queue.csv`
- Videos in packet: 100

## Year Breakdown

- 2021: 56
- 2022: 44

## Instructions

1. Open each YouTube URL.
2. Click the transcript/CC button below the video.
3. Copy the transcript text into the `transcript_text` column.
4. Save the filled CSV as `data/imports/manual_transcripts_filled.csv`.
5. Run: `python3 -m finfluencer_alpha import-manual-transcripts --input data/imports/manual_transcripts_filled.csv --confirm-import`

- Packet CSV: `data/exports/transcripts/manual_collection_packet.csv`
- Template CSV: `data/imports/manual_transcripts_template.csv`
