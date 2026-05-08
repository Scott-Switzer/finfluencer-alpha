#!/usr/bin/env bash
set -euo pipefail

echo "=== RunPod Bootstrap for FIN 496 ==="
echo "Started at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cd /workspace

if [ -d "FIN496CAPSTONE" ]; then
    echo "Repo exists. Pulling latest..."
    cd FIN496CAPSTONE
    git pull origin main
else
    echo "Cloning repo..."
    git clone https://github.com/Scott-Switzer/finfluencer-alpha.git FIN496CAPSTONE
    cd FIN496CAPSTONE
fi

echo "Setting up virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Creating data directories..."
mkdir -p data/logs data/exports/report_ready data/backups data/.locks

echo "=== Validation ==="

echo "--- Ruff ---"
python3 -m ruff check .
echo ""

echo "--- Pytest ---"
python3 -m pytest -q
echo ""

echo "--- Transcript Collection Status ---"
python3 -m finfluencer_alpha transcript-collection-status
echo ""

echo "--- Overnight Readiness Check ---"
python3 -m finfluencer_alpha overnight-readiness-check
echo ""

echo "=== Bootstrap complete at $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="
echo ""
echo "If readiness shows READY_FOR_OVERNIGHT, run:"
echo "  bash scripts/runpod_overnight_safe.sh"
echo ""
echo "If NOT_READY, review the reasons above before running the overnight command."
