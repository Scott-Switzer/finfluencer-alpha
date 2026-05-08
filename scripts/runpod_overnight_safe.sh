#!/usr/bin/env bash
set -euo pipefail

echo "=== Overnight Transcript Collection (RunPod Safe) ==="
echo "Started at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

source .venv/bin/activate

python3 -m finfluencer_alpha run-overnight-transcript-collection \
  --batches 6 \
  --batch-limit 4 \
  --between-batch-sleep-seconds 3600 \
  --sleep-seconds 45 \
  --jitter-seconds 20 \
  --max-per-creator 1 \
  --min-disk-mb 1000 \
  --cooldown-hours 24 \
  --max-daily-attempts 30

EXIT_CODE=$?

echo ""
echo "=== Overnight collection finished at $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="
echo "Exit code: $EXIT_CODE"
echo ""
echo "Review results:"
echo "  cat data/exports/report_ready/overnight_transcript_collection_summary.txt"
echo "  tail -200 data/logs/overnight_transcripts.log"
echo ""
echo "When ready, run: bash scripts/runpod_morning_review.sh"

exit $EXIT_CODE
