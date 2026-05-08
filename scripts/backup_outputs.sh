#!/usr/bin/env bash
set -euo pipefail

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="finfluencer_backup_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="data/backups/${ARCHIVE_NAME}"

echo "=== Creating backup: ${ARCHIVE_PATH} ==="

mkdir -p data/backups

tar -czf "${ARCHIVE_PATH}" \
  --exclude='.env' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='*.egg-info' \
  --exclude='.DS_Store' \
  --exclude='data/raw' \
  --exclude='data/templates' \
  --exclude='data/interim' \
  --exclude='data/imports' \
  --exclude='data/backups' \
  --exclude='data/.locks' \
  data/finfluencer_alpha.db \
  data/exports/report_ready/ \
  data/logs/ \
  2>/dev/null || true

if [ -f "${ARCHIVE_PATH}" ]; then
    SIZE=$(du -h "${ARCHIVE_PATH}" | cut -f1)
    echo "=== Backup created: ${ARCHIVE_PATH} (${SIZE}) ==="
    echo ""
    echo "To download to your local machine:"
    echo "  scp user@pod-ip:/workspace/FIN496CAPSTONE/${ARCHIVE_PATH} ./"
    echo ""
    echo "Or upload to Google Drive using rclone or the RunPod web file browser."
else
    echo "=== Backup file was not created (no files to include?) ==="
fi
