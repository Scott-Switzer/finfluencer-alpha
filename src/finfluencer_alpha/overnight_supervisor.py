from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import PROJECT_ROOT
from .db import connect, init_db
from .utils import get_logger

LOCK_PATH = PROJECT_ROOT / "data" / ".locks" / "overnight_transcript_collection.lock"
DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "overnight_transcripts.log"
DEFAULT_SUMMARY_PATH = (
    PROJECT_ROOT / "data" / "exports" / "report_ready"
    / "overnight_transcript_collection_summary.txt"
)

logger = get_logger("overnight_supervisor")


@dataclass
class BatchResult:
    batch_number: int
    attempted: int = 0
    available: int = 0
    no_transcript: int = 0
    ip_blocked: int = 0
    request_blocked: int = 0
    rate_limited: int = 0
    other_errors: int = 0
    stopped_reason: str | None = None
    transcript_count_after: int = 0
    free_disk_after: float = 0


@dataclass
class OvernightSupervisorResult:
    started_at: str
    ended_at: str = ""
    batches_requested: int = 0
    batches_completed: int = 0
    total_attempted: int = 0
    total_available: int = 0
    total_no_transcript: int = 0
    total_ip_blocked: int = 0
    total_request_blocked: int = 0
    total_rate_limited: int = 0
    total_other_errors: int = 0
    starting_transcript_count: int = 0
    ending_transcript_count: int = 0
    starting_accepted_events: int = 0
    ending_accepted_events: int = 0
    disk_start_mb: float = 0
    disk_end_mb: float = 0
    stopped_reason: str | None = None
    batches: list[BatchResult] = field(default_factory=list)
    recommended_next_action: str = "RUN_ANOTHER_OVERNIGHT"


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_lock_stale(lock_data: dict) -> bool:
    pid = lock_data.get("pid")
    if pid is None:
        return True
    if not _pid_is_alive(pid):
        return True
    return False


def acquire_lock() -> bool:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    if LOCK_PATH.exists():
        try:
            lock_data = json.loads(LOCK_PATH.read_text())
        except (json.JSONDecodeError, ValueError):
            logger.warning("Corrupt lock file found. Removing stale lock.")
            LOCK_PATH.unlink(missing_ok=True)
        else:
            if not _is_lock_stale(lock_data):
                logger.error(
                    "Lock file exists and process PID %s appears active. "
                    "Refusing to start a duplicate overnight run.",
                    lock_data.get("pid"),
                )
                return False
            logger.warning(
                "Stale lock file found (PID %s is not alive). Removing and continuing.",
                lock_data.get("pid"),
            )
            LOCK_PATH.unlink(missing_ok=True)

    lock_data = {
        "pid": os.getpid(),
        "started_at": datetime.now(UTC).isoformat(),
        "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
    }
    LOCK_PATH.write_text(json.dumps(lock_data, indent=2))
    logger.info("Lock acquired: %s", LOCK_PATH)
    return True


def release_lock() -> None:
    if LOCK_PATH.exists():
        LOCK_PATH.unlink(missing_ok=True)
        logger.info("Lock released: %s", LOCK_PATH)


def _setup_file_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def _get_transcript_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM youtube_transcripts"
        ).fetchone()
        return row[0] if row else 0


def _get_accepted_events_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM transcript_recommendation_events"
        ).fetchone()
        return row[0] if row else 0


def _log_batch_start(logger: logging.Logger, batch_num: int, total_batches: int) -> None:
    msg = (
        f"\n{'='*60}\n"
        f"BATCH {batch_num}/{total_batches} starting at "
        f"{datetime.now(UTC).isoformat()}\n"
        f"{'='*60}"
    )
    logger.info(msg)


def _log_batch_result(logger: logging.Logger, result: BatchResult) -> None:
    logger.info(
        "Batch %d complete: attempted=%d, available=%d, no_transcript=%d, "
        "ip_blocked=%d, request_blocked=%d, rate_limited=%d, other_errors=%d, "
        "stopped_reason=%s, transcripts_after=%d, disk_after=%.0f MB",
        result.batch_number,
        result.attempted,
        result.available,
        result.no_transcript,
        result.ip_blocked,
        result.request_blocked,
        result.rate_limited,
        result.other_errors,
        result.stopped_reason or "none",
        result.transcript_count_after,
        result.free_disk_after,
    )


def _check_stop_conditions(result: BatchResult) -> tuple[bool, str | None]:
    if result.stopped_reason in ("ip_blocked", "request_blocked"):
        return True, f"block_detected:{result.stopped_reason}"
    if result.stopped_reason == "rate_limited":
        return True, "rate_limited"
    if result.stopped_reason and result.stopped_reason.startswith("disk_below"):
        return True, result.stopped_reason
    if result.stopped_reason == "cooldown_active":
        return True, "cooldown_active"
    if result.stopped_reason == "max_daily_attempts":
        return True, "max_daily_attempts"
    return False, None


def _compute_recommended_action(
    stopped_reason: str | None,
    block_detected: bool,
    total_attempted: int,
    total_available: int,
) -> str:
    if stopped_reason and "disk_below" in stopped_reason:
        return "REBUILD_EVENTS_AND_EXPORT"
    if block_detected:
        return "WAIT_FOR_COOLDOWN"
    if stopped_reason in ("max_daily_attempts", "rate_limited"):
        return "WAIT_FOR_COOLDOWN"
    if total_attempted == 0:
        return "MOVE_TO_CLASSIFIER_TRAINING"
    if total_available > 0:
        return "RUN_ANOTHER_OVERNIGHT"
    if total_attempted > 0 and total_available == 0:
        return "PAY_FOR_PROVIDER"
    return "RUN_ANOTHER_OVERNIGHT"


def write_final_summary(result: OvernightSupervisorResult, summary_path: Path) -> Path:
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    gain = result.ending_transcript_count - result.starting_transcript_count

    lines = [
        "=== Overnight Transcript Collection Summary ===",
        "",
        f"Started at:                 {result.started_at}",
        f"Ended at:                   {result.ended_at}",
        f"Batches requested:          {result.batches_requested}",
        f"Batches completed:          {result.batches_completed}",
        "",
        "--- Collection Totals ---",
        f"Total attempted:            {result.total_attempted}",
        f"Total available:            {result.total_available}",
        f"Total no_transcript:        {result.total_no_transcript}",
        f"Total ip_blocked:           {result.total_ip_blocked}",
        f"Total request_blocked:      {result.total_request_blocked}",
        f"Total rate_limited:         {result.total_rate_limited}",
        f"Total other errors:         {result.total_other_errors}",
        "",
        "--- Transcript State ---",
        f"Starting transcript count:  {result.starting_transcript_count}",
        f"Ending transcript count:    {result.ending_transcript_count}",
        f"Transcript gain:            {gain}",
        f"Starting accepted events:   {result.starting_accepted_events}",
        f"Ending accepted events:     {result.ending_accepted_events}",
        "",
        "--- Disk ---",
        f"Disk start (MB):            {result.disk_start_mb:.0f}",
        f"Disk end (MB):              {result.disk_end_mb:.0f}",
        "",
        f"Stopped reason:             {result.stopped_reason or 'completed normally'}",
        f"Recommended next action:    {result.recommended_next_action}",
        "",
    ]

    if result.batches:
        lines.append("--- Per-Batch Detail ---")
        lines.append(
            f"{'Batch':<7} {'Attempted':>9} {'Available':>9} "
            f"{'NoTranscript':>12} {'IpHlocked':>9} {'ReqBlocked':>10} "
            f"{'RateLimited':>11} {'OtherErrs':>9} {'StoppedReason':<20}"
        )
        lines.append("-" * 110)
        for b in result.batches:
            lines.append(
                f"{b.batch_number:<7} {b.attempted:>9} {b.available:>9} "
                f"{b.no_transcript:>12} {b.ip_blocked:>9} {b.request_blocked:>10} "
                f"{b.rate_limited:>11} {b.other_errors:>9} "
                f"{b.stopped_reason or 'none':<20}"
            )

    content = "\n".join(lines) + "\n"
    summary_path.write_text(content, encoding="utf-8")
    logger.info("Summary written to %s", summary_path)
    return summary_path


def run_overnight_transcript_collection(
    batches: int = 8,
    batch_limit: int = 5,
    between_batch_sleep_seconds: float = 2700,
    sleep_seconds: float = 35,
    jitter_seconds: float = 15,
    max_per_creator: int = 1,
    min_disk_mb: int = 500,
    cooldown_hours: int = 24,
    max_daily_attempts: int = 50,
    stop_on_block: bool = True,
    creator_diversify: bool = True,
    allow_translation: bool = False,
    rebuild_events_at_end: bool = False,
    log_path: Path | None = None,
    summary_path: Path | None = None,
    dry_run: bool = False,
) -> OvernightSupervisorResult:
    effective_log_path = log_path or DEFAULT_LOG_PATH
    effective_summary_path = summary_path or DEFAULT_SUMMARY_PATH
    logger = _setup_file_logging(effective_log_path)

    init_db()

    from .overnight_readiness import overnight_readiness_check
    from .overtime_collection import (
        _free_disk_mb,
        collect_native_transcripts_overtime,
        transcript_collection_status,
    )

    result = OvernightSupervisorResult(
        started_at=datetime.now(UTC).isoformat(),
        batches_requested=batches,
    )

    result.starting_transcript_count = _get_transcript_count()
    result.starting_accepted_events = _get_accepted_events_count()
    result.disk_start_mb = _free_disk_mb()

    logger.info("Overnight supervisor starting.")
    logger.info("  Batches requested: %d", batches)
    logger.info("  Batch limit: %d", batch_limit)
    logger.info("  Between-batch sleep: %.0f seconds", between_batch_sleep_seconds)
    logger.info("  Per-attempt sleep: %.1f seconds", sleep_seconds)
    logger.info("  Jitter: %.1f seconds", jitter_seconds)
    logger.info("  Max per creator: %d", max_per_creator)
    logger.info("  Min disk MB: %d", min_disk_mb)
    logger.info("  Cooldown hours: %d", cooldown_hours)
    logger.info("  Max daily attempts: %d", max_daily_attempts)
    logger.info("  Stop on block: %s", stop_on_block)
    logger.info("  Creator diversify: %s", creator_diversify)
    logger.info("  Allow translation: %s", allow_translation)
    logger.info("  Rebuild events at end: %s", rebuild_events_at_end)
    logger.info("  Dry run: %s", dry_run)
    logger.info("  Starting transcript count: %d", result.starting_transcript_count)
    logger.info("  Starting accepted events: %d", result.starting_accepted_events)
    logger.info("  Disk start: %.0f MB", result.disk_start_mb)

    if dry_run:
        logger.info("DRY RUN: Readiness check only; no transcripts will be collected.")

        readiness = overnight_readiness_check()
        status = transcript_collection_status()

        logger.info("Readiness: %s", "READY" if readiness.ready else "NOT_READY")
        for reason in readiness.reasons:
            logger.info("  Reason: %s", reason)
        logger.info("Queue eligible: %d", readiness.queue_eligible)
        logger.info("Transcripts: %d", status.total_transcripts)
        logger.info("Recommended command: %s", readiness.recommended_command)

        result.ended_at = datetime.now(UTC).isoformat()
        result.disk_end_mb = _free_disk_mb()
        result.ending_transcript_count = status.total_transcripts
        result.ending_accepted_events = status.accepted_events
        if not readiness.ready:
            result.stopped_reason = "NOT_READY_FOR_OVERNIGHT"
        result.recommended_next_action = (
            "MOVE_TO_CLASSIFIER_TRAINING" if readiness.ready else "WAIT_FOR_COOLDOWN"
        )

        write_final_summary(result, effective_summary_path)
        return result

    stopped = False
    stop_reason: str | None = None

    for batch_num in range(1, batches + 1):
        if stopped:
            logger.info("Skipping batch %d: stopped earlier (%s)", batch_num, stop_reason)
            break

        _log_batch_start(logger, batch_num, batches)

        logger.info("Running readiness check before batch %d...", batch_num)
        readiness = overnight_readiness_check()
        if not readiness.ready:
            logger.error(
                "Batch %d: NOT_READY_FOR_OVERNIGHT. Reasons: %s",
                batch_num, "; ".join(readiness.reasons),
            )
            stop_reason = "NOT_READY_FOR_OVERNIGHT"
            stopped = True
            break

        status_before = transcript_collection_status()
        logger.info(
            "Pre-batch status: transcripts=%d, accepted_events=%d, "
            "attempts_24h=%d, cooldown=%s",
            status_before.total_transcripts,
            status_before.accepted_events,
            status_before.attempts_last_24h,
            status_before.cooldown_active,
        )

        logger.info(
            "Calling collect-native-transcripts-overtime with limit=%d...",
            batch_limit,
        )
        collection_result = collect_native_transcripts_overtime(
            limit=batch_limit,
            sleep_seconds=sleep_seconds,
            jitter_seconds=jitter_seconds,
            max_per_creator=max_per_creator,
            min_disk_mb=min_disk_mb,
            stop_on_block=stop_on_block,
            allow_translation=allow_translation,
            creator_diversify=creator_diversify,
            input_csv=None,
            cooldown_hours=cooldown_hours,
            max_daily_attempts=max_daily_attempts,
            undercovered_years_first=True,
            undercovered_creators_first=True,
        )

        batch_result = BatchResult(batch_number=batch_num)
        batch_result.attempted = collection_result.attempted_count
        batch_result.available = collection_result.status_counts.get("available", 0)
        batch_result.no_transcript = collection_result.status_counts.get("no_language", 0)
        batch_result.ip_blocked = collection_result.status_counts.get("ip_blocked", 0)
        batch_result.request_blocked = collection_result.status_counts.get("request_blocked", 0)
        batch_result.rate_limited = collection_result.status_counts.get("rate_limited", 0)
        other = collection_result.attempted_count - sum([
            batch_result.available,
            batch_result.no_transcript,
            batch_result.ip_blocked,
            batch_result.request_blocked,
            batch_result.rate_limited,
        ])
        batch_result.other_errors = max(other, 0)
        batch_result.stopped_reason = collection_result.stopped_reason
        batch_result.transcript_count_after = _get_transcript_count()
        batch_result.free_disk_after = _free_disk_mb()

        result.batches.append(batch_result)
        result.batches_completed = batch_num

        result.total_attempted += batch_result.attempted
        result.total_available += batch_result.available
        result.total_no_transcript += batch_result.no_transcript
        result.total_ip_blocked += batch_result.ip_blocked
        result.total_request_blocked += batch_result.request_blocked
        result.total_rate_limited += batch_result.rate_limited
        result.total_other_errors += batch_result.other_errors

        _log_batch_result(logger, batch_result)

        should_stop, reason = _check_stop_conditions(batch_result)
        if should_stop:
            logger.warning("Stop condition triggered after batch %d: %s", batch_num, reason)
            stop_reason = reason
            stopped = True
            break

        if batch_num < batches:
            logger.info(
                "Sleeping for %.0f seconds between batches...",
                between_batch_sleep_seconds,
            )
            time.sleep(between_batch_sleep_seconds)

    result.ended_at = datetime.now(UTC).isoformat()
    result.ending_transcript_count = _get_transcript_count()
    result.disk_end_mb = _free_disk_mb()

    if rebuild_events_at_end and not dry_run:
        logger.info("Rebuilding transcript events at end of overnight run...")
        try:
            from .transcript_classify import build_transcript_recommendation_events
            from .transcript_exports import export_transcript_events

            event_result = build_transcript_recommendation_events(refresh_existing=True)
            logger.info(
                "Events rebuilt: %d candidate windows, %d events",
                event_result.candidate_windows,
                event_result.events,
            )
            export_transcript_events()
            logger.info("Transcript events exported.")

            try:
                from .transcript_vendor import build_transcript_coverage_bias_report
                build_transcript_coverage_bias_report()
                logger.info("Coverage bias report built.")
            except ImportError:
                logger.info("Coverage bias report not available.")
        except Exception as exc:
            logger.error("Failed to rebuild events: %s", exc)

    result.ending_accepted_events = _get_accepted_events_count()

    block_detected = result.total_ip_blocked > 0 or result.total_request_blocked > 0
    if stop_reason is None:
        result.stopped_reason = "completed_all_batches"
    else:
        result.stopped_reason = stop_reason

    result.recommended_next_action = _compute_recommended_action(
        result.stopped_reason, block_detected,
        result.total_attempted, result.total_available,
    )

    logger.info(
        "Overnight supervisor complete. "
        "Batches: %d/%d, attempted: %d, available: %d, stop: %s",
        result.batches_completed,
        result.batches_requested,
        result.total_attempted,
        result.total_available,
        result.stopped_reason,
    )

    write_final_summary(result, effective_summary_path)
    return result


def _register_signal_handlers() -> None:
    def _cleanup(signum, frame):
        logger.warning("Received signal %s. Cleaning up lock file.", signum)
        release_lock()
        raise SystemExit(1)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)
