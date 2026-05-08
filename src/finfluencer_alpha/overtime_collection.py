from __future__ import annotations

import datetime as _dt
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import get_settings
from .db import connect, init_db
from .youtube_transcripts import (
    _check_disk_space,
    _diversify_by_creator,
    _free_disk_mb,
    _pending_cooldown,
    fetch_transcript_for_video,
    store_transcript_result,
)


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


@dataclass
class OvertimeRun:
    run_id: int
    started_at: str
    ended_at: str | None = None
    command_name: str | None = None
    input_source: str | None = None
    requested_limit: int | None = None
    attempted_count: int = 0
    available_count: int = 0
    no_transcript_count: int = 0
    ip_blocked_count: int = 0
    request_blocked_count: int = 0
    rate_limited_count: int = 0
    other_error_count: int = 0
    stopped_reason: str | None = None
    min_disk_mb: int | None = None
    free_disk_mb_start: float | None = None
    free_disk_mb_end: float | None = None
    sleep_seconds: float | None = None
    jitter_seconds: float | None = None
    max_per_creator: int | None = None
    creator_diversify: bool = False
    allow_translation: bool = False
    notes: str | None = None


@dataclass
class OvertimeCollectionResult:
    run_id: int
    attempted_count: int
    available_count: int
    status_counts: dict[str, int]
    stopped_reason: str | None
    cooldown_blocked: bool = False


@dataclass
class CollectionStatus:
    total_transcripts: int
    native_transcripts: int
    provider_transcripts: int
    candidate_windows: int
    accepted_events: int
    last_run_at: str | None
    last_stopped_reason: str | None
    cooldown_active: bool
    next_safe_run_time: str | None
    attempts_last_24h: int
    successes_last_24h: int
    attempts_24h_success_rate: float
    blocks_last_24h: int
    coverage_by_year: list[dict[str, Any]]
    coverage_by_creator: list[dict[str, Any]]
    recommended_action: str


def _create_run(
    conn,
    command_name: str,
    input_source: str | None,
    requested_limit: int,
    min_disk_mb: int,
    sleep_seconds: float,
    jitter_seconds: float,
    max_per_creator: int | None,
    creator_diversify: bool,
    allow_translation: bool,
) -> int:
    free_start = _free_disk_mb()
    conn.execute(
        """
        INSERT INTO transcript_collection_runs (
          started_at, command_name, input_source, requested_limit,
          min_disk_mb, free_disk_mb_start, sleep_seconds, jitter_seconds,
          max_per_creator, creator_diversify, allow_translation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _utc_now_iso(), command_name, input_source, requested_limit,
            min_disk_mb, free_start, sleep_seconds, jitter_seconds,
            max_per_creator, int(creator_diversify), int(allow_translation),
        ),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _finalize_run(conn, run_id: int, stopped_reason: str | None) -> None:
    counts = dict(
        conn.execute(
            """
            SELECT
              COUNT(*) AS attempted,
              SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) AS available,
              SUM(CASE WHEN status = 'no_language' THEN 1 ELSE 0 END) AS no_transcript,
              SUM(CASE WHEN status = 'ip_blocked' THEN 1 ELSE 0 END) AS ip_blocked,
              SUM(CASE WHEN status = 'request_blocked' THEN 1 ELSE 0 END) AS request_blocked,
              SUM(CASE WHEN status = 'rate_limited' THEN 1 ELSE 0 END) AS rate_limited,
              SUM(CASE WHEN status NOT IN (
                'available', 'no_language', 'ip_blocked', 'request_blocked', 'rate_limited'
              ) THEN 1 ELSE 0 END) AS other_error
            FROM transcript_collection_attempts
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    )
    conn.execute(
        """
        UPDATE transcript_collection_runs SET
          ended_at = ?, attempted_count = ?, available_count = ?,
          no_transcript_count = ?, ip_blocked_count = ?, request_blocked_count = ?,
          rate_limited_count = ?, other_error_count = ?,
          stopped_reason = ?, free_disk_mb_end = ?
        WHERE run_id = ?
        """,
        (
            _utc_now_iso(),
            counts["attempted"], counts["available"],
            counts["no_transcript"], counts["ip_blocked"],
            counts["request_blocked"], counts["rate_limited"],
            counts["other_error"],
            stopped_reason, _free_disk_mb(),
            run_id,
        ),
    )
    conn.commit()


def _log_attempt(
    conn,
    run_id: int,
    video_id: str,
    creator: str | None,
    published_at: str | None,
    ticker_signal_count: int | None,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
    transcript_source: str | None = None,
    provider_name: str | None = None,
    retrieval_method: str | None = None,
    is_asr_generated: int | None = None,
    language: str | None = None,
    source_confidence: float | None = None,
    word_count: int | None = None,
    segment_count: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO transcript_collection_attempts (
          run_id, video_id, creator, published_at, ticker_signal_count,
          attempted_at, status, error_type, error_message,
          transcript_source, provider_name, retrieval_method,
          is_asr_generated, language, source_confidence,
          word_count, segment_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, video_id, creator, published_at, ticker_signal_count,
            _utc_now_iso(), status, error_type, error_message,
            transcript_source, provider_name, retrieval_method,
            is_asr_generated, language, source_confidence,
            word_count, segment_count,
        ),
    )


def _last_block_time(conn, cooldown_hours: int) -> _dt.datetime | None:
    row = conn.execute(
        """
        SELECT started_at, stopped_reason FROM transcript_collection_runs
        WHERE stopped_reason IN ('ip_blocked', 'request_blocked')
        ORDER BY started_at DESC LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    try:
        return _dt.datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _cooldown_active(conn, cooldown_hours: int) -> bool:
    last = _last_block_time(conn, cooldown_hours)
    if last is None:
        return False
    return _dt.datetime.now(_dt.UTC) < (last + _dt.timedelta(hours=cooldown_hours))


def _next_safe_run_time(conn, cooldown_hours: int) -> _dt.datetime | None:
    last = _last_block_time(conn, cooldown_hours)
    if last is None:
        return _dt.datetime.now(_dt.UTC)
    return last + _dt.timedelta(hours=cooldown_hours)


def _attempts_last_24h(conn) -> dict[str, int]:
    cutoff = (_dt.datetime.now(_dt.UTC) - _dt.timedelta(hours=24)).isoformat()
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) AS successes,
          SUM(CASE WHEN status IN ('ip_blocked', 'request_blocked', 'rate_limited') THEN 1 ELSE 0 END) AS blocks
        FROM transcript_collection_attempts
        WHERE attempted_at >= ?
        """,
        (cutoff,),
    ).fetchone()
    return {
        "total": row["total"] or 0,
        "successes": row["successes"] or 0,
        "blocks": row["blocks"] or 0,
    }


def _max_daily_attempts_reached(conn, max_daily: int) -> bool:
    stats = _attempts_last_24h(conn)
    return stats["total"] >= max_daily


def _undercovered_years(conn) -> list[str]:
    rows = conn.execute(
        """
        SELECT strftime('%Y', rv.published_at) AS year
        FROM raw_youtube_videos rv
        WHERE COALESCE(rv.excluded_flag, 0) = 0
          AND rv.published_at IS NOT NULL
          AND rv.video_id NOT IN (
            SELECT video_id FROM youtube_transcripts WHERE status = 'available'
          )
        GROUP BY year
        ORDER BY COUNT(*) DESC
        """
    ).fetchall()
    return [r["year"] for r in rows]


def _undercovered_creators(conn, limit: int = 30) -> list[str]:
    rows = conn.execute(
        """
        SELECT rv.channel_title
        FROM raw_youtube_videos rv
        WHERE COALESCE(rv.excluded_flag, 0) = 0
          AND rv.video_id NOT IN (
            SELECT video_id FROM youtube_transcripts WHERE status = 'available'
          )
        GROUP BY rv.channel_title
        ORDER BY COUNT(*) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [r["channel_title"] for r in rows]


def _eligible_from_queue(
    conn,
    limit: int,
    undercovered_years_first: bool,
    undercovered_creators_first: bool,
    cooldown_hours: int,
) -> list[Any]:
    if undercovered_years_first or undercovered_creators_first:
        undercovered_yr = set(_undercovered_years(conn)) if undercovered_years_first else set()
        undercovered_cr = set(_undercovered_creators(conn)) if undercovered_creators_first else set()

    rows = conn.execute(
        """
        SELECT tfq.video_id, tfq.channel_title, tfq.published_at, tfq.title,
               tfq.transcript_status, tfq.attempt_count,
               tfq.next_eligible_attempt_at,
               rv.description
        FROM transcript_fetch_queue tfq
        JOIN raw_youtube_videos rv ON rv.video_id = tfq.video_id
        WHERE COALESCE(rv.excluded_flag, 0) = 0
          AND (
            tfq.transcript_status IS NULL
            OR tfq.transcript_status IN ('error', 'rate_limited', 'no_language')
          )
        ORDER BY tfq.priority_score DESC, tfq.published_at DESC
        LIMIT ?
        """,
        (limit * 4,),
    ).fetchall()

    eligible = [
        row for row in rows
        if not _pending_cooldown(row, cooldown_hours)
    ]

    if undercovered_years_first or undercovered_creators_first:
        def _boost(row) -> float:
            boost = 0.0
            if undercovered_yr:
                year = (row["published_at"] or "")[:4]
                if year in undercovered_yr:
                    boost += 100.0
            if undercovered_cr:
                creator = row["channel_title"] or ""
                if creator in undercovered_cr:
                    boost += 50.0
            return boost

        eligible.sort(key=lambda r: _boost(r), reverse=True)

    return eligible


def collect_native_transcripts_overtime(
    limit: int = 20,
    sleep_seconds: float = 20.0,
    jitter_seconds: float = 10.0,
    max_per_creator: int = 3,
    min_disk_mb: int = 500,
    stop_on_block: bool = True,
    allow_translation: bool = False,
    creator_diversify: bool = True,
    input_csv: Path | None = None,
    cooldown_hours: int = 24,
    max_daily_attempts: int = 50,
    undercovered_years_first: bool = True,
    undercovered_creators_first: bool = True,
) -> OvertimeCollectionResult:
    settings = get_settings()
    init_db()

    if not _check_disk_space(min_disk_mb):
        return OvertimeCollectionResult(
            run_id=-1, attempted_count=0, available_count=0,
            status_counts={}, stopped_reason=f"disk_below_{min_disk_mb}mb",
        )

    with connect() as conn:
        if _cooldown_active(conn, cooldown_hours):
            return OvertimeCollectionResult(
                run_id=-1, attempted_count=0, available_count=0,
                status_counts={}, stopped_reason="cooldown_active",
                cooldown_blocked=True,
            )

        if _max_daily_attempts_reached(conn, max_daily_attempts):
            return OvertimeCollectionResult(
                run_id=-1, attempted_count=0, available_count=0,
                status_counts={}, stopped_reason="max_daily_attempts",
            )

        if input_csv and input_csv.exists():
            from .youtube_transcripts import seed_transcript_queue_from_csv
            seed_transcript_queue_from_csv(conn, input_csv)

        run_id = _create_run(
            conn,
            command_name="collect-native-transcripts-overtime",
            input_source=str(input_csv) if input_csv else None,
            requested_limit=limit,
            min_disk_mb=min_disk_mb,
            sleep_seconds=sleep_seconds,
            jitter_seconds=jitter_seconds,
            max_per_creator=max_per_creator,
            creator_diversify=creator_diversify,
            allow_translation=allow_translation,
        )

        eligible = _eligible_from_queue(
            conn, limit,
            undercovered_years_first=undercovered_years_first,
            undercovered_creators_first=undercovered_creators_first,
            cooldown_hours=cooldown_hours,
        )

        if creator_diversify and max_per_creator > 0:
            eligible = _diversify_by_creator(eligible, limit, max_per_creator)
        else:
            eligible = eligible[:limit]

        attempted = 0
        status_counts: dict[str, int] = {}
        rate_limit_errors = 0
        stopped_reason: str | None = None

        for row in eligible:
            if not _check_disk_space(min_disk_mb):
                stopped_reason = f"disk_below_{min_disk_mb}mb"
                break

            if sleep_seconds > 0 and attempted > 0:
                jitter = random.uniform(0, jitter_seconds)
                time.sleep(sleep_seconds + jitter)

            attempts_for_video = 0
            while attempts_for_video < 2:
                attempts_for_video += 1
                attempted += 1
                result = fetch_transcript_for_video(
                    row["video_id"],
                    languages=settings.youtube_transcript_language_list,
                    allow_translation=allow_translation,
                )
                store_transcript_result(conn, result)
                conn.execute(
                    """
                    UPDATE transcript_fetch_queue SET
                      transcript_status = ?,
                      attempt_count = attempt_count + 1,
                      last_attempted_at = ?
                    WHERE video_id = ?
                    """,
                    (result.status, _dt.datetime.now(_dt.UTC).isoformat(), row["video_id"]),
                )

                word_count = len((result.full_text or "").split()) if result.full_text else None
                _log_attempt(
                    conn, run_id,
                    video_id=row["video_id"],
                    creator=row["channel_title"],
                    published_at=row["published_at"],
                    ticker_signal_count=None,
                    status=result.status,
                    error_type=result.error_type,
                    error_message=result.error_message,
                    transcript_source=result.transcript_source,
                    provider_name=result.provider_name,
                    retrieval_method=result.retrieval_method,
                    is_asr_generated=int(result.is_asr_generated) if result.is_asr_generated is not None else None,
                    language=result.language,
                    source_confidence=result.source_confidence,
                    word_count=word_count,
                    segment_count=result.segment_count,
                )
                conn.commit()
                status_counts[result.status] = status_counts.get(result.status, 0) + 1

                if result.status in ("ip_blocked", "request_blocked") and stop_on_block:
                    conn.execute(
                        """
                        UPDATE transcript_fetch_queue SET
                          next_eligible_attempt_at = ?
                        WHERE video_id = ?
                        """,
                        (
                            (_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=cooldown_hours)).isoformat(),
                            row["video_id"],
                        ),
                    )
                    conn.commit()
                    stopped_reason = result.status
                    break

                if result.status == "rate_limited" and attempts_for_video == 1:
                    rate_limit_errors += 1
                    if rate_limit_errors >= settings.max_rate_limit_errors_per_run:
                        stopped_reason = "rate_limited"
                        break
                    backoff = min(60.0, (2.0 ** max(rate_limit_errors - 1, 0)) + random.uniform(0, 1))
                    time.sleep(backoff)
                    continue

                if result.status == "rate_limited":
                    rate_limit_errors += 1
                    if rate_limit_errors >= settings.max_rate_limit_errors_per_run:
                        stopped_reason = "rate_limited"
                    break

                break

            if stopped_reason:
                break

        _finalize_run(conn, run_id, stopped_reason)
        return OvertimeCollectionResult(
            run_id=run_id,
            attempted_count=attempted,
            available_count=status_counts.get("available", 0),
            status_counts=status_counts,
            stopped_reason=stopped_reason,
        )


def transcript_collection_status() -> CollectionStatus:
    init_db()
    with connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM youtube_transcripts"
        ).fetchone()[0]
        native = conn.execute(
            "SELECT COUNT(*) FROM youtube_transcripts WHERE transcript_source = 'youtube' AND status = 'available'"
        ).fetchone()[0]
        provider = conn.execute(
            "SELECT COUNT(*) FROM youtube_transcripts WHERE transcript_source = 'external_provider' AND status = 'available'"
        ).fetchone()[0]
        windows = conn.execute(
            "SELECT COUNT(*) FROM transcript_candidate_windows"
        ).fetchone()[0]
        events = conn.execute(
            "SELECT COUNT(*) FROM transcript_recommendation_events"
        ).fetchone()[0]

        last_run = conn.execute(
            """
            SELECT started_at, stopped_reason
            FROM transcript_collection_runs
            ORDER BY started_at DESC LIMIT 1
            """
        ).fetchone()

        last_run_at = last_run["started_at"] if last_run else None
        last_stopped_reason = last_run["stopped_reason"] if last_run else None

        cooldown_hours = get_settings().transcript_queue_cooldown_hours
        _cooldown = _cooldown_active(conn, cooldown_hours)
        _next_safe = _next_safe_run_time(conn, cooldown_hours)

        stats_24h = _attempts_last_24h(conn)
        total_24h = stats_24h["total"]
        successes_24h = stats_24h["successes"]
        blocks_24h = stats_24h["blocks"]
        rate_24h = successes_24h / total_24h if total_24h > 0 else 0.0

        coverage_year = [
            dict(r)
            for r in conn.execute(
                """
                SELECT strftime('%Y', rv.published_at) AS year,
                       COUNT(yt.video_id) AS covered,
                       COUNT(*) - COUNT(yt.video_id) AS uncovered,
                       COUNT(*) AS total
                FROM raw_youtube_videos rv
                LEFT JOIN youtube_transcripts yt ON yt.video_id = rv.video_id AND yt.status = 'available'
                WHERE COALESCE(rv.excluded_flag, 0) = 0 AND rv.published_at IS NOT NULL
                GROUP BY year ORDER BY year
                """
            ).fetchall()
        ]

        coverage_creator = [
            dict(r)
            for r in conn.execute(
                """
                SELECT rv.channel_title AS creator,
                       COUNT(yt.video_id) AS covered,
                       COUNT(*) - COUNT(yt.video_id) AS uncovered,
                       COUNT(*) AS total
                FROM raw_youtube_videos rv
                LEFT JOIN youtube_transcripts yt ON yt.video_id = rv.video_id AND yt.status = 'available'
                WHERE COALESCE(rv.excluded_flag, 0) = 0
                GROUP BY rv.channel_title
                ORDER BY (CAST(COUNT(yt.video_id) AS REAL) / COUNT(*)) ASC, COUNT(*) DESC
                LIMIT 20
                """
            ).fetchall()
        ]

        if _cooldown:
            action = "WAIT FOR COOLDOWN"
        elif blocks_24h > 0:
            action = "WAIT AT LEAST 2 HOURS"
        elif total_24h >= 40:
            action = "WAIT UNTIL TOMORROW"
        elif total < 500:
            action = "RUN SMALL OVERTIME BATCH"
        else:
            action = "MOVE TO CLASSIFIER TRAINING"

        return CollectionStatus(
            total_transcripts=total,
            native_transcripts=native,
            provider_transcripts=provider,
            candidate_windows=windows,
            accepted_events=events,
            last_run_at=last_run_at,
            last_stopped_reason=last_stopped_reason,
            cooldown_active=_cooldown,
            next_safe_run_time=_next_safe.isoformat() if _next_safe else None,
            attempts_last_24h=total_24h,
            successes_last_24h=successes_24h,
            attempts_24h_success_rate=rate_24h,
            blocks_last_24h=blocks_24h,
            coverage_by_year=coverage_year,
            coverage_by_creator=coverage_creator,
            recommended_action=action,
        )
