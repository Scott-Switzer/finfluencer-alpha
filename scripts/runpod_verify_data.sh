#!/usr/bin/env bash
set -euo pipefail

echo "=== RunPod Data Verification ==="
echo "Started at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

cd /workspace/FIN496CAPSTONE

echo "--- Checking data directories ---"
mkdir -p data/logs data/exports/report_ready data/backups data/.locks
ls -d data/logs data/exports data/backups 2>/dev/null
echo ""

echo "--- Checking database file ---"
DB_PATH="data/finfluencer_alpha.db"

if [ ! -f "${DB_PATH}" ]; then
    echo ""
    echo "=== ERROR: Database not found at ${DB_PATH} ==="
    echo ""
    echo "The database has NOT been transferred to RunPod yet."
    echo ""
    echo "Upload steps:"
    echo "  1. On your Mac, run: bash scripts/local_prepare_runpod_upload.sh"
    echo "  2. Upload finfluencer_alpha.db to /workspace/FIN496CAPSTONE/data/"
    echo "     Use RunPod web File Browser, scp, or Google Drive"
    echo "  3. Re-run this script after upload"
    echo ""
    exit 1
fi

DB_SIZE=$(ls -lh "${DB_PATH}" | awk '{print $5}')
echo "Database: ${DB_PATH} (${DB_SIZE})"
echo ""

echo "--- Transcript Collection Status ---"
source .venv/bin/activate 2>/dev/null || true
python3 -m finfluencer_alpha transcript-collection-status
STATUS_EXIT=$?
echo ""

if [ ${STATUS_EXIT} -ne 0 ]; then
    echo "=== WARNING: transcript-collection-status exited with code ${STATUS_EXIT} ==="
    echo "This may indicate the DB is missing, corrupted, or DATABASE_URL is wrong."
    echo "Check your .env file: DATABASE_URL=sqlite:///data/finfluencer_alpha.db"
    echo ""
fi

echo "--- Overnight Readiness Check ---"
python3 -m finfluencer_alpha overnight-readiness-check
READY_EXIT=$?
echo ""

echo "=== Verification complete at $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="
echo ""

if [ ${STATUS_EXIT} -eq 0 ] && [ ${READY_EXIT} -eq 0 ]; then
    echo "=== READY ==="
    echo ""
    echo "Next: Run the smoke test before overnight:"
    echo ""
    echo "  python3 -m finfluencer_alpha run-overnight-transcript-collection \\"
    echo "    --batches 1 \\"
    echo "    --batch-limit 2 \\"
    echo "    --between-batch-sleep-seconds 30 \\"
    echo "    --sleep-seconds 45 \\"
    echo "    --jitter-seconds 20 \\"
    echo "    --max-per-creator 1 \\"
    echo "    --min-disk-mb 1000 \\"
    echo "    --cooldown-hours 24 \\"
    echo "    --max-daily-attempts 10"
    echo ""
    echo "If smoke test passes (transcripts collected, no block errors):"
    echo "  bash scripts/runpod_overnight_safe.sh"
elif [ ! -f "${DB_PATH}" ]; then
    echo "=== NOT READY: Database file is missing ==="
    echo "Transfer the DB first (see instructions above)."
else
    echo "=== NOT READY: Review the status and readiness output above ==="
    echo "If 0 transcripts: DB may not have been transferred or DATABASE_URL is wrong."
    echo "If disk issue: ensure you are using /workspace Network Volume, not container disk."
    echo "If block error: RunPod cloud IP may not be viable for native collection."
fi
