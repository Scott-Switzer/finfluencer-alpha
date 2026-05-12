from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import EXPORTS_DIR, IMPORTS_DIR, PROJECT_ROOT, ensure_data_dirs, get_settings
from .db import connect, init_db
from .transcript_vendor import import_transcripts_csv
from .utils import configure_csv_field_size_limit
from .youtube_transcripts import TranscriptFetchResult, TranscriptSegment, store_transcript_result

TRANSCRIPT_EXPORT_DIR = EXPORTS_DIR / "transcripts"
DEFAULT_PAID_BATCH_CSV = TRANSCRIPT_EXPORT_DIR / "next_paid_transcript_batch_61.csv"
DEFAULT_PAID_BATCH_MD = TRANSCRIPT_EXPORT_DIR / "next_paid_transcript_batch_61.md"
DEFAULT_PAID_SUMMARY_CSV = TRANSCRIPT_EXPORT_DIR / "paid_transcript_batch_summary.csv"
DEFAULT_PAID_SUMMARY_MD = TRANSCRIPT_EXPORT_DIR / "paid_transcript_batch_summary.md"
DEFAULT_MANUAL_IMPORT_CSV = IMPORTS_DIR / "manual_transcripts.csv"
DEFAULT_MANUAL_SUMMARY_CSV = TRANSCRIPT_EXPORT_DIR / "manual_transcript_import_summary.csv"
DEFAULT_MANUAL_SUMMARY_MD = TRANSCRIPT_EXPORT_DIR / "manual_transcript_import_summary.md"
DEFAULT_PROVENANCE_CSV = TRANSCRIPT_EXPORT_DIR / "transcript_provenance_summary.csv"
DEFAULT_PROVENANCE_MD = TRANSCRIPT_EXPORT_DIR / "transcript_provenance_summary.md"
DEFAULT_METHODOLOGY_NOTE = TRANSCRIPT_EXPORT_DIR / "transcript_collection_methodology_note.md"
PAID_BATCH_COLUMNS = [
    "video_id",
    "title",
    "creator/channel",
    "upload_date",
    "year",
    "transcript_status",
    "selected_order",
    "estimated_credit_cost",
    "selected_for_paid_batch",
]
MANUAL_REQUIRED_COLUMNS = {
    "video_id",
    "transcript_text",
    "transcript_source",
    "collected_at",
    "collector_notes",
}
MANUAL_SUMMARY_COLUMNS = [
    "row_number",
    "video_id",
    "transcript_source",
    "status",
    "word_count",
    "character_count",
    "checksum",
    "duplicate_checksum",
    "existing_transcript",
    "message",
    "imported",
]
PAID_SUMMARY_COLUMNS = [
    "video_id",
    "selected_order",
    "status",
    "provider",
    "transcript_source",
    "word_count",
    "character_count",
    "checksum",
    "estimated_credit_cost",
    "message",
]
PROVENANCE_COLUMNS = [
    "section",
    "label",
    "value",
    "total_videos",
    "videos_with_transcripts",
    "videos_missing_transcripts",
    "transcript_count",
    "coverage_rate",
]
MIN_USEFUL_TRANSCRIPT_WORDS = 50


@dataclass(frozen=True)
class PaidBatchPlanResult:
    csv_path: Path
    md_path: Path
    selected_count: int
    credit_budget: int
    total_videos: int
    videos_with_transcripts: int
    videos_missing_transcripts: int


@dataclass(frozen=True)
class PaidTranscriptCollectionResult:
    summary_csv_path: Path
    summary_md_path: Path
    attempted_count: int
    imported_count: int
    failed_count: int
    skipped_existing_count: int
    live_api_calls_made: bool


@dataclass(frozen=True)
class ManualTranscriptImportResult:
    summary_csv_path: Path
    summary_md_path: Path
    total_rows: int
    imported_count: int
    rejected_count: int
    skipped_existing_count: int
    duplicate_checksum_count: int
    dry_run: bool


@dataclass(frozen=True)
class TranscriptProvenanceReportResult:
    csv_path: Path
    md_path: Path
    methodology_note_path: Path
    total_videos: int
    videos_with_transcripts: int
    videos_missing_transcripts: int


class ManualTranscriptImportError(ValueError):
    pass


def _resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _clean(value: object) -> str:
    return str(value or "").strip()


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _truthy(value: object) -> bool:
    return _clean(value).lower() in {"1", "true", "t", "yes", "y", "selected"}


def _year(value: str) -> str:
    return value[:4] if len(value) >= 4 and value[:4].isdigit() else ""


def _upload_date(value: str) -> str:
    return value[:10] if len(value) >= 10 else ""


def _word_count(text: str) -> int:
    return len(text.split())


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _available(status: object, full_text: object) -> bool:
    return _clean(status) == "available" and bool(_clean(full_text))


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> Path:
    path = _resolve_project_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _md_escape(value: object) -> str:
    return _clean(value).replace("|", "\\|").replace("\n", " ")


def _markdown_table(columns: list[str], rows: list[dict[str, object]], limit: int | None = None) -> list[str]:
    selected = rows if limit is None else rows[:limit]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(_md_escape(row.get(column)) for column in columns) + " |")
    return lines


def _write_text(path: Path, text: str) -> Path:
    path = _resolve_project_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _transcript_status(row: object) -> str:
    status = _clean(row["transcript_status"])
    if _available(status, row["full_text"]):
        return "available"
    return status or "missing"


def _ordered_video_rows() -> list[object]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT
              y.video_id,
              y.channel_id,
              y.channel_title,
              y.published_at,
              y.title,
              y.url,
              yt.status AS transcript_status,
              yt.full_text
            FROM raw_youtube_videos y
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
            WHERE COALESCE(y.excluded_flag, 0) = 0
            ORDER BY y.published_at DESC, y.video_id
            """
        ).fetchall()


def _coverage_counts(rows: list[object]) -> tuple[int, int, int]:
    total = len(rows)
    with_transcripts = sum(
        1 for row in rows if _available(row["transcript_status"], row["full_text"])
    )
    return total, with_transcripts, total - with_transcripts


def plan_next_paid_transcript_batch(
    *,
    credit_budget: int = 61,
    csv_path: Path = DEFAULT_PAID_BATCH_CSV,
    md_path: Path = DEFAULT_PAID_BATCH_MD,
) -> PaidBatchPlanResult:
    if credit_budget < 1:
        raise ValueError("--credit-budget must be at least 1")
    ensure_data_dirs()
    rows = _ordered_video_rows()
    total_videos, videos_with_transcripts, videos_missing_transcripts = _coverage_counts(rows)
    missing_rows = [
        row
        for row in rows
        if not _available(row["transcript_status"], row["full_text"])
    ]
    selected_rows = missing_rows[:credit_budget]
    output_rows: list[dict[str, object]] = []
    for selected_order, row in enumerate(selected_rows, start=1):
        output_rows.append(
            {
                "video_id": row["video_id"],
                "title": row["title"] or "",
                "creator/channel": row["channel_title"] or row["channel_id"] or "unknown",
                "upload_date": _upload_date(row["published_at"] or ""),
                "year": _year(row["published_at"] or ""),
                "transcript_status": _transcript_status(row),
                "selected_order": selected_order,
                "estimated_credit_cost": 1,
                "selected_for_paid_batch": 1,
            }
        )
    csv_path = _write_csv(csv_path, output_rows, PAID_BATCH_COLUMNS)
    md_lines = [
        "# Next Paid Transcript Batch",
        "",
        "This plan uses the repository's existing deterministic YouTube video ordering: "
        "`published_at DESC, video_id`. It does not rank by creator, year, views, "
        "event likelihood, or title signal.",
        "",
        f"- Total included videos: {total_videos}",
        f"- Videos with transcripts: {videos_with_transcripts}",
        f"- Videos missing transcripts: {videos_missing_transcripts}",
        f"- Credit budget: {credit_budget}",
        f"- Planned videos: {len(output_rows)}",
        f"- Estimated credits required: {sum(int(row['estimated_credit_cost']) for row in output_rows)}",
        "",
        "## Selected Videos",
        "",
    ]
    md_lines.extend(
        _markdown_table(
            ["selected_order", "video_id", "upload_date", "year", "creator/channel", "title"],
            output_rows,
        )
    )
    md_path = _write_text(md_path, "\n".join(md_lines) + "\n")
    return PaidBatchPlanResult(
        csv_path=csv_path,
        md_path=md_path,
        selected_count=len(output_rows),
        credit_budget=credit_budget,
        total_videos=total_videos,
        videos_with_transcripts=videos_with_transcripts,
        videos_missing_transcripts=videos_missing_transcripts,
    )


def _load_dict_rows(path: Path) -> list[dict[str, str]]:
    path = _resolve_project_path(path)
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV is missing a header row: {path}")
        return [dict(row) for row in reader]


def _selected_paid_rows(path: Path, credit_budget: int) -> list[dict[str, str]]:
    rows = _load_dict_rows(path)
    if not rows:
        return []
    if "video_id" not in rows[0]:
        raise ValueError("Paid transcript batch CSV must include video_id")
    seen: set[str] = set()
    selected: list[dict[str, str]] = []
    for row in rows:
        video_id = _clean(row.get("video_id"))
        if not video_id or video_id in seen:
            continue
        selected_flag = row.get("selected_for_paid_batch")
        if selected_flag is not None and not _truthy(selected_flag):
            continue
        seen.add(video_id)
        selected.append(row)
        if len(selected) >= credit_budget:
            break
    return selected


def _existing_video_lookup(video_ids: list[str]) -> tuple[set[str], set[str]]:
    if not video_ids:
        return set(), set()
    placeholders = ",".join("?" for _ in video_ids)
    with connect() as conn:
        raw_ids = {
            row["video_id"]
            for row in conn.execute(
                f"SELECT video_id FROM raw_youtube_videos WHERE video_id IN ({placeholders})",
                video_ids,
            ).fetchall()
        }
        transcript_ids = {
            row["video_id"]
            for row in conn.execute(
                f"""
                SELECT video_id
                FROM youtube_transcripts
                WHERE video_id IN ({placeholders})
                  AND status = 'available'
                  AND COALESCE(full_text, '') != ''
                """,
                video_ids,
            ).fetchall()
        }
    return raw_ids, transcript_ids


def _provider_api_key_available(provider: str) -> bool:
    settings = get_settings()
    normalized = provider.strip().lower()
    if normalized == "transcriptapi":
        return bool(settings.transcriptapi_key)
    if normalized == "youtubetranscript_dev":
        return bool(settings.youtubetranscript_dev_api_key)
    raise ValueError(f"Unsupported provider: {provider}")


def _provider_display_name(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "transcriptapi":
        return "TranscriptAPI.com"
    if normalized == "youtubetranscript_dev":
        return "YouTubeTranscript.dev"
    return provider


def _write_provider_input(path: Path, rows: list[dict[str, str]]) -> Path:
    provider_rows = []
    for row in rows:
        video_id = _clean(row.get("video_id"))
        provider_rows.append(
            {
                "video_id": video_id,
                "url": _clean(row.get("url")) or f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    return _write_csv(path, provider_rows, ["video_id", "url"])


def _read_provider_success_rows(path: Path) -> list[dict[str, str]]:
    resolved = _resolve_project_path(path)
    if not resolved.exists():
        return []
    return _load_dict_rows(resolved)


def _read_provider_failure_rows(path: Path) -> list[dict[str, str]]:
    resolved = _resolve_project_path(path)
    if not resolved.exists():
        return []
    return _load_dict_rows(resolved)


def _write_paid_summary(
    *,
    rows: list[dict[str, object]],
    csv_path: Path,
    md_path: Path,
    provider: str,
    live_api_calls_made: bool,
) -> tuple[Path, Path]:
    csv_path = _write_csv(csv_path, rows, PAID_SUMMARY_COLUMNS)
    status_counts = Counter(_clean(row.get("status")) for row in rows)
    md_lines = [
        "# Paid Transcript Batch Summary",
        "",
        f"- Provider: {_provider_display_name(provider)}",
        f"- Live API calls made: {'yes' if live_api_calls_made else 'no'}",
        f"- Attempted provider videos: {status_counts.get('imported', 0) + status_counts.get('provider_failed', 0)}",
        f"- Imported transcripts: {status_counts.get('imported', 0)}",
        f"- Provider failures: {status_counts.get('provider_failed', 0)}",
        f"- Skipped existing transcripts: {status_counts.get('skipped_existing', 0)}",
        f"- Not attempted: {sum(count for status, count in status_counts.items() if status.startswith('not_attempted'))}",
        "",
        "## Rows",
        "",
    ]
    md_lines.extend(
        _markdown_table(
            ["selected_order", "video_id", "status", "word_count", "character_count", "message"],
            rows,
        )
    )
    md_path = _write_text(md_path, "\n".join(md_lines) + "\n")
    return csv_path, md_path


def collect_paid_transcript_batch(
    *,
    input_path: Path,
    confirm_paid_transcript_run: bool,
    provider: str = "transcriptapi",
    credit_budget: int = 61,
    batch_size: int = 100,
    language: str = "en",
    timestamps: bool = False,
    captions_only: bool = False,
    allow_asr: bool = False,
    allow_overwrite: bool = False,
    summary_csv_path: Path = DEFAULT_PAID_SUMMARY_CSV,
    summary_md_path: Path = DEFAULT_PAID_SUMMARY_MD,
) -> PaidTranscriptCollectionResult:
    if not confirm_paid_transcript_run:
        raise ValueError("Refusing paid transcript run without --confirm-paid-transcript-run.")
    if credit_budget < 1 or credit_budget > 61:
        raise ValueError("--credit-budget must be between 1 and 61")
    selected = _selected_paid_rows(input_path, credit_budget)
    selected_ids = [_clean(row.get("video_id")) for row in selected]
    raw_ids, existing_ids = _existing_video_lookup(selected_ids)
    provider_name = _provider_display_name(provider)
    summary_rows: list[dict[str, object]] = []
    provider_rows: list[dict[str, str]] = []
    for order, row in enumerate(selected, start=1):
        video_id = _clean(row.get("video_id"))
        status = "ready"
        message = ""
        if video_id not in raw_ids:
            status = "not_attempted_unknown_video_id"
            message = "video_id is not present in raw_youtube_videos"
        elif video_id in existing_ids and not allow_overwrite:
            status = "skipped_existing"
            message = "available transcript already exists"
        else:
            provider_rows.append(row)
        summary_rows.append(
            {
                "video_id": video_id,
                "selected_order": _clean(row.get("selected_order")) or order,
                "status": status,
                "provider": provider_name,
                "transcript_source": "paid_provider",
                "word_count": "",
                "character_count": "",
                "checksum": "",
                "estimated_credit_cost": 1 if status == "ready" else 0,
                "message": message,
            }
        )
    if not _provider_api_key_available(provider):
        for row in summary_rows:
            if row["status"] == "ready":
                row["status"] = "not_attempted_missing_api_key"
                row["estimated_credit_cost"] = 0
                row["message"] = f"Missing API key for {provider_name}"
        csv_path, md_path = _write_paid_summary(
            rows=summary_rows,
            csv_path=summary_csv_path,
            md_path=summary_md_path,
            provider=provider,
            live_api_calls_made=False,
        )
        return PaidTranscriptCollectionResult(
            summary_csv_path=csv_path,
            summary_md_path=md_path,
            attempted_count=0,
            imported_count=0,
            failed_count=0,
            skipped_existing_count=sum(1 for row in summary_rows if row["status"] == "skipped_existing"),
            live_api_calls_made=False,
        )

    if not provider_rows:
        csv_path, md_path = _write_paid_summary(
            rows=summary_rows,
            csv_path=summary_csv_path,
            md_path=summary_md_path,
            provider=provider,
            live_api_calls_made=False,
        )
        return PaidTranscriptCollectionResult(
            summary_csv_path=csv_path,
            summary_md_path=md_path,
            attempted_count=0,
            imported_count=0,
            failed_count=0,
            skipped_existing_count=sum(1 for row in summary_rows if row["status"] == "skipped_existing"),
            live_api_calls_made=False,
        )

    init_db()
    from .provider_transcripts import (  # noqa: PLC0415
        ProviderConfigError,
        ProviderRequestError,
        collect_provider_transcripts,
    )

    provider_input = TRANSCRIPT_EXPORT_DIR / "paid_transcript_batch_provider_input.csv"
    provider_output = IMPORTS_DIR / "paid_transcript_batch_provider_output.csv"
    _write_provider_input(provider_input, provider_rows)
    try:
        result = collect_provider_transcripts(
            provider=provider,
            input_path=provider_input,
            output_path=provider_output,
            limit=min(credit_budget, len(provider_rows)),
            batch_size=batch_size,
            language=language,
            timestamps=timestamps,
            captions_only=captions_only,
            allow_asr=allow_asr,
            confirm_provider_run=True,
            skip_existing=False,
            transcript_source="paid_provider",
        )
    except (ProviderConfigError, ProviderRequestError, ValueError) as exc:
        for row in summary_rows:
            if row["status"] == "ready":
                row["status"] = "provider_unavailable"
                row["estimated_credit_cost"] = 0
                row["message"] = str(exc)[:1000]
        csv_path, md_path = _write_paid_summary(
            rows=summary_rows,
            csv_path=summary_csv_path,
            md_path=summary_md_path,
            provider=provider,
            live_api_calls_made=True,
        )
        raise ValueError(
            f"Paid provider run stopped safely: {exc}. Summary written to {csv_path}"
        ) from exc

    success_rows = {
        _clean(row.get("video_id")): row for row in _read_provider_success_rows(provider_output)
    }
    failure_rows = {
        _clean(row.get("video_id")): row for row in _read_provider_failure_rows(result.failure_path)
    }
    imported_count = 0
    if success_rows:
        import_result = import_transcripts_csv(
            provider_output,
            source="paid_provider",
            overwrite=allow_overwrite,
        )
        imported_count = import_result.imported_count
    for row in summary_rows:
        video_id = _clean(row.get("video_id"))
        if row["status"] != "ready":
            continue
        success = success_rows.get(video_id)
        failure = failure_rows.get(video_id)
        if success:
            text = _clean(success.get("transcript_text"))
            row["status"] = "imported"
            row["word_count"] = _word_count(text)
            row["character_count"] = len(text)
            row["checksum"] = _checksum(text)
            row["message"] = "transcript imported"
        elif failure:
            row["status"] = "provider_failed"
            row["estimated_credit_cost"] = 1
            row["message"] = _clean(failure.get("error_message")) or _clean(failure.get("status"))
        else:
            row["status"] = "provider_failed"
            row["message"] = "provider returned no success or failure row"
    csv_path, md_path = _write_paid_summary(
        rows=summary_rows,
        csv_path=summary_csv_path,
        md_path=summary_md_path,
        provider=provider,
        live_api_calls_made=True,
    )
    return PaidTranscriptCollectionResult(
        summary_csv_path=csv_path,
        summary_md_path=md_path,
        attempted_count=result.attempted_count,
        imported_count=imported_count,
        failed_count=sum(1 for row in summary_rows if row["status"] == "provider_failed"),
        skipped_existing_count=sum(1 for row in summary_rows if row["status"] == "skipped_existing"),
        live_api_calls_made=True,
    )


def _load_manual_rows(path: Path) -> list[dict[str, str]]:
    rows = _load_dict_rows(path)
    fieldnames = set(rows[0]) if rows else set()
    missing = MANUAL_REQUIRED_COLUMNS - fieldnames
    legacy_ok = {
        "video_id",
        "transcript_text",
        "transcript_source",
        "retrieved_at",
        "collector_notes",
    } <= fieldnames
    if missing and not legacy_ok:
        raise ValueError(
            "Manual transcript CSV is missing required columns: " + ", ".join(sorted(missing))
        )
    return rows


def _existing_hashes(conn: object, video_id: str) -> set[str]:
    return {
        row["full_text_sha256"]
        for row in conn.execute(
            """
            SELECT full_text_sha256
            FROM youtube_transcripts
            WHERE video_id != ?
              AND status = 'available'
              AND COALESCE(full_text_sha256, '') != ''
            """,
            (video_id,),
        ).fetchall()
    }


def _manual_summary_markdown(
    *,
    rows: list[dict[str, object]],
    dry_run: bool,
    min_word_count: int,
) -> str:
    status_counts = Counter(_clean(row.get("status")) for row in rows)
    lines = [
        "# Manual Transcript Import Summary",
        "",
        f"- Mode: {'dry run' if dry_run else 'confirmed import'}",
        f"- Input rows: {len(rows)}",
        f"- Imported transcripts: {status_counts.get('imported', 0)}",
        f"- Ready transcripts: {status_counts.get('ready', 0)}",
        f"- Rejected rows: {sum(count for status, count in status_counts.items() if status.startswith('rejected'))}",
        f"- Skipped existing transcripts: {status_counts.get('skipped_existing', 0)}",
        f"- Minimum useful length: {min_word_count} words",
        "",
        "## Rows",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["row_number", "video_id", "status", "word_count", "checksum", "message"],
            rows,
        )
    )
    return "\n".join(lines) + "\n"


def import_manual_transcripts_with_summary(
    *,
    input_path: Path = DEFAULT_MANUAL_IMPORT_CSV,
    dry_run: bool = True,
    confirm_import: bool = False,
    allow_short: bool = False,
    allow_overwrite: bool = False,
    min_word_count: int = MIN_USEFUL_TRANSCRIPT_WORDS,
    summary_csv_path: Path = DEFAULT_MANUAL_SUMMARY_CSV,
    summary_md_path: Path = DEFAULT_MANUAL_SUMMARY_MD,
) -> ManualTranscriptImportResult:
    if confirm_import and dry_run:
        raise ValueError("--dry-run cannot be combined with --confirm-import")
    if not dry_run and not confirm_import:
        raise ValueError("Refusing manual import without --confirm-import.")
    rows = _load_manual_rows(input_path)
    if min_word_count < 1:
        raise ValueError("--min-word-count must be at least 1")
    video_ids = [_clean(row.get("video_id")) for row in rows if _clean(row.get("video_id"))]
    raw_ids, existing_ids = _existing_video_lookup(video_ids)
    checksums = [
        _checksum(_clean(row.get("transcript_text")))
        for row in rows
        if _clean(row.get("transcript_text"))
    ]
    duplicate_input_hashes = {checksum for checksum, count in Counter(checksums).items() if count > 1}
    summary_rows: list[dict[str, object]] = []
    valid_results: list[TranscriptFetchResult] = []
    rejected_count = 0
    skipped_existing_count = 0
    duplicate_checksum_count = 0
    with connect() as conn:
        for index, row in enumerate(rows, start=2):
            video_id = _clean(row.get("video_id"))
            full_text = _clean(row.get("transcript_text"))
            transcript_source = _clean(row.get("transcript_source")) or "manual"
            collected_at = _clean(row.get("collected_at")) or _clean(row.get("retrieved_at"))
            collector_notes = _clean(row.get("collector_notes"))
            checksum = _checksum(full_text) if full_text else ""
            word_count = _word_count(full_text)
            character_count = len(full_text)
            duplicate_checksum = bool(
                checksum
                and (
                    checksum in duplicate_input_hashes
                    or checksum in _existing_hashes(conn, video_id)
                )
            )
            status = "ready"
            message = ""
            if not video_id:
                status = "rejected_missing_video_id"
                message = "video_id is required"
            elif video_id not in raw_ids:
                status = "rejected_unknown_video_id"
                message = "video_id is not present in raw_youtube_videos"
            elif not full_text:
                status = "rejected_empty_transcript"
                message = "transcript_text is required"
            elif word_count < min_word_count and not allow_short:
                status = "rejected_short_transcript"
                message = f"word_count {word_count} is below minimum {min_word_count}"
            elif duplicate_checksum:
                status = "rejected_duplicate_checksum"
                message = "transcript checksum duplicates another transcript"
            elif video_id in existing_ids and not allow_overwrite:
                status = "skipped_existing"
                message = "available transcript already exists"
            if status.startswith("rejected"):
                rejected_count += 1
            if status == "skipped_existing":
                skipped_existing_count += 1
            if duplicate_checksum:
                duplicate_checksum_count += 1
            summary_rows.append(
                {
                    "row_number": index,
                    "video_id": video_id,
                    "transcript_source": transcript_source,
                    "status": status,
                    "word_count": word_count if full_text else 0,
                    "character_count": character_count if full_text else 0,
                    "checksum": checksum,
                    "duplicate_checksum": int(duplicate_checksum),
                    "existing_transcript": int(video_id in existing_ids),
                    "message": message,
                    "imported": 0,
                }
            )
            if status == "ready" and not dry_run:
                retrieved_at = collected_at or _utc_now_iso()
                result = TranscriptFetchResult(
                    video_id=video_id,
                    provider_name=transcript_source,
                    provider_version="",
                    status="available",
                    transcript_source=transcript_source,
                    retrieval_method="manual_supplemental_import",
                    retrieval_status="available",
                    retrieved_at=retrieved_at,
                    provider_notes=collector_notes,
                    is_generated=False,
                    is_asr_generated=False,
                    full_text=full_text,
                    full_text_sha256=checksum,
                    raw_json="",
                    segments=[TranscriptSegment(video_id, 0, 0.0, None, full_text)],
                    source_confidence=0.80,
                    collected_at=collected_at or retrieved_at,
                    character_count=character_count,
                    word_count=word_count,
                    collector_notes=collector_notes,
                )
                valid_results.append(result)

    if rejected_count and not dry_run:
        csv_path = _write_csv(summary_csv_path, summary_rows, MANUAL_SUMMARY_COLUMNS)
        md_path = _write_text(
            summary_md_path,
            _manual_summary_markdown(
                rows=summary_rows,
                dry_run=dry_run,
                min_word_count=min_word_count,
            ),
        )
        raise ManualTranscriptImportError(
            f"Manual transcript import rejected {rejected_count} row(s). "
            f"Summary written to {csv_path} and {md_path}."
        )

    imported_count = 0
    if valid_results and not dry_run:
        init_db()
        with connect() as conn:
            for result in valid_results:
                store_transcript_result(conn, result)
                imported_count += 1
            conn.commit()
        valid_ids = {result.video_id for result in valid_results}
        for row in summary_rows:
            if row["video_id"] in valid_ids and row["status"] == "ready":
                row["status"] = "imported"
                row["imported"] = 1
                row["message"] = "transcript imported"

    csv_path = _write_csv(summary_csv_path, summary_rows, MANUAL_SUMMARY_COLUMNS)
    md_path = _write_text(
        summary_md_path,
        _manual_summary_markdown(
            rows=summary_rows,
            dry_run=dry_run,
            min_word_count=min_word_count,
        ),
    )
    return ManualTranscriptImportResult(
        summary_csv_path=csv_path,
        summary_md_path=md_path,
        total_rows=len(rows),
        imported_count=imported_count,
        rejected_count=rejected_count,
        skipped_existing_count=skipped_existing_count,
        duplicate_checksum_count=duplicate_checksum_count,
        dry_run=dry_run,
    )


def _available_transcript_records() -> list[dict[str, object]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              y.video_id,
              y.channel_title,
              y.channel_id,
              y.published_at,
              yt.transcript_source,
              yt.provider_name,
              yt.full_text,
              yt.full_text_sha256
            FROM raw_youtube_videos y
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
             AND yt.status = 'available'
             AND COALESCE(yt.full_text, '') != ''
            WHERE COALESCE(y.excluded_flag, 0) = 0
            """
        ).fetchall()
    records: list[dict[str, object]] = []
    for row in rows:
        full_text = _clean(row["full_text"])
        records.append(
            {
                "video_id": row["video_id"],
                "creator": row["channel_title"] or row["channel_id"] or "unknown",
                "year": _year(row["published_at"] or "") or "unknown",
                "transcript_source": _clean(row["transcript_source"]) or "missing",
                "provider_name": _clean(row["provider_name"]),
                "full_text": full_text,
                "checksum": _clean(row["full_text_sha256"]) or (_checksum(full_text) if full_text else ""),
                "word_count": _word_count(full_text),
                "has_transcript": bool(full_text),
            }
        )
    return records


def _coverage_summary_rows(
    records: list[dict[str, object]],
    *,
    key: str,
    section: str,
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "covered": 0})
    for record in records:
        label = _clean(record.get(key)) or "unknown"
        grouped[label]["total"] += 1
        grouped[label]["covered"] += int(bool(record["has_transcript"]))
    rows = []
    for label, counts in grouped.items():
        missing = counts["total"] - counts["covered"]
        rows.append(
            {
                "section": section,
                "label": label,
                "value": "",
                "total_videos": counts["total"],
                "videos_with_transcripts": counts["covered"],
                "videos_missing_transcripts": missing,
                "transcript_count": counts["covered"],
                "coverage_rate": round(counts["covered"] / counts["total"], 4)
                if counts["total"]
                else 0.0,
            }
        )
    rows.sort(key=lambda row: (-int(row["total_videos"]), str(row["label"])))
    return rows


def write_transcript_collection_methodology_note(
    path: Path = DEFAULT_METHODOLOGY_NOTE,
) -> Path:
    return _write_text(
        path,
        (
            "# Transcript Collection Methodology Note\n\n"
            "Transcripts were collected from a combination of provider-based transcript APIs, "
            "publicly available caption/transcript surfaces, and manual supplemental collection "
            "where automated retrieval was unavailable.\n\n"
            "Each transcript was stored with source and provenance metadata, including the "
            "transcript source, provider when available, collection timestamp, text hash, "
            "character count, and word count.\n\n"
            "The transcript corpus was used to identify stock-specific recommendation events. "
            "The analysis remains limited by transcript availability, creator coverage, and "
            "potential selection bias in videos with retrievable captions.\n\n"
            "These transcript-derived events support descriptive and event-study evidence, but "
            "the design should not be interpreted as establishing causal effects of creator "
            "recommendations on security prices.\n"
        ),
    )


def build_transcript_provenance_report(
    *,
    csv_path: Path = DEFAULT_PROVENANCE_CSV,
    md_path: Path = DEFAULT_PROVENANCE_MD,
    methodology_note_path: Path = DEFAULT_METHODOLOGY_NOTE,
    min_word_count: int = MIN_USEFUL_TRANSCRIPT_WORDS,
) -> TranscriptProvenanceReportResult:
    ensure_data_dirs()
    records = _available_transcript_records()
    total_videos = len(records)
    videos_with_transcripts = sum(1 for record in records if record["has_transcript"])
    videos_missing_transcripts = total_videos - videos_with_transcripts
    available = [record for record in records if record["has_transcript"]]
    source_counts = Counter(_clean(record["transcript_source"]) for record in available)
    checksum_counts = Counter(_clean(record["checksum"]) for record in available if record["checksum"])
    duplicate_transcript_count = sum(count - 1 for count in checksum_counts.values() if count > 1)
    short_transcript_count = sum(
        1 for record in available if int(record["word_count"]) < min_word_count
    )
    native_public_count = sum(
        count
        for source, count in source_counts.items()
        if source in {"youtube", "native", "public", "public_caption", "youtube_transcript_api"}
    )
    manual_count = sum(
        count for source, count in source_counts.items() if source.startswith("manual")
    )
    paid_provider_count = source_counts.get("paid_provider", 0)
    recommended_next_action = (
        "Run the planned 61-video paid provider batch when ready to spend credits, "
        "then use the manual supplemental import for remaining missing transcripts."
        if videos_missing_transcripts
        else "Transcript coverage is complete for the current included metadata universe."
    )
    csv_rows: list[dict[str, object]] = [
        {
            "section": "summary",
            "label": "total_videos",
            "value": total_videos,
            "total_videos": total_videos,
            "videos_with_transcripts": videos_with_transcripts,
            "videos_missing_transcripts": videos_missing_transcripts,
            "transcript_count": videos_with_transcripts,
            "coverage_rate": round(videos_with_transcripts / total_videos, 4)
            if total_videos
            else 0.0,
        },
        {
            "section": "summary",
            "label": "paid_provider_transcript_count",
            "value": paid_provider_count,
            "total_videos": "",
            "videos_with_transcripts": "",
            "videos_missing_transcripts": "",
            "transcript_count": paid_provider_count,
            "coverage_rate": "",
        },
        {
            "section": "summary",
            "label": "native_public_transcript_count",
            "value": native_public_count,
            "total_videos": "",
            "videos_with_transcripts": "",
            "videos_missing_transcripts": "",
            "transcript_count": native_public_count,
            "coverage_rate": "",
        },
        {
            "section": "summary",
            "label": "manual_transcript_count",
            "value": manual_count,
            "total_videos": "",
            "videos_with_transcripts": "",
            "videos_missing_transcripts": "",
            "transcript_count": manual_count,
            "coverage_rate": "",
        },
        {
            "section": "summary",
            "label": "duplicate_transcript_count",
            "value": duplicate_transcript_count,
            "total_videos": "",
            "videos_with_transcripts": "",
            "videos_missing_transcripts": "",
            "transcript_count": duplicate_transcript_count,
            "coverage_rate": "",
        },
        {
            "section": "summary",
            "label": "short_transcript_count",
            "value": short_transcript_count,
            "total_videos": "",
            "videos_with_transcripts": "",
            "videos_missing_transcripts": "",
            "transcript_count": short_transcript_count,
            "coverage_rate": "",
        },
        {
            "section": "summary",
            "label": "recommended_next_action",
            "value": recommended_next_action,
            "total_videos": "",
            "videos_with_transcripts": "",
            "videos_missing_transcripts": "",
            "transcript_count": "",
            "coverage_rate": "",
        },
    ]
    for source, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0])):
        csv_rows.append(
            {
                "section": "transcripts_by_source",
                "label": source or "unknown",
                "value": count,
                "total_videos": "",
                "videos_with_transcripts": "",
                "videos_missing_transcripts": "",
                "transcript_count": count,
                "coverage_rate": "",
            }
        )
    creator_rows = _coverage_summary_rows(records, key="creator", section="transcripts_by_creator")
    year_rows = _coverage_summary_rows(records, key="year", section="transcripts_by_year")
    csv_rows.extend(creator_rows)
    csv_rows.extend(year_rows)
    csv_path = _write_csv(csv_path, csv_rows, PROVENANCE_COLUMNS)
    methodology_note_path = write_transcript_collection_methodology_note(methodology_note_path)
    md_lines = [
        "# Transcript Provenance Summary",
        "",
        f"- Total included videos: {total_videos}",
        f"- Videos with transcripts: {videos_with_transcripts}",
        f"- Videos missing transcripts: {videos_missing_transcripts}",
        f"- Paid provider transcript count: {paid_provider_count}",
        f"- Native/public transcript count: {native_public_count}",
        f"- Manual transcript count: {manual_count}",
        f"- Duplicate transcript count: {duplicate_transcript_count}",
        f"- Short transcript count: {short_transcript_count}",
        f"- Recommended next action: {recommended_next_action}",
        "",
        "## Transcripts by Source",
        "",
    ]
    source_rows = [
        {"source": source or "unknown", "transcript_count": count}
        for source, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    md_lines.extend(_markdown_table(["source", "transcript_count"], source_rows))
    md_lines.extend(["", "## Coverage by Year", ""])
    md_lines.extend(
        _markdown_table(
            [
                "label",
                "total_videos",
                "videos_with_transcripts",
                "videos_missing_transcripts",
                "coverage_rate",
            ],
            year_rows,
        )
    )
    md_lines.extend(["", "## Coverage by Creator (Top 25)", ""])
    md_lines.extend(
        _markdown_table(
            [
                "label",
                "total_videos",
                "videos_with_transcripts",
                "videos_missing_transcripts",
                "coverage_rate",
            ],
            creator_rows,
            limit=25,
        )
    )
    md_path = _write_text(md_path, "\n".join(md_lines) + "\n")
    return TranscriptProvenanceReportResult(
        csv_path=csv_path,
        md_path=md_path,
        methodology_note_path=methodology_note_path,
        total_videos=total_videos,
        videos_with_transcripts=videos_with_transcripts,
        videos_missing_transcripts=videos_missing_transcripts,
    )
