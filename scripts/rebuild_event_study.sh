set -e
cd /workspace/FIN496CAPSTONE
source .venv/bin/activate

echo "=== REBUILD MARKET DATA REQUEST ==="
python3 -m finfluencer_alpha build-market-data-request

echo "=== FETCH YFINANCE MARKET DATA ==="
python3 -m finfluencer_alpha fetch-yfinance-market-data --confirm-yfinance-run

echo "=== RUN EVENT STUDY ==="
python3 -m finfluencer_alpha run-event-study

echo "=== FINAL RESULTS ==="
python3 -m finfluencer_alpha transcript-coverage-report | head -5

echo "=== CLEAN EVENTS COUNT ==="
python3 scripts/check_event_counts.py
