#!/usr/bin/env bash
set -euo pipefail

echo "=== Local Mac → RunPod Transfer Prep ==="
echo "Started at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

TRANSFER_DIR="runpod_transfer"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
STAGING="${TRANSFER_DIR}/transfer_${TIMESTAMP}"

echo "Creating staging directory: ${STAGING}"
mkdir -p "${STAGING}"

DB_FILE="data/finfluencer_alpha.db"
ENV_EXAMPLE=".env.example"

FILES_TO_UPLOAD=""

if [ -f "${DB_FILE}" ]; then
    DB_SIZE=$(du -h "${DB_FILE}" | cut -f1)
    echo "Found DB: ${DB_FILE} (${DB_SIZE})"

    AVAILABLE_MB=$(df -m . | awk 'NR==2 {print $4}')
    DB_SIZE_MB=$(du -m "${DB_FILE}" | cut -f1)

    if [ "${AVAILABLE_MB}" -lt "$((DB_SIZE_MB + 50))" ]; then
        echo ""
        echo "=== WARNING: Low disk space ==="
        echo "Available: ${AVAILABLE_MB} MB, DB is ~${DB_SIZE_MB} MB"
        echo ""
        echo "Copying the DB locally may fail or leave you with near-zero free space."
        echo "Manual alternatives:"
        echo "  1. Upload DB directly through RunPod web file browser (no local copy needed)"
        echo "  2. Upload DB to Google Drive from your Mac without local duplication"
        echo "  3. Free some disk space first and re-run this script"
        echo ""
        echo "Attempting to copy anyway..."
    fi

    cp "${DB_FILE}" "${STAGING}/"
    FILES_TO_UPLOAD="${FILES_TO_UPLOAD} finfluencer_alpha.db"
    echo "  Copied: finfluencer_alpha.db (${DB_SIZE})"
else
    echo "No existing DB found at ${DB_FILE}."
    echo "If this is a fresh RunPod setup without a pre-existing DB, skip this step."
fi

if [ -f "${ENV_EXAMPLE}" ]; then
    cp "${ENV_EXAMPLE}" "${STAGING}/"
    FILES_TO_UPLOAD="${FILES_TO_UPLOAD} .env.example"
    echo "  Copied: .env.example"
fi

echo ""

INSTRUCTIONS_FILE="${TRANSFER_DIR}/UPLOAD_INSTRUCTIONS.txt"
cat > "${INSTRUCTIONS_FILE}" << 'EOF'
============================================================
RunPod Data Transfer Instructions
============================================================

Target RunPod path for the database:

    /workspace/FIN496CAPSTONE/data/finfluencer_alpha.db

Upload method options:
  1. RunPod web console → File Browser → navigate to
     /workspace/FIN496CAPSTONE/data/ → upload finfluencer_alpha.db
  2. scp from Mac:
     scp finfluencer_alpha.db user@pod-ip:/workspace/FIN496CAPSTONE/data/finfluencer_alpha.db
  3. Google Drive upload from Mac, then download on RunPod terminal

After upload, verify on RunPod:
  ls -lh data/finfluencer_alpha.db
  python3 -m finfluencer_alpha transcript-collection-status

Expected: ~164 transcripts, ~97 accepted events, ~6305 queue eligible
If 0 transcripts: DB not transferred or DATABASE_URL is wrong in .env

Do NOT upload logs, exports, imports, caches, .env, or large raw data files.
============================================================
EOF

echo "=== Files ready in: ${STAGING}/ ==="
ls -lh "${STAGING}/"
echo ""
echo "Upload these file(s) to RunPod:"
if [ -n "${FILES_TO_UPLOAD}" ]; then
    for f in ${FILES_TO_UPLOAD}; do
        echo "  - ${f}"
    done
fi
echo ""
echo "Upload instructions saved to: ${INSTRUCTIONS_FILE}"
echo ""
echo "Next: upload the DB to /workspace/FIN496CAPSTONE/data/finfluencer_alpha.db"
echo "      then run bash scripts/runpod_verify_data.sh on the RunPod terminal"
