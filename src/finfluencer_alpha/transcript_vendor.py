from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .classify import classify_text
from .config import PROJECT_ROOT, ensure_data_dirs, get_settings
from .db import connect, init_db
from .ticker_extract import extract_tickers
from .youtube_transcripts import (
    BLOCKED_TRANSCRIPT_STATUSES,
    TranscriptFetchResult,
    TranscriptSegment,
    _pending_cooldown,
    _priority_score,
    store_transcript_result,
)

TRANSCRIPT_VENDOR_BATCH_COLUMNS = [
    "video_id",
    "url",
    "creator",
    "creator_category",
    "published_at",
    "title",
    "description",
    "priority_score",
    "ticker_signal_count",
    "recommendation_keyword_signal",
    "current_view_count",
    "current_like_count",
    "current_comment_count",
]

REQUIRED_TRANSCRIPT_IMPORT_COLUMNS = {
    "video_id",
    "transcript_text",
    "transcript_source",
    "provider_name",
    "retrieval_method",
    "is_asr_generated",
    "retrieved_at",
    "notes",
}


@dataclass(frozen=True)
class VendorBatchResult:
    output_path: Path
    row_count: int
    creator_counts: dict[str, int]


@dataclass(frozen=True)
class TranscriptImportResult:
    imported_count: int
    overwritten_count: int
    segment_count: int
    source: str


@dataclass(frozen=True)
class VendorCandidate:
    video_id: str
    url: str
    creator: str
    creator_category: str
    published_at: str
    title: str
    description: str
    priority_score: float
    ticker_signal_count: int
    recommendation_keyword_signal: int
    current_view_count: int | None
    current_like_count: int | None
    current_comment_count: int | None

    def as_row(self) -> dict[str, object]:
        return {
            "video_id": self.video_id,
            "url": self.url,
            "creator": self.creator,
            "creator_category": self.creator_category,
            "published_at": self.published_at,
            "title": self.title,
            "description": self.description,
            "priority_score": round(self.priority_score, 3),
            "ticker_signal_count": self.ticker_signal_count,
            "recommendation_keyword_signal": self.recommendation_keyword_signal,
            "current_view_count": self.current_view_count,
            "current_like_count": self.current_like_count,
            "current_comment_count": self.current_comment_count,
        }


def _resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _clean(value: object) -> str:
    return str(value or "").strip()


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_from_csv(value: object) -> bool:
    normalized = _clean(value).lower()
    if normalized in {"1", "true", "t", "yes", "y", "asr", "generated"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "manual", "human"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _validate_retrieved_at(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("retrieved_at is required")
    datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    return cleaned


def _published_timestamp(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _recommendation_signal(text: str) -> int:
    result = classify_text(text)
    return int(
        result.stance in {"bullish", "bearish"}
        and result.actionability_score >= 2
        and result.label not in {"retrospective_claim", "news_only"}
    )


def _engagement_score(view_count: int | None, like_count: int | None, comment_count: int | None) -> float:
    views = math.log1p(max(view_count or 0, 0)) / 6
    likes = math.log1p(max(like_count or 0, 0)) / 5
    comments = math.log1p(max(comment_count or 0, 0)) / 4
    return min(4.0, views + likes + comments)


def _candidate_from_row(row: Any) -> VendorCandidate:
    text = f"{row['title'] or ''} {row['description'] or ''}"
    base_score, _reason = _priority_score(row["title"], row["description"], row["channel_title"])
    ticker_count = len({mention.ticker for mention in extract_tickers(text)})
    rec_signal = _recommendation_signal(text)
    view_count = _int_or_none(row["current_view_count"])
    like_count = _int_or_none(row["current_like_count"])
    comment_count = _int_or_none(row["current_comment_count"])
    priority_score = (
        base_score
        + min(ticker_count, 5) * 2.0
        + rec_signal * 5.0
        + _engagement_score(view_count, like_count, comment_count)
    )
    return VendorCandidate(
        video_id=row["video_id"],
        url=row["url"] or f"https://www.youtube.com/watch?v={row['video_id']}",
        creator=row["channel_title"] or row["channel_id"] or "unknown",
        creator_category=row["creator_category"] or "unknown",
        published_at=row["published_at"] or "",
        title=row["title"] or "",
        description=row["description"] or "",
        priority_score=priority_score,
        ticker_signal_count=ticker_count,
        recommendation_keyword_signal=rec_signal,
        current_view_count=view_count,
        current_like_count=like_count,
        current_comment_count=comment_count,
    )


def _eligible_vendor_candidates(include_blocked: bool = False) -> list[VendorCandidate]:
    init_db()
    cooldown_hours = get_settings().transcript_queue_cooldown_hours
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              y.video_id,
              y.url,
              y.channel_id,
              y.channel_title,
              y.creator_category,
              y.published_at,
              y.title,
              y.description,
              y.current_view_count,
              y.current_like_count,
              y.current_comment_count,
              yt.status AS transcript_status,
              yt.full_text,
              tfq.transcript_status AS queue_status,
              tfq.next_eligible_attempt_at
            FROM raw_youtube_videos y
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
            LEFT JOIN transcript_fetch_queue tfq
              ON tfq.video_id = y.video_id
            WHERE COALESCE(y.excluded_flag, 0) = 0
            ORDER BY y.published_at DESC, y.video_id
            """
        ).fetchall()

    candidates: list[VendorCandidate] = []
    for row in rows:
        if row["transcript_status"] == "available" and _clean(row["full_text"]):
            continue
        if row["queue_status"] in {"available", "excluded"}:
            continue
        if not include_blocked:
            if row["queue_status"] in BLOCKED_TRANSCRIPT_STATUSES:
                continue
            if row["transcript_status"] in BLOCKED_TRANSCRIPT_STATUSES:
                continue
            if _pending_cooldown(row, cooldown_hours):
                continue
        candidates.append(_candidate_from_row(row))

    candidates.sort(
        key=lambda item: (
            -item.priority_score,
            -_published_timestamp(item.published_at),
            item.video_id,
        )
    )
    return candidates


def select_transcript_vendor_batch(
    limit: int,
    include_blocked: bool = False,
) -> list[VendorCandidate]:
    candidates = _eligible_vendor_candidates(include_blocked=include_blocked)
    grouped: dict[str, deque[VendorCandidate]] = defaultdict(deque)
    for candidate in candidates:
        grouped[candidate.creator].append(candidate)

    creator_order = sorted(
        grouped,
        key=lambda creator: (
            -grouped[creator][0].priority_score,
            -len(grouped[creator]),
            creator.lower(),
        ),
    )

    selected: list[VendorCandidate] = []
    while len(selected) < limit and creator_order:
        next_order: list[str] = []
        for creator in creator_order:
            if len(selected) >= limit:
                break
            queue = grouped[creator]
            if not queue:
                continue
            selected.append(queue.popleft())
            if queue:
                next_order.append(creator)
        creator_order = next_order
    return selected


def export_transcript_vendor_batch(
    limit: int,
    output_path: Path,
    include_blocked: bool = False,
) -> VendorBatchResult:
    ensure_data_dirs()
    output_path = _resolve_project_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected = select_transcript_vendor_batch(limit=limit, include_blocked=include_blocked)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRANSCRIPT_VENDOR_BATCH_COLUMNS)
        writer.writeheader()
        for candidate in selected:
            writer.writerow(candidate.as_row())
    creator_counts: dict[str, int] = {}
    for candidate in selected:
        creator_counts[candidate.creator] = creator_counts.get(candidate.creator, 0) + 1
    return VendorBatchResult(output_path, len(selected), creator_counts)


def _load_import_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Transcript CSV is missing a header row")
        missing = REQUIRED_TRANSCRIPT_IMPORT_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError("Transcript CSV is missing required columns: " + ", ".join(sorted(missing)))
        return [dict(row) for row in reader]


def _segments_from_json(video_id: str, raw_json: str) -> list[TranscriptSegment]:
    data = json.loads(raw_json)
    if not isinstance(data, list):
        raise ValueError("segments_json must be a JSON list")
    segments: list[TranscriptSegment] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError("segments_json entries must be objects")
        text = _clean(item.get("text") or item.get("segment_text"))
        if not text:
            continue
        start = _float_or_none(item.get("start_seconds", item.get("start")))
        duration = _float_or_none(item.get("duration_seconds", item.get("duration")))
        end = _float_or_none(item.get("end_seconds", item.get("end")))
        if duration is None and start is not None and end is not None:
            duration = max(0.0, end - start)
        segments.append(TranscriptSegment(video_id, index, start, duration, text))
    return segments


def _segments_from_import_rows(
    video_id: str,
    rows: list[dict[str, str]],
    full_text: str,
) -> list[TranscriptSegment]:
    first = rows[0]
    if _clean(first.get("segments_json")):
        segments = _segments_from_json(video_id, first["segments_json"])
        if segments:
            return segments

    has_segment_columns = any(
        _clean(row.get(column))
        for row in rows
        for column in ("segment_text", "start_seconds", "duration_seconds", "end_seconds")
    )
    if has_segment_columns:
        segments: list[TranscriptSegment] = []
        for index, row in enumerate(rows):
            text = _clean(row.get("segment_text")) or (_clean(row.get("transcript_text")) if len(rows) == 1 else "")
            if not text:
                continue
            start = _float_or_none(row.get("start_seconds"))
            duration = _float_or_none(row.get("duration_seconds"))
            end = _float_or_none(row.get("end_seconds"))
            if duration is None and start is not None and end is not None:
                duration = max(0.0, end - start)
            segments.append(TranscriptSegment(video_id, index, start, duration, text))
        if segments:
            return segments

    return [TranscriptSegment(video_id, 0, 0.0, None, full_text)]


def import_transcripts_csv(
    path: Path,
    source: str,
    overwrite: bool = False,
) -> TranscriptImportResult:
    init_db()
    path = _resolve_project_path(path)
    rows = _load_import_rows(path)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_clean(row.get("video_id"))].append(row)

    errors: list[str] = []
    imported: list[tuple[TranscriptFetchResult, bool]] = []
    with connect() as conn:
        for video_id, group in grouped.items():
            first = group[0]
            if not video_id:
                errors.append("missing video_id")
                continue
            video_exists = conn.execute(
                "SELECT 1 FROM raw_youtube_videos WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if not video_exists:
                errors.append(f"{video_id}: unknown video_id")
                continue

            full_text = _clean(first.get("transcript_text"))
            if not full_text:
                errors.append(f"{video_id}: empty transcript_text")
                continue

            existing = conn.execute(
                """
                SELECT status, full_text
                FROM youtube_transcripts
                WHERE video_id = ?
                """,
                (video_id,),
            ).fetchone()
            existing_available = bool(
                existing and existing["status"] == "available" and _clean(existing["full_text"])
            )
            if existing_available and not overwrite:
                errors.append(f"{video_id}: transcript already exists; pass --overwrite to replace it")
                continue

            transcript_source = _clean(first.get("transcript_source"))
            provider_name = _clean(first.get("provider_name"))
            retrieval_method = _clean(first.get("retrieval_method"))
            if not transcript_source:
                errors.append(f"{video_id}: transcript_source is required")
                continue
            if not provider_name:
                errors.append(f"{video_id}: provider_name is required")
                continue
            if not retrieval_method:
                errors.append(f"{video_id}: retrieval_method is required")
                continue
            try:
                is_asr_generated = _bool_from_csv(first.get("is_asr_generated"))
                retrieved_at = _validate_retrieved_at(_clean(first.get("retrieved_at")))
                segments = _segments_from_import_rows(video_id, group, full_text)
            except (ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{video_id}: {exc}")
                continue
            if not segments:
                errors.append(f"{video_id}: no transcript segments could be created")
                continue

            normalized_segments = [
                {
                    "text": segment.text,
                    "start": segment.start_seconds,
                    "duration": segment.duration_seconds,
                }
                for segment in segments
            ]
            text_for_hash = " ".join(segment.text for segment in segments if segment.text).strip()
            if not text_for_hash:
                text_for_hash = full_text
            source_confidence = _float_or_none(first.get("source_confidence"))
            if source_confidence is None:
                source_confidence = 0.80 if is_asr_generated else 0.90
            result = TranscriptFetchResult(
                video_id=video_id,
                provider_name=provider_name,
                provider_version=_clean(first.get("provider_version")),
                status="available",
                transcript_source=transcript_source,
                retrieval_method=retrieval_method,
                retrieval_status="available",
                retrieved_at=retrieved_at,
                provider_notes=_clean(first.get("notes")),
                is_generated=is_asr_generated,
                is_asr_generated=is_asr_generated,
                is_translatable=None,
                full_text=full_text,
                full_text_sha256=hashlib.sha256(text_for_hash.encode("utf-8")).hexdigest(),
                raw_json=json.dumps(normalized_segments, ensure_ascii=False),
                segments=segments,
                source_confidence=source_confidence,
            )
            imported.append((result, existing_available))

        if errors:
            raise ValueError("Transcript CSV validation failed: " + "; ".join(errors[:10]))

        overwritten = 0
        segment_count = 0
        for result, existing_available in imported:
            store_transcript_result(conn, result)
            conn.execute(
                """
                UPDATE transcript_fetch_queue
                SET transcript_status = 'available',
                    last_attempted_at = ?,
                    next_eligible_attempt_at = ?
                WHERE video_id = ?
                """,
                (result.retrieved_at, result.retrieved_at, result.video_id),
            )
            overwritten += int(existing_available)
            segment_count += len(result.segments)
        conn.commit()

    return TranscriptImportResult(
        imported_count=len(imported),
        overwritten_count=overwritten,
        segment_count=segment_count,
        source=source,
    )


def _covered(value: dict[str, object]) -> bool:
    return bool(value["covered"])


def _metric_bucket(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value < 1_000:
        return "0-999"
    if value < 10_000:
        return "1k-9.9k"
    if value < 100_000:
        return "10k-99k"
    if value < 1_000_000:
        return "100k-999k"
    return "1M+"


def _published_year(value: str) -> str:
    return value[:4] if len(value) >= 4 and value[:4].isdigit() else "unknown"


def _coverage_records() -> list[dict[str, object]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              y.video_id,
              y.channel_title,
              y.creator_category,
              y.published_at,
              y.title,
              y.description,
              y.current_view_count,
              y.current_like_count,
              y.current_comment_count,
              yt.status,
              yt.full_text
            FROM raw_youtube_videos y
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
            WHERE COALESCE(y.excluded_flag, 0) = 0
            """
        ).fetchall()
    records: list[dict[str, object]] = []
    for row in rows:
        text = f"{row['title'] or ''} {row['description'] or ''}"
        records.append(
            {
                "video_id": row["video_id"],
                "creator": row["channel_title"] or "unknown",
                "creator_category": row["creator_category"] or "unknown",
                "year": _published_year(row["published_at"] or ""),
                "view_count_bucket": _metric_bucket(_int_or_none(row["current_view_count"])),
                "like_count_bucket": _metric_bucket(_int_or_none(row["current_like_count"])),
                "comment_count_bucket": _metric_bucket(_int_or_none(row["current_comment_count"])),
                "title_keyword_signal": "high_signal" if _recommendation_signal(text) else "low_signal",
                "covered": row["status"] == "available" and bool(_clean(row["full_text"])),
            }
        )
    return records


def _summarize(records: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"covered": 0, "uncovered": 0})
    for record in records:
        label = _clean(record.get(key)) or "unknown"
        grouped[label]["covered" if _covered(record) else "uncovered"] += 1
    rows: list[dict[str, object]] = []
    for label, counts in grouped.items():
        total = counts["covered"] + counts["uncovered"]
        rows.append(
            {
                key: label,
                "covered": counts["covered"],
                "uncovered": counts["uncovered"],
                "total": total,
                "coverage_rate": round(counts["covered"] / total, 3) if total else 0,
            }
        )
    rows.sort(key=lambda row: (-int(row["total"]), str(row[key])))
    return rows


def build_transcript_coverage_bias_report() -> dict[str, list[dict[str, object]]]:
    records = _coverage_records()
    return {
        "creator": _summarize(records, "creator"),
        "creator_category": _summarize(records, "creator_category"),
        "year": _summarize(records, "year"),
        "view_count_bucket": _summarize(records, "view_count_bucket"),
        "like_count_bucket": _summarize(records, "like_count_bucket"),
        "comment_count_bucket": _summarize(records, "comment_count_bucket"),
        "title_keyword_signal": _summarize(records, "title_keyword_signal"),
    }


def build_transcript_priority_report(limit: int = 1000) -> dict[str, object]:
    candidates = _eligible_vendor_candidates(include_blocked=False)
    selected = select_transcript_vendor_batch(limit=limit, include_blocked=False)
    creator_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    for candidate in selected:
        creator_counts[candidate.creator] += 1
        category_counts[candidate.creator_category] += 1
    top_creator_share = (
        max(creator_counts.values()) / len(selected) if selected and creator_counts else 0.0
    )
    with connect() as conn:
        observed = conn.execute(
            """
            SELECT
              COUNT(DISTINCT yt.video_id) AS available_count,
              COUNT(tre.transcript_event_id) AS event_count
            FROM youtube_transcripts yt
            LEFT JOIN transcript_recommendation_events tre
              ON tre.video_id = yt.video_id
            WHERE yt.status = 'available'
              AND COALESCE(yt.full_text, '') != ''
            """
        ).fetchone()
    available_count = int(observed["available_count"] or 0)
    event_count = int(observed["event_count"] or 0)
    observed_event_rate = event_count / available_count if available_count else 0.0
    fallback_rate = 0.08
    estimated_rate = observed_event_rate or fallback_rate
    high_signal_count = sum(
        1
        for candidate in selected
        if candidate.recommendation_keyword_signal or candidate.ticker_signal_count
    )
    estimated_candidate_yield = round(high_signal_count * estimated_rate, 1)
    recommended_size = min(limit, len(candidates))
    return {
        "eligible_count": len(candidates),
        "selected_count": len(selected),
        "top_creators": sorted(
            [{"creator": key, "count": value} for key, value in creator_counts.items()],
            key=lambda row: (-int(row["count"]), str(row["creator"])),
        )[:10],
        "top_categories": sorted(
            [{"creator_category": key, "count": value} for key, value in category_counts.items()],
            key=lambda row: (-int(row["count"]), str(row["creator_category"])),
        )[:10],
        "top_high_signal_videos": [
            candidate.as_row()
            for candidate in sorted(selected, key=lambda item: -item.priority_score)[:20]
        ],
        "creator_concentration": {
            "distinct_creators": len(creator_counts),
            "top_creator_share": round(top_creator_share, 3),
        },
        "estimated_candidate_yield": {
            "observed_event_rate": round(observed_event_rate, 3),
            "estimated_events": estimated_candidate_yield,
            "high_signal_videos": high_signal_count,
        },
        "recommended_provider_batch_size": recommended_size,
    }
