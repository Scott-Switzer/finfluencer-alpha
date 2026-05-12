from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db

TRANSCRIPTS_EXPORT_DIR = EXPORTS_DIR / "transcripts"
DEFAULT_AVAILABILITY_AUDIT_CSV_PATH = TRANSCRIPTS_EXPORT_DIR / "transcript_availability_audit.csv"
DEFAULT_AVAILABILITY_AUDIT_MD_PATH = TRANSCRIPTS_EXPORT_DIR / "transcript_availability_audit.md"
AVAILABILITY_AUDIT_COLUMNS = [
    "scope",
    "year",
    "creator",
    "total_raw_youtube_videos",
    "available_transcripts",
    "disabled_transcripts",
    "unavailable_transcripts",
    "no_language_transcripts",
    "pending_unattempted",
    "request_blocked",
    "ip_blocked",
    "rate_limited",
    "error",
    "blocked_rate_limited_error_total",
    "transcript_coverage_pct",
    "transcript_supported_events",
    "event_yield_per_available_transcript",
    "warning_flags",
]


@dataclass(frozen=True)
class TranscriptAvailabilityAuditResult:
    csv_path: Path
    markdown_path: Path
    rows: tuple[dict[str, Any], ...]
    warning_flags: tuple[str, ...]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _empty_bucket(scope: str, year: str = "", creator: str = "") -> dict[str, Any]:
    return {
        "scope": scope,
        "year": year,
        "creator": creator,
        "total_raw_youtube_videos": 0,
        "available_transcripts": 0,
        "disabled_transcripts": 0,
        "unavailable_transcripts": 0,
        "no_language_transcripts": 0,
        "pending_unattempted": 0,
        "request_blocked": 0,
        "ip_blocked": 0,
        "rate_limited": 0,
        "error": 0,
        "blocked_rate_limited_error_total": 0,
        "transcript_coverage_pct": 0.0,
        "transcript_supported_events": 0,
        "event_yield_per_available_transcript": 0.0,
        "warning_flags": "",
    }


def _status_field(status: str) -> str:
    if status == "available":
        return "available_transcripts"
    if status == "disabled":
        return "disabled_transcripts"
    if status == "unavailable":
        return "unavailable_transcripts"
    if status == "no_language":
        return "no_language_transcripts"
    if status == "request_blocked":
        return "request_blocked"
    if status == "ip_blocked":
        return "ip_blocked"
    if status == "rate_limited":
        return "rate_limited"
    if status in {"", "missing", "pending", "pending_unattempted"}:
        return "pending_unattempted"
    return "error"


def _increment(bucket: dict[str, Any], status: str) -> None:
    bucket["total_raw_youtube_videos"] += 1
    bucket[_status_field(status)] += 1


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket["blocked_rate_limited_error_total"] = (
        int(bucket["request_blocked"])
        + int(bucket["ip_blocked"])
        + int(bucket["rate_limited"])
        + int(bucket["error"])
    )
    total = int(bucket["total_raw_youtube_videos"])
    available = int(bucket["available_transcripts"])
    events = int(bucket["transcript_supported_events"])
    bucket["transcript_coverage_pct"] = round((available / total) if total else 0.0, 6)
    bucket["event_yield_per_available_transcript"] = round(
        (events / available) if available else 0.0,
        6,
    )
    warnings: list[str] = []
    if total >= 5 and float(bucket["transcript_coverage_pct"]) < 0.5:
        warnings.append("low_coverage")
    if total >= 5 and int(bucket["pending_unattempted"]) >= max(3, total // 3):
        warnings.append("large_pending_share")
    if int(bucket["blocked_rate_limited_error_total"]) > 0:
        warnings.append("collection_friction")
    bucket["warning_flags"] = ";".join(warnings)
    return bucket


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AVAILABILITY_AUDIT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _coverage_warnings(year_rows: list[dict[str, Any]], creator_rows: list[dict[str, Any]]) -> tuple[str, ...]:
    warnings: list[str] = []
    year_rates = [float(row["transcript_coverage_pct"]) for row in year_rows if int(row["total_raw_youtube_videos"])]
    if len(year_rates) >= 2 and max(year_rates) - min(year_rates) >= 0.15:
        warnings.append("year_coverage_dispersion")
    if any("low_coverage" in _clean(row["warning_flags"]) for row in creator_rows):
        warnings.append("creator_coverage_gaps")
    top_creator_missing = max(
        (
            int(row["total_raw_youtube_videos"]) - int(row["available_transcripts"])
            for row in creator_rows
        ),
        default=0,
    )
    total_missing = sum(
        int(row["total_raw_youtube_videos"]) - int(row["available_transcripts"])
        for row in creator_rows
    )
    if total_missing and top_creator_missing / total_missing >= 0.25:
        warnings.append("missingness_concentrated_by_creator")
    return tuple(warnings)


def build_transcript_availability_audit(
    *,
    database_url: str | None = None,
    start_year: int = 2020,
    end_year: int = 2023,
    output_csv_path: Path = DEFAULT_AVAILABILITY_AUDIT_CSV_PATH,
    output_md_path: Path = DEFAULT_AVAILABILITY_AUDIT_MD_PATH,
) -> TranscriptAvailabilityAuditResult:
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")
    ensure_data_dirs()
    init_db(database_url=database_url)
    start_date = f"{start_year}-01-01T00:00:00Z"
    end_date = f"{end_year}-12-31T23:59:59Z"

    buckets: dict[tuple[str, str, str], dict[str, Any]] = {
        ("overall", "", ""): _empty_bucket("overall")
    }
    with connect(database_url=database_url) as conn:
        video_rows = conn.execute(
            """
            SELECT
              rv.video_id,
              SUBSTR(COALESCE(rv.published_at, ''), 1, 4) AS year,
              COALESCE(rv.channel_title, rv.channel_id, 'unknown') AS creator,
              COALESCE(yt.status, 'pending_unattempted') AS transcript_status
            FROM raw_youtube_videos rv
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = rv.video_id
            WHERE rv.published_at >= ?
              AND rv.published_at <= ?
              AND COALESCE(rv.excluded_flag, 0) = 0
            ORDER BY year, creator, rv.video_id
            """,
            (start_date, end_date),
        ).fetchall()
        event_rows = conn.execute(
            """
            SELECT
              SUBSTR(COALESCE(rv.published_at, ''), 1, 4) AS year,
              COALESCE(rv.channel_title, rv.channel_id, 'unknown') AS creator,
              COUNT(*) AS event_count
            FROM transcript_recommendation_events tre
            JOIN raw_youtube_videos rv
              ON rv.video_id = tre.video_id
            WHERE rv.published_at >= ?
              AND rv.published_at <= ?
              AND COALESCE(rv.excluded_flag, 0) = 0
            GROUP BY year, creator
            """,
            (start_date, end_date),
        ).fetchall()

    for row in video_rows:
        year = _clean(row["year"]) or "unknown"
        creator = _clean(row["creator"]) or "unknown"
        status = _clean(row["transcript_status"]) or "pending_unattempted"
        for key in (
            ("overall", "", ""),
            ("year", year, ""),
            ("creator", "", creator),
            ("year_creator", year, creator),
        ):
            bucket = buckets.setdefault(key, _empty_bucket(*key))
            _increment(bucket, status)

    for row in event_rows:
        year = _clean(row["year"]) or "unknown"
        creator = _clean(row["creator"]) or "unknown"
        count = int(row["event_count"] or 0)
        for key in (
            ("overall", "", ""),
            ("year", year, ""),
            ("creator", "", creator),
            ("year_creator", year, creator),
        ):
            bucket = buckets.setdefault(key, _empty_bucket(*key))
            bucket["transcript_supported_events"] += count

    rows = [_finalize_bucket(bucket) for _, bucket in sorted(buckets.items())]
    overall = next(row for row in rows if row["scope"] == "overall")
    year_rows = [row for row in rows if row["scope"] == "year"]
    creator_rows = [row for row in rows if row["scope"] == "creator"]
    top_missing_years = sorted(
        year_rows,
        key=lambda row: (
            -(int(row["total_raw_youtube_videos"]) - int(row["available_transcripts"])),
            str(row["year"]),
        ),
    )[:5]
    top_missing_creators = sorted(
        creator_rows,
        key=lambda row: (
            -(int(row["total_raw_youtube_videos"]) - int(row["available_transcripts"])),
            str(row["creator"]),
        ),
    )[:10]
    warnings = _coverage_warnings(year_rows, creator_rows)

    _write_csv(output_csv_path, rows)
    lines = [
        "# Transcript Availability Audit",
        "",
        f"- Period: {start_year}-{end_year}",
        f"- Eligible raw YouTube videos: {overall['total_raw_youtube_videos']}",
        f"- Available transcripts: {overall['available_transcripts']}",
        f"- Pending/unattempted: {overall['pending_unattempted']}",
        "- Disabled/unavailable/no-language: "
        f"{overall['disabled_transcripts']}/{overall['unavailable_transcripts']}/{overall['no_language_transcripts']}",
        "- Blocked/rate-limited/error: "
        f"{overall['request_blocked'] + overall['ip_blocked']}/"
        f"{overall['rate_limited']}/{overall['error']}",
        f"- Overall transcript coverage: {float(overall['transcript_coverage_pct']):.1%}",
        f"- Transcript-supported events in scope: {overall['transcript_supported_events']}",
        "",
        "## Coverage By Year",
        "",
    ]
    for row in sorted(year_rows, key=lambda item: str(item["year"])):
        lines.append(
            f"- {row['year']}: {row['available_transcripts']}/{row['total_raw_youtube_videos']} "
            f"({float(row['transcript_coverage_pct']):.1%}), "
            f"event_yield={row['event_yield_per_available_transcript']}"
        )
    lines.extend(["", "## Lowest-Coverage Creators", ""])
    for row in sorted(
        creator_rows,
        key=lambda item: (float(item["transcript_coverage_pct"]), -int(item["total_raw_youtube_videos"]), str(item["creator"])),
    )[:10]:
        lines.append(
            f"- {row['creator']}: {row['available_transcripts']}/{row['total_raw_youtube_videos']} "
            f"({float(row['transcript_coverage_pct']):.1%}), "
            f"pending={row['pending_unattempted']}"
        )
    lines.extend(["", "## Top Missing Years", ""])
    for row in top_missing_years:
        missing = int(row["total_raw_youtube_videos"]) - int(row["available_transcripts"])
        lines.append(f"- {row['year']}: missing={missing}")
    lines.extend(["", "## Top Missing Creators", ""])
    for row in top_missing_creators:
        missing = int(row["total_raw_youtube_videos"]) - int(row["available_transcripts"])
        lines.append(f"- {row['creator']}: missing={missing}")
    lines.extend(["", "## Warning Flags", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This audit uses local database state only. It makes no live YouTube requests.",
            "",
        ]
    )
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text("\n".join(lines), encoding="utf-8")
    return TranscriptAvailabilityAuditResult(
        csv_path=output_csv_path,
        markdown_path=output_md_path,
        rows=tuple(rows),
        warning_flags=warnings,
    )
