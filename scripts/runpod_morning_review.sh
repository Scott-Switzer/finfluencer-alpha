#!/usr/bin/env bash
set -euo pipefail

echo "=== Morning Review ==="
echo "Started at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

source .venv/bin/activate

echo ""
echo "--- Transcript Collection Status ---"
python3 -m finfluencer_alpha transcript-collection-status
echo ""

echo "--- Overnight Summary ---"
if [ -f "data/exports/report_ready/overnight_transcript_collection_summary.txt" ]; then
    cat data/exports/report_ready/overnight_transcript_collection_summary.txt
else
    echo "No summary file found."
fi
echo ""

echo "--- Last 200 Log Lines ---"
if [ -f "data/logs/overnight_transcripts.log" ]; then
    tail -200 data/logs/overnight_transcripts.log
else
    echo "No overnight log found."
fi
echo ""

echo "--- Rebuilding Transcript Events ---"
python3 -m finfluencer_alpha build-transcript-events --refresh-existing
echo ""

echo "--- Exporting Transcript Events ---"
python3 -m finfluencer_alpha export-transcript-events
echo ""

echo "--- Transcript Coverage Bias Report ---"
python3 -m finfluencer_alpha transcript-coverage-bias-report 2>/dev/null || echo "Coverage bias report not available."
echo ""

echo "--- Creating Backup ---"
bash scripts/backup_outputs.sh
echo ""

echo "=== Morning review complete at $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="
echo ""
echo "Recommended next actions:"
echo "  1. Download the backup archive from data/backups/"
echo "  2. Review the summary and coverage report"
echo "  3. If you want another overnight run, wait for cooldown, then:"
echo "     bash scripts/runpod_overnight_safe.sh"
echo "  4. Stop the pod when done to conserve credits"
