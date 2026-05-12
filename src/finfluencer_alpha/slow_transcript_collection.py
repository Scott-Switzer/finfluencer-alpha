from __future__ import annotations

import csv
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)

try:
    from youtube_transcript_api._errors import TooManyRequests
except ImportError:

    class TooManyRequests(Exception):
        pass

from .config import (
    EXPORTS_DIR,
    IMPORTS_DIR,
    clear_settings_cache,
    ensure_data_dirs,
    get_settings,
)
from .db import connect, init_db
from .utils import configure_csv_field_size_limit
from .youtube_transcripts import (
    BLOCKED_TRANSCRIPT_STATUSES,
    PERMANENT_NO_TRANSCRIPT_STATUSES,
    fetch_transcript_for_video,
    store_transcript_result,
)

TRANSCRIPTS_EXPORT_DIR = EXPORTS_DIR / "transcripts"
DEFAULT_SLOW_QUEUE_PATH = TRANSCRIPTS_EXPORT_DIR / "slow_youtube_transcript_queue.csv"
DEFAULT_SLOW_QUEUE_MD_PATH = TRANSCRIPTS_EXPORT_DIR / "slow_youtube_transcript_queue.md"
DEFAULT_SLOW_SUMMARY_CSV_PATH = TRANSCRIPTS_EXPORT_DIR / "slow_youtube_collection_summary.csv"
DEFAULT_SLOW_SUMMARY_MD_PATH = TRANSCRIPTS_EXPORT_DIR / "slow_youtube_collection_summary.md"
DEFAULT_MANUAL_PACKET_PATH = TRANSCRIPTS_EXPORT_DIR / "manual_collection_packet.csv"
DEFAULT_MANUAL_PACKET_MD_PATH = TRANSCRIPTS_EXPORT_DIR / "manual_collection_packet.md"
DEFAULT_MANUAL_TEMPLATE_PATH = IMPORTS_DIR / "manual_transcripts_template.csv"
DEFAULT_DAILY_PLAN_PATH = TRANSCRIPTS_EXPORT_DIR / "slow_collection_daily_plan.md"

SLOW_QUEUE_COLUMNS = [
    "queue_rank",
    "video_id",
    "title",
    "channel_title",
    "published_at",
    "year",
    "creator_type",
    "current_transcript_status",
    "previous_failure_status",
    "priority_reason",
    "recommended_batch",
]

MANUAL_PACKET_COLUMNS = [
    "packet_rank",
    "video_id",
    "title",
    "channel_title",
    "upload_date",
    "year",
    "youtube_url",
    "selected_reason",
    "transcript_text",
    "transcript_source",
    "collector_notes",
]

SLOW_SUMMARY_COLUMNS = [
    "run_id",
    "started_at",
    "ended_at",
    "input_file",
    "max_videos",
    "delay_seconds",
    "attempted",
    "imported",
    "skipped_existing",
    "terminal_failures",
    "transient_failures",
    "block_detected",
    "stop_reason",
    "fallback_triggered",
    "fallback_route",
    "remaining_queue_count",
    "recommended_next_command",
]


@dataclass(frozen=True)
class SlowQueueResult:
    queue_path: Path
    summary_md_path: Path
    queue_size: int
    year_breakdown: dict[str, int]
    creator_breakdown: dict[str, int]


@dataclass(frozen=True)
class SlowCollectionResult:
    summary_csv_path: Path
    summary_md_path: Path
    run_id: str
    attempted: int
    imported: int
    skipped_existing: int
    terminal_failures: int
    transient_failures: int
    block_detected: bool
    stop_reason: str | None
    fallback_triggered: bool
    fallback_route: str | None
    remaining_queue_count: int
    recommended_next_command: str


@dataclass(frozen=True)
class ManualPacketResult:
    packet_csv_path: Path
    packet_md_path: Path
    template_path: Path
    packet_size: int
    year_breakdown: dict[str, int]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _error_status(exc: BaseException) -> str:
    if isinstance(exc, IpBlocked):
        return "ip_blocked"
    if isinstance(exc, RequestBlocked):
        return "request_blocked"
    if isinstance(exc, TooManyRequests):
        return "rate_limited"
    if isinstance(exc, TranscriptsDisabled):
        return "disabled"
    if isinstance(exc, NoTranscriptFound):
        return "no_language"
    if isinstance(exc, VideoUnavailable):
        return "unavailable"
    text = str(exc).lower()
    if "429" in text or "too many requests" in text:
        return "rate_limited"
    return "error"


def _is_block_status(status: str) -> bool:
    return status in BLOCKED_TRANSCRIPT_STATUSES


def _is_terminal_no_transcript(status: str) -> bool:
    return status in PERMANENT_NO_TRANSCRIPT_STATUSES or status in ("no_language", "disabled", "unavailable")


def _is_transient(status: str) -> bool:
    return status in ("error", "rate_limited", "timeout", "parse_error")


def _creator_type(channel_title: str | None, creator_taxonomy: dict[str, str]) -> str:
    return creator_taxonomy.get(_clean(channel_title).lower(), "unknown")


def _load_creator_taxonomy(conn: Any) -> dict[str, str]:
    rows = conn.execute(
        "SELECT handle_or_channel, initial_category FROM creator_taxonomy WHERE platform = 'youtube'"
    ).fetchall()
    return {_clean(row["handle_or_channel"]).lower(): _clean(row["initial_category"]) for row in rows}


def plan_slow_youtube_transcript_queue(
    *,
    start_year: int = 2020,
    end_year: int = 2023,
    max_videos: int = 724,
    database_url: str | None = None,
    exclude_permanent_failures: bool = True,
    output_path: Path = DEFAULT_SLOW_QUEUE_PATH,
    summary_md_path: Path = DEFAULT_SLOW_QUEUE_MD_PATH,
) -> SlowQueueResult:
    ensure_data_dirs()
    resolved_db_url, _ = _resolve_database_url(database_url)
    init_db(database_url=resolved_db_url)
    with connect(database_url=resolved_db_url) as conn:
        creator_taxonomy = _load_creator_taxonomy(conn)
        start_date = f"{start_year}-01-01T00:00:00Z"
        end_date = f"{end_year}-12-31T23:59:59Z"

        exclude_statuses = ["available"]
        if exclude_permanent_failures:
            exclude_statuses.extend(PERMANENT_NO_TRANSCRIPT_STATUSES)
            exclude_statuses.append("no_language")

        rows = conn.execute(
            f"""
            SELECT
              rv.video_id,
              rv.title,
              rv.channel_title,
              rv.published_at,
              COALESCE(yt.status, 'missing') AS transcript_status,
              yt.error_type AS previous_error
            FROM raw_youtube_videos rv
            LEFT JOIN youtube_transcripts yt ON yt.video_id = rv.video_id
            WHERE rv.published_at >= ?
              AND rv.published_at <= ?
              AND COALESCE(rv.excluded_flag, 0) = 0
              AND COALESCE(yt.status, 'missing') NOT IN ({','.join('?' for _ in exclude_statuses)})
            ORDER BY rv.published_at ASC, rv.video_id
            """,
            (start_date, end_date, *exclude_statuses),
        ).fetchall()

    output_rows: list[dict[str, Any]] = []
    year_counts: dict[str, int] = {}
    creator_counts: dict[str, int] = {}
    rank = 0
    for row in rows:
        video_id = _clean(row["video_id"])
        status = _clean(row["transcript_status"])
        year = _clean(row["published_at"])[:4] if row["published_at"] else "unknown"
        channel = _clean(row["channel_title"])
        ctype = _creator_type(channel, creator_taxonomy)
        rank += 1
        if rank > max_videos:
            break
        year_counts[year] = year_counts.get(year, 0) + 1
        creator_counts[channel] = creator_counts.get(channel, 0) + 1
        output_rows.append(
            {
                "queue_rank": rank,
                "video_id": video_id,
                "title": _clean(row["title"]),
                "channel_title": channel,
                "published_at": _clean(row["published_at"]),
                "year": year,
                "creator_type": ctype,
                "current_transcript_status": status,
                "previous_failure_status": _clean(row["previous_error"]) or "",
                "priority_reason": f"older_year:{year}",
                "recommended_batch": f"batch_{(rank - 1) // 25 + 1}",
            }
        )

    _write_csv(output_path, output_rows, SLOW_QUEUE_COLUMNS)
    lines = [
        "# Slow YouTube Transcript Queue",
        "",
        f"- Period: {start_year}-{end_year}",
        f"- Max videos planned: {max_videos}",
        f"- Videos in queue: {len(output_rows)}",
        f"- Permanent failures excluded: {exclude_permanent_failures}",
        "",
        "## Year Breakdown",
        "",
    ]
    for year in sorted(year_counts):
        lines.append(f"- {year}: {year_counts[year]}")
    lines.extend(["", "## Creator Breakdown (top 10)", ""])
    for creator, count in sorted(creator_counts.items(), key=lambda x: (-x[1], x[0]))[:10]:
        lines.append(f"- {creator}: {count}")
    lines.extend(["", "## Recommended Next Command", ""])
    lines.append(
        "```bash\n"
        "python3 -m finfluencer_alpha collect-youtube-transcripts-slow \n"
        "  --input data/exports/transcripts/slow_youtube_transcript_queue.csv \n"
        "  --max-videos 25 \n"
        "  --delay-seconds 45 \n"
        "  --stop-on-block \n"
        "  --database-url sqlite:///data/finfluencer_alpha.db \n"
        "  --confirm-run\n"
        "```"
    )
    summary_md_path.parent.mkdir(parents=True, exist_ok=True)
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return SlowQueueResult(
        queue_path=output_path,
        summary_md_path=summary_md_path,
        queue_size=len(output_rows),
        year_breakdown=year_counts,
        creator_breakdown=creator_counts,
    )


def refresh_slow_youtube_transcript_queue(
    *,
    database_url: str | None = None,
    output_path: Path = DEFAULT_SLOW_QUEUE_PATH,
    summary_md_path: Path = DEFAULT_SLOW_QUEUE_MD_PATH,
) -> SlowQueueResult:
    return plan_slow_youtube_transcript_queue(
        start_year=2020,
        end_year=2023,
        max_videos=724,
        database_url=database_url,
        exclude_permanent_failures=True,
        output_path=output_path,
        summary_md_path=summary_md_path,
    )


def _looks_like_temp_db(url: str) -> bool:
    lowered = url.lower()
    return any(
        fragment in lowered
        for fragment in ("/tmp/", "/temp/", "/var/folders/", "pytest", "_tmp")
    )


def _resolve_database_url(explicit_url: str | None = None) -> tuple[str, bool]:
    clear_settings_cache()
    if explicit_url:
        return explicit_url, False

    resolved = get_settings().database_url
    using_default = False

    if resolved.startswith("sqlite:///"):
        from .config import PROJECT_ROOT

        raw_path = resolved.replace("sqlite:///", "", 1)
        path = Path(raw_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists() and _looks_like_temp_db(resolved):
            fallback = "sqlite:///data/finfluencer_alpha.db"
            resolved = fallback
            using_default = True

    return resolved, using_default


def collect_youtube_transcripts_slow(
    *,
    input_path: Path = DEFAULT_SLOW_QUEUE_PATH,
    max_videos: int = 10,
    delay_seconds: float = 60.0,
    stop_on_block: bool = True,
    confirm_run: bool = False,
    allow_overwrite: bool = False,
    allow_translation: bool = True,
    database_url: str | None = None,
    output_summary_csv: Path = DEFAULT_SLOW_SUMMARY_CSV_PATH,
    output_summary_md: Path = DEFAULT_SLOW_SUMMARY_MD_PATH,
) -> SlowCollectionResult:
    ensure_data_dirs()
    queue_rows = _read_csv(input_path)
    if not queue_rows:
        raise ValueError(f"Queue input is empty: {input_path}")

    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    if not confirm_run:
        return SlowCollectionResult(
            summary_csv_path=output_summary_csv,
            summary_md_path=output_summary_md,
            run_id=run_id,
            attempted=0,
            imported=0,
            skipped_existing=0,
            terminal_failures=0,
            transient_failures=0,
            block_detected=False,
            stop_reason="dry_run",
            fallback_triggered=False,
            fallback_route=None,
            remaining_queue_count=len(queue_rows),
            recommended_next_command="Re-run with --confirm-run to collect transcripts",
        )

    resolved_db_url, using_default_db = _resolve_database_url(database_url)
    init_db(database_url=resolved_db_url)
    settings = get_settings()
    languages = settings.youtube_transcript_language_list

    attempted = 0
    imported = 0
    skipped_existing = 0
    terminal_failures = 0
    transient_failures = 0
    block_detected = False
    stop_reason: str | None = None
    fallback_triggered = False
    fallback_route: str | None = None

    with connect(database_url=resolved_db_url) as conn:
        conn.execute(
            """
            INSERT INTO transcript_collection_runs (
              started_at, command_name, input_source, requested_limit,
              sleep_seconds, allow_translation
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                started_at,
                "collect-youtube-transcripts-slow",
                str(input_path),
                max_videos,
                delay_seconds,
                int(allow_translation),
            ),
        )
        run_db_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for row in queue_rows[:max_videos]:
            if stop_reason:
                break

            video_id = _clean(row.get("video_id"))
            if not video_id:
                continue

            if delay_seconds > 0 and attempted > 0:
                time.sleep(delay_seconds)

            attempted += 1

            existing = conn.execute(
                "SELECT status FROM youtube_transcripts WHERE video_id = ?",
                (video_id,),
            ).fetchone()

            if existing and existing["status"] == "available" and not allow_overwrite:
                skipped_existing += 1
                conn.execute(
                    """
                    INSERT INTO transcript_collection_attempts (
                      run_id, video_id, attempted_at, status,
                      transcript_source, provider_name, retrieval_method
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_db_id,
                        video_id,
                        datetime.now(UTC).isoformat(),
                        "skipped_existing",
                        "youtube",
                        settings.youtube_transcript_provider,
                        "slow_collection_skip",
                    ),
                )
                conn.commit()
                continue

            result = fetch_transcript_for_video(
                video_id,
                languages=languages,
                allow_translation=allow_translation,
            )

            if result.status == "available":
                store_transcript_result(conn, result)
                imported += 1
            else:
                conn.execute(
                    """
                    INSERT INTO youtube_transcripts (
                      video_id, transcript_source, retrieval_method, retrieval_status,
                      provider_name, provider_version, status, error_type, error_message,
                      collected_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                      status = excluded.status,
                      error_type = excluded.error_type,
                      error_message = excluded.error_message,
                      collected_at = excluded.collected_at
                    """,
                    (
                        video_id,
                        "youtube",
                        "youtube_transcript_api",
                        result.status,
                        settings.youtube_transcript_provider,
                        result.provider_version or "unknown",
                        result.status,
                        result.error_type,
                        result.error_message,
                        datetime.now(UTC).isoformat(),
                    ),
                )

            conn.execute(
                """
                INSERT INTO transcript_collection_attempts (
                  run_id, video_id, attempted_at, status,
                  error_type, error_message,
                  transcript_source, provider_name, retrieval_method,
                  word_count, segment_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_db_id,
                    video_id,
                    datetime.now(UTC).isoformat(),
                    result.status,
                    result.error_type,
                    result.error_message,
                    "youtube",
                    settings.youtube_transcript_provider,
                    result.retrieval_method or "youtube_transcript_api",
                    result.word_count,
                    result.segment_count,
                ),
            )
            conn.commit()

            if _is_block_status(result.status):
                block_detected = True
                if stop_on_block:
                    stop_reason = result.status
                    fallback_triggered = True
                    fallback_route = "manual_packet_after_block"
                    break

            if _is_terminal_no_transcript(result.status):
                terminal_failures += 1

            if _is_transient(result.status):
                transient_failures += 1
                if transient_failures >= 3:
                    stop_reason = "repeated_transient_errors"
                    fallback_triggered = True
                    fallback_route = "manual_packet_after_transient"
                    break

        conn.execute(
            """
            UPDATE transcript_collection_runs SET
              ended_at = ?,
              attempted_count = ?,
              available_count = ?,
              no_transcript_count = ?,
              ip_blocked_count = ?,
              request_blocked_count = ?,
              rate_limited_count = ?,
              other_error_count = ?,
              stopped_reason = ?
            WHERE run_id = ?
            """,
            (
                datetime.now(UTC).isoformat(),
                attempted,
                imported,
                terminal_failures,
                1 if stop_reason == "ip_blocked" else 0,
                1 if stop_reason == "request_blocked" else 0,
                transient_failures,
                terminal_failures,
                stop_reason,
                run_db_id,
            ),
        )
        conn.commit()

    ended_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    remaining = max(0, len(queue_rows) - attempted)

    if fallback_triggered:
        recommended_next = (
            f"python3 -m finfluencer_alpha build-manual-transcript-collection-packet "
            f"--input {input_path} --max-videos 100"
        )
    else:
        recommended_next = (
            f"python3 -m finfluencer_alpha collect-youtube-transcripts-slow "
            f"--input {input_path} --max-videos 25 --delay-seconds 60 --stop-on-block --confirm-run"
        )

    summary_row = {
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "input_file": str(input_path),
        "max_videos": max_videos,
        "delay_seconds": delay_seconds,
        "attempted": attempted,
        "imported": imported,
        "skipped_existing": skipped_existing,
        "terminal_failures": terminal_failures,
        "transient_failures": transient_failures,
        "block_detected": block_detected,
        "stop_reason": stop_reason or "completed",
        "fallback_triggered": fallback_triggered,
        "fallback_route": fallback_route or "",
        "remaining_queue_count": remaining,
        "recommended_next_command": recommended_next,
    }
    _write_csv(output_summary_csv, [summary_row], SLOW_SUMMARY_COLUMNS)

    lines = [
        "# Slow YouTube Transcript Collection Summary",
        "",
        f"- Run ID: `{run_id}`",
        f"- Started: {started_at}",
        f"- Ended: {ended_at}",
        f"- Input: `{input_path}`",
        f"- Resolved database URL: `{resolved_db_url}`",
        f"- Database path exists: {Path(resolved_db_url.replace('sqlite:///', '')).exists() if resolved_db_url.startswith('sqlite:///') else 'N/A'}",
        f"- Using default database: {using_default_db}",
        f"- Max videos requested: {max_videos}",
        f"- Delay seconds: {delay_seconds}",
        f"- Attempted: {attempted}",
        f"- Imported: {imported}",
        f"- Skipped existing: {skipped_existing}",
        f"- Terminal failures: {terminal_failures}",
        f"- Transient failures: {transient_failures}",
        f"- Block detected: {block_detected}",
        f"- Stop reason: {stop_reason or 'completed'}",
        f"- Fallback triggered: {fallback_triggered}",
        f"- Fallback route: {fallback_route or 'N/A'}",
        f"- Remaining in queue: {remaining}",
        "",
        "## Recommended Next Step",
        "",
        f"```bash\n{recommended_next}\n```",
        "",
    ]
    output_summary_md.parent.mkdir(parents=True, exist_ok=True)
    output_summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return SlowCollectionResult(
        summary_csv_path=output_summary_csv,
        summary_md_path=output_summary_md,
        run_id=run_id,
        attempted=attempted,
        imported=imported,
        skipped_existing=skipped_existing,
        terminal_failures=terminal_failures,
        transient_failures=transient_failures,
        block_detected=block_detected,
        stop_reason=stop_reason,
        fallback_triggered=fallback_triggered,
        fallback_route=fallback_route,
        remaining_queue_count=remaining,
        recommended_next_command=recommended_next,
    )


def build_manual_transcript_collection_packet(
    *,
    input_path: Path = DEFAULT_SLOW_QUEUE_PATH,
    max_videos: int = 100,
    output_packet_csv: Path = DEFAULT_MANUAL_PACKET_PATH,
    output_packet_md: Path = DEFAULT_MANUAL_PACKET_MD_PATH,
    output_template_csv: Path = DEFAULT_MANUAL_TEMPLATE_PATH,
) -> ManualPacketResult:
    ensure_data_dirs()
    queue_rows = _read_csv(input_path)
    if not queue_rows:
        raise ValueError(f"Queue input is empty: {input_path}")

    packet_rows: list[dict[str, Any]] = []
    year_counts: dict[str, int] = {}
    rank = 0
    for row in queue_rows:
        if rank >= max_videos:
            break
        video_id = _clean(row.get("video_id"))
        if not video_id:
            continue
        status = _clean(row.get("current_transcript_status"))
        if status == "available":
            continue
        year = _clean(row.get("year")) or "unknown"
        rank += 1
        year_counts[year] = year_counts.get(year, 0) + 1
        packet_rows.append(
            {
                "packet_rank": rank,
                "video_id": video_id,
                "title": _clean(row.get("title")),
                "channel_title": _clean(row.get("channel_title")),
                "upload_date": _clean(row.get("published_at")),
                "year": year,
                "youtube_url": _video_url(video_id),
                "selected_reason": _clean(row.get("priority_reason")),
                "transcript_text": "",
                "transcript_source": "manual_public_transcript_surface",
                "collector_notes": "Fill transcript_text manually from YouTube public captions or auto-generated transcript.",
            }
        )

    _write_csv(output_packet_csv, packet_rows, MANUAL_PACKET_COLUMNS)
    _write_csv(output_template_csv, packet_rows, MANUAL_PACKET_COLUMNS)

    lines = [
        "# Manual Transcript Collection Packet",
        "",
        f"- Source queue: `{input_path}`",
        f"- Videos in packet: {len(packet_rows)}",
        "",
        "## Year Breakdown",
        "",
    ]
    for year in sorted(year_counts):
        lines.append(f"- {year}: {year_counts[year]}")
    lines.extend(
        [
            "",
            "## Instructions",
            "",
            "1. Open each YouTube URL.",
            "2. Click the transcript/CC button below the video.",
            "3. Copy the transcript text into the `transcript_text` column.",
            "4. Save the filled CSV as `data/imports/manual_transcripts_filled.csv`.",
            "5. Run: `python3 -m finfluencer_alpha import-manual-transcripts`",
            "",
            f"- Packet CSV: `{output_packet_csv}`",
            f"- Template CSV: `{output_template_csv}`",
        ]
    )
    output_packet_md.parent.mkdir(parents=True, exist_ok=True)
    output_packet_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return ManualPacketResult(
        packet_csv_path=output_packet_csv,
        packet_md_path=output_packet_md,
        template_path=output_template_csv,
        packet_size=len(packet_rows),
        year_breakdown=year_counts,
    )


def build_slow_collection_daily_plan(
    *,
    output_path: Path = DEFAULT_DAILY_PLAN_PATH,
) -> Path:
    lines = [
        "# Slow Collection Daily Plan",
        "",
        "## Conservative 10-Video Test Run",
        "",
        "```bash",
        "python3 -m finfluencer_alpha collect-youtube-transcripts-slow \\",
        "  --input data/exports/transcripts/slow_youtube_transcript_queue.csv \\",
        "  --max-videos 10 \\",
        "  --delay-seconds 60 \\",
        "  --stop-on-block \\",
        "  --confirm-run",
        "```",
        "",
        "## Normal 25-Video Run",
        "",
        "```bash",
        "python3 -m finfluencer_alpha collect-youtube-transcripts-slow \\",
        "  --input data/exports/transcripts/slow_youtube_transcript_queue.csv \\",
        "  --max-videos 25 \\",
        "  --delay-seconds 60 \\",
        "  --stop-on-block \\",
        "  --confirm-run",
        "```",
        "",
        "## Extended 50-Video Run (only if prior run had no block-like errors)",
        "",
        "```bash",
        "python3 -m finfluencer_alpha collect-youtube-transcripts-slow \\",
        "  --input data/exports/transcripts/slow_youtube_transcript_queue.csv \\",
        "  --max-videos 50 \\",
        "  --delay-seconds 60 \\",
        "  --stop-on-block \\",
        "  --confirm-run",
        "```",
        "",
        "## Post-Collection Integration",
        "",
        "After a successful run with at least one new transcript imported:",
        "",
        "```bash",
        "python3 -m finfluencer_alpha build-transcript-provenance-report",
        "python3 -m finfluencer_alpha extract-events-from-new-transcripts",
        "python3 -m finfluencer_alpha build-expanded-robustness",
        "```",
        "",
        "## Manual Fallback",
        "",
        "If live collection stops due to blocks or repeated errors:",
        "",
        "```bash",
        "python3 -m finfluencer_alpha build-manual-transcript-collection-packet \\",
        "  --input data/exports/transcripts/slow_youtube_transcript_queue.csv \\",
        "  --max-videos 100",
        "```",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
