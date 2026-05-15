#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/FIN496CAPSTONE"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

LOG_DIR="$ROOT/logs"
OUT_DIR="$ROOT/data/exports/overnight_collection"
FINAL_REPORT_MD="$OUT_DIR/63_youtube_autonomous_expansion_final_report.md"
WATCHDOG_STATUS_MD="$OUT_DIR/65_autonomous_watchdog_status.md"
WATCHDOG_PID_FILE="$LOG_DIR/youtube_autonomous_watchdog.pid"

mkdir -p "$LOG_DIR" "$OUT_DIR"

START_TS="$(date -u +%Y%m%d_%H%M%S)"
WATCHDOG_LOG="$LOG_DIR/youtube_autonomous_watchdog_${START_TS}.log"

exec >>"$WATCHDOG_LOG" 2>&1

utc_now() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

active_autonomous_pids() {
  pgrep -f "python scripts/autonomous_youtube_transcript_expansion.py" || true
}

active_runner_pids() {
  pgrep -f "python scripts/run_youtube_apify_transcript_overnight.py" || true
}

write_status() {
  local decision="$1"
  local auto_pids="$2"
  local runner_pids="$3"
  local final_exists="$4"
  cat >"$WATCHDOG_STATUS_MD" <<EOF
# Autonomous watchdog status

- Timestamp UTC: \`$(utc_now)\`
- Watchdog PID: \`$$\`
- Watchdog log: \`${WATCHDOG_LOG#$ROOT/}\`
- Decision: \`${decision}\`
- Active autonomous PIDs: \`${auto_pids:-none}\`
- Active child runner PIDs: \`${runner_pids:-none}\`
- Final report exists: \`${final_exists}\`
- Check interval seconds: \`120\`

Do not terminate RunPod until final outputs and backup verification are complete.
EOF
}

echo "$(utc_now) watchdog starting, pid=$$"
echo "$$" >"$WATCHDOG_PID_FILE"

while true; do
  echo "$$" >"$WATCHDOG_PID_FILE"

  if [[ -f "$FINAL_REPORT_MD" ]]; then
    write_status "final_report_present_exit" "$(active_autonomous_pids | tr '\n' ' ' | sed 's/[[:space:]]*$//')" "$(active_runner_pids | tr '\n' ' ' | sed 's/[[:space:]]*$//')" "yes"
    echo "$(utc_now) final report found, exiting watchdog"
    exit 0
  fi

  AUTO_PIDS="$(active_autonomous_pids | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  RUNNER_PIDS="$(active_runner_pids | tr '\n' ' ' | sed 's/[[:space:]]*$//')"

  if [[ -n "${AUTO_PIDS}" ]]; then
    write_status "autonomous_active_no_restart" "$AUTO_PIDS" "$RUNNER_PIDS" "no"
    echo "$(utc_now) autonomous active (${AUTO_PIDS}), no restart"
    sleep 120
    continue
  fi

  write_status "autonomous_missing_restarting" "none" "$RUNNER_PIDS" "no"
  RESTART_TS="$(date -u +%Y%m%d_%H%M%S)"
  RESTART_LOG="$LOG_DIR/youtube_autonomous_expansion_restarted_${RESTART_TS}.log"
  echo "$(utc_now) autonomous missing; restarting to $RESTART_LOG"

  nohup bash -lc '
  cd /workspace/FIN496CAPSTONE

  RUN_YOUTUBE_AUTONOMOUS_EXPANSION=1 \
  YOUTUBE_AUTONOMOUS_ENABLE_METADATA_EXPANSION=1 \
  YOUTUBE_AUTONOMOUS_ENABLE_SEARCH_DISCOVERY=1 \
  YOUTUBE_AUTONOMOUS_MAX_CYCLES=20 \
  YOUTUBE_AUTONOMOUS_MIN_NEW_VIDEOS_TO_CONTINUE=100 \
  YOUTUBE_AUTONOMOUS_SEARCH_QUOTA_CAP=2000 \
  YOUTUBE_AUTONOMOUS_MAX_NEW_CHANNELS_PER_CYCLE=50 \
  YOUTUBE_AUTONOMOUS_MAX_NEW_VIDEOS_PER_CYCLE=10000 \
  YOUTUBE_AUTONOMOUS_MAX_QUEUE_ROWS=50000 \
  YOUTUBE_TRANSCRIPT_QUEUE_MAX_ROWS=50000 \
  YOUTUBE_TRANSCRIPT_QUEUE_EXPANSION_MODE=exhaustive \
  RUN_YOUTUBE_APIFY_OVERNIGHT=1 \
  YOUTUBE_APIFY_EXHAUST_ALL_KEYS=1 \
  YOUTUBE_APIFY_STOP_WHEN_ALL_KEYS_EXHAUSTED=1 \
  YOUTUBE_APIFY_SELECTED_PROVIDER="supreme_coder/youtube-transcript-scraper" \
  YOUTUBE_APIFY_TARGET_SPEND_USD=9999 \
  YOUTUBE_APIFY_MAX_TOTAL_SPEND_USD=9999 \
  YOUTUBE_APIFY_BATCH_SIZE=100 \
  YOUTUBE_APIFY_MAX_VIDEOS=0 \
  YOUTUBE_APIFY_MIN_REMAINING_USD_PER_TOKEN=0.05 \
  YOUTUBE_APIFY_STOP_ON_LOW_SUCCESS_RATE=1 \
  YOUTUBE_APIFY_SUCCESS_RATE_FLOOR=0.10 \
  YOUTUBE_APIFY_ACCEPTED_EVENT_RATE_FLOOR=0.00 \
  python scripts/autonomous_youtube_transcript_expansion.py
  ' >"$RESTART_LOG" 2>&1 &

  echo "$(utc_now) restart launched pid=$!"
  sleep 120
done
