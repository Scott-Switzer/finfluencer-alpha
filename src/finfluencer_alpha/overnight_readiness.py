from __future__ import annotations

from dataclasses import dataclass

from .config import get_settings
from .db import connect, init_db


@dataclass
class OvernightReadiness:
    ready: bool
    reasons: list[str]
    free_disk_mb: float
    cooldown_active: bool
    attempts_last_24h: int
    max_daily_attempts: int
    queue_eligible: int
    high_risk_only_targets: int
    false_positive_quarantine_count: int
    recommended_command: str


def overnight_readiness_check() -> OvernightReadiness:
    init_db()
    settings = get_settings()
    reasons: list[str] = []

    from .overtime_collection import (
        _attempts_last_24h,
        _cooldown_active,
        _free_disk_mb,
    )
    from .ticker_false_positive import count_high_risk_only_targets

    free_disk = _free_disk_mb()
    cooldown = _cooldown_active(connect(), settings.transcript_queue_cooldown_hours)
    stats_24h = _attempts_last_24h(connect())

    with connect() as conn:
        queue_eligible = conn.execute(
            """
            SELECT COUNT(*) FROM transcript_fetch_queue tfq
            JOIN raw_youtube_videos rv ON rv.video_id = tfq.video_id
            WHERE COALESCE(rv.excluded_flag, 0) = 0
              AND (tfq.transcript_status IS NULL
                   OR tfq.transcript_status IN ('error', 'rate_limited', 'no_language'))
            """
        ).fetchone()[0]

        false_pos_quarantine = conn.execute(
            "SELECT COUNT(*) FROM transcript_event_exclusions"
        ).fetchone()[0]

    high_risk_only = count_high_risk_only_targets(connect())

    if free_disk < 500:
        reasons.append(f"DISK_TOO_LOW: {free_disk:.0f} MB free (need 500 MB)")
    elif free_disk < 1000:
        reasons.append(f"DISK_LOW_WARNING: {free_disk:.0f} MB free (recommend 1000 MB)")

    if cooldown:
        reasons.append("COOLDOWN_ACTIVE: IP or request block within cooldown window")

    if stats_24h["total"] >= 50:
        reasons.append(f"DAILY_CAP_REACHED: {stats_24h['total']} attempts in last 24h (cap=50)")

    if queue_eligible == 0:
        reasons.append("NO_ELIGIBLE_QUEUE: no pending videos in fetch queue")

    if high_risk_only > 50:
        reasons.append(f"HIGH_RISK_ONLY_TARGETS: {high_risk_only} videos with only high-risk ticker signals")

    ready = len([r for r in reasons if "TOO_LOW" in r or "CAP_REACHED" in r or "NO_ELIGIBLE" in r or "COOLDOWN_ACTIVE" in r]) == 0

    if ready:
        rec_cmd = (
            "python3 -m finfluencer_alpha collect-native-transcripts-overtime "
            "--limit 20 --sleep-seconds 20 --jitter-seconds 10 "
            "--max-per-creator 3 --min-disk-mb 500 --stop-on-block "
            "--creator-diversify --cooldown-hours 24 --max-daily-attempts 50"
        )
    else:
        rec_cmd = "DO NOT RUN — resolve blocking issues first"

    return OvernightReadiness(
        ready=ready,
        reasons=reasons if reasons else ["ALL_CLEAR"],
        free_disk_mb=free_disk,
        cooldown_active=cooldown,
        attempts_last_24h=stats_24h["total"],
        max_daily_attempts=50,
        queue_eligible=queue_eligible,
        high_risk_only_targets=high_risk_only,
        false_positive_quarantine_count=false_pos_quarantine,
        recommended_command=rec_cmd,
    )
