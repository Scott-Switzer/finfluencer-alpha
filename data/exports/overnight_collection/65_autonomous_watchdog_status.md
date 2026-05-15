# Autonomous watchdog status

- Timestamp UTC: `2026-05-15T03:48:43Z`
- Watchdog PID: `12447`
- Watchdog detached: `yes` (PPID `1`)
- Watchdog log: `logs/youtube_autonomous_watchdog_20260515_034751.log`
- Active autonomous PIDs: `7979` (launcher), `7986` (python autonomous)
- Active child runner PIDs: `none` (not active at sample instant)
- Current run active: `yes`
- Decision: `autonomous_active_no_restart`
- Check interval seconds: `120`

## Latest visible metrics (53_* / 62_*)

- `53_youtube_apify_overnight_live_status.md`:
  - attempted: `0`
  - imported: `0`
  - transient_failures: `100`
  - spend_usd: `0.0`
  - queue_remaining: `5096`
  - decision: `STOP_ALL_KEYS_EXHAUSTED`
- `62_youtube_autonomous_expansion_live_status.md`:
  - current_cycle: `11`
  - total_spend_estimate_usd: `1.3005`
  - queue_before: `5196`
  - queue_after: `5196`
  - new_accepted_events: `0`

## Artifact status

- `62_youtube_autonomous_expansion_live_status.md`: `present`
- `63_youtube_autonomous_expansion_final_report.md`: `missing`

## Duplicate-process check

- Active autonomous python processes: `1` (`7986`)
- Duplicate autonomous process exists: `no`

## Next manual check commands

```bash
cat logs/youtube_autonomous_watchdog.pid
ps -axo pid,ppid,pgid,sess,etime,stat,command | awk '/watch_youtube_autonomous_expansion|autonomous_youtube_transcript_expansion|run_youtube_apify_transcript_overnight/ && !/awk/'
cat data/exports/overnight_collection/53_youtube_apify_overnight_live_status.md
cat data/exports/overnight_collection/62_youtube_autonomous_expansion_live_status.md
```

## Warning

Do not terminate RunPod until final outputs are produced and backup bundle is pulled and verified locally.
