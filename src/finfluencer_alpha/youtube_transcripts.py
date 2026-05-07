from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
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

from .config import get_settings
from .db import connect, init_db, sqlite_path_from_url

PROVIDER_PACKAGE = "youtube-transcript-api"


@dataclass(frozen=True)
class TranscriptSegment:
    video_id: str
    segment_index: int
    start_seconds: float | None
    duration_seconds: float | None
    text: str


@dataclass(frozen=True)
class TranscriptFetchResult:
    video_id: str
    provider_name: str
    provider_version: str
    status: str
    language: str | None = None
    language_code: str | None = None
    is_generated: bool | None = None
    is_translatable: bool | None = None
    error_type: str | None = None
    error_message: str | None = None
    full_text: str | None = None
    full_text_sha256: str | None = None
    raw_json: str | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        return len(self.segments)


@dataclass(frozen=True)
class TranscriptVideoSelection:
    video_id: str
    channel_title: str | None
    published_at: str | None
    title: str | None


@dataclass(frozen=True)
class TranscriptCollectionResult:
    selected_videos: list[TranscriptVideoSelection]
    attempted_count: int
    status_counts: dict[str, int]
    dry_run: bool = False
    stopped_reason: str | None = None

    @property
    def selected_count(self) -> int:
        return len(self.selected_videos)

    @property
    def available_count(self) -> int:
        return self.status_counts.get("available", 0)


def _provider_version() -> str:
    try:
        return version(PROVIDER_PACKAGE)
    except PackageNotFoundError:
        return "unknown"


def _sanitize_error_message(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:1000]


def _status_result(video_id: str, status: str, exc: BaseException | None = None) -> TranscriptFetchResult:
    return TranscriptFetchResult(
        video_id=video_id,
        provider_name=get_settings().youtube_transcript_provider,
        provider_version=_provider_version(),
        status=status,
        error_type=type(exc).__name__ if exc else None,
        error_message=_sanitize_error_message(exc) if exc else None,
    )


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


def _select_transcript(transcript_list: Any, languages: list[str]) -> Any:
    try:
        return transcript_list.find_manually_created_transcript(languages)
    except NoTranscriptFound:
        pass
    try:
        return transcript_list.find_generated_transcript(languages)
    except NoTranscriptFound:
        pass
    return transcript_list.find_transcript(languages)


def _raw_segments(fetched: Any) -> list[dict[str, Any]]:
    if hasattr(fetched, "to_raw_data"):
        return list(fetched.to_raw_data())
    raw: list[dict[str, Any]] = []
    for item in fetched:
        if isinstance(item, dict):
            raw.append(item)
        else:
            raw.append(
                {
                    "text": getattr(item, "text", ""),
                    "start": getattr(item, "start", None),
                    "duration": getattr(item, "duration", None),
                }
            )
    return raw


def _segments_from_raw(video_id: str, raw_segments: list[dict[str, Any]]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for index, item in enumerate(raw_segments):
        segments.append(
            TranscriptSegment(
                video_id=video_id,
                segment_index=index,
                start_seconds=item.get("start"),
                duration_seconds=item.get("duration"),
                text=str(item.get("text") or "").strip(),
            )
        )
    return segments


def fetch_transcript_for_video(
    video_id: str,
    languages: list[str] | None = None,
) -> TranscriptFetchResult:
    settings = get_settings()
    language_list = languages or settings.youtube_transcript_language_list
    provider_name = settings.youtube_transcript_provider
    provider_version = _provider_version()
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        transcript = _select_transcript(transcript_list, language_list)
        fetched = transcript.fetch(
            preserve_formatting=settings.youtube_transcript_preserve_formatting
        )
        raw_segments = _raw_segments(fetched)
        segments = _segments_from_raw(video_id, raw_segments)
        full_text = " ".join(segment.text for segment in segments if segment.text).strip()
        full_text_sha256 = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        return TranscriptFetchResult(
            video_id=video_id,
            provider_name=provider_name,
            provider_version=provider_version,
            language=getattr(transcript, "language", None),
            language_code=getattr(transcript, "language_code", None),
            is_generated=getattr(transcript, "is_generated", None),
            is_translatable=getattr(transcript, "is_translatable", None),
            status="available",
            full_text=full_text,
            full_text_sha256=full_text_sha256,
            raw_json=json.dumps(raw_segments, ensure_ascii=False),
            segments=segments,
        )
    except (
        RequestBlocked,
        IpBlocked,
        TooManyRequests,
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
        CouldNotRetrieveTranscript,
    ) as exc:
        return _status_result(video_id, _error_status(exc), exc)
    except Exception as exc:
        return _status_result(video_id, _error_status(exc), exc)


def store_transcript_result(conn: sqlite3.Connection, result: TranscriptFetchResult) -> None:
    conn.execute(
        """
        INSERT INTO youtube_transcripts (
          video_id, provider_name, provider_version, language, language_code,
          is_generated, is_translatable, status, error_type, error_message,
          full_text, full_text_sha256, segment_count, raw_json, retrieved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(video_id) DO UPDATE SET
          provider_name = excluded.provider_name,
          provider_version = excluded.provider_version,
          language = excluded.language,
          language_code = excluded.language_code,
          is_generated = excluded.is_generated,
          is_translatable = excluded.is_translatable,
          status = excluded.status,
          error_type = excluded.error_type,
          error_message = excluded.error_message,
          full_text = excluded.full_text,
          full_text_sha256 = excluded.full_text_sha256,
          segment_count = excluded.segment_count,
          raw_json = excluded.raw_json,
          retrieved_at = CURRENT_TIMESTAMP
        """,
        (
            result.video_id,
            result.provider_name,
            result.provider_version,
            result.language,
            result.language_code,
            None if result.is_generated is None else int(result.is_generated),
            None if result.is_translatable is None else int(result.is_translatable),
            result.status,
            result.error_type,
            result.error_message,
            result.full_text,
            result.full_text_sha256,
            result.segment_count,
            result.raw_json,
        ),
    )
    conn.execute("DELETE FROM youtube_transcript_segments WHERE video_id = ?", (result.video_id,))
    if result.status == "available":
        conn.executemany(
            """
            INSERT INTO youtube_transcript_segments (
              video_id, segment_index, start_seconds, duration_seconds, text
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    segment.video_id,
                    segment.segment_index,
                    segment.start_seconds,
                    segment.duration_seconds,
                    segment.text,
                )
                for segment in result.segments
            ],
        )


def _select_videos(
    conn: sqlite3.Connection,
    limit: int,
    only_candidates: bool,
) -> list[TranscriptVideoSelection]:
    if only_candidates:
        rows = conn.execute(
            """
            SELECT DISTINCT
              y.video_id,
              y.channel_title,
              y.published_at,
              y.title
            FROM recommendation_candidates rc
            JOIN raw_youtube_videos y
              ON rc.platform = 'youtube' AND rc.source_id = y.video_id
            ORDER BY y.published_at DESC, y.video_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT video_id, channel_title, published_at, title
            FROM raw_youtube_videos
            ORDER BY published_at DESC, video_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        TranscriptVideoSelection(
            video_id=row["video_id"],
            channel_title=row["channel_title"],
            published_at=row["published_at"],
            title=row["title"],
        )
        for row in rows
    ]


def _backoff_seconds(error_count: int) -> float:
    return min(60.0, (2.0 ** max(error_count - 1, 0)) + random.uniform(0, 1))


def collect_transcripts_for_videos(
    limit: int | None = None,
    only_candidates: bool = False,
    dry_run: bool = False,
) -> TranscriptCollectionResult:
    settings = get_settings()
    selected_limit = limit or settings.youtube_transcript_max_videos_per_run
    if dry_run and not sqlite_path_from_url().exists():
        return TranscriptCollectionResult(
            selected_videos=[],
            attempted_count=0,
            status_counts={},
            dry_run=True,
        )
    if not dry_run:
        init_db()
    with connect() as conn:
        selected = _select_videos(conn, selected_limit, only_candidates)
        if dry_run:
            return TranscriptCollectionResult(
                selected_videos=selected,
                attempted_count=0,
                status_counts={},
                dry_run=True,
            )

        attempted = 0
        status_counts: dict[str, int] = {}
        blocked_errors = 0
        rate_limit_errors = 0
        stopped_reason: str | None = None

        for video in selected:
            attempts_for_video = 0
            while attempts_for_video < 2:
                attempts_for_video += 1
                attempted += 1
                result = fetch_transcript_for_video(
                    video.video_id,
                    languages=settings.youtube_transcript_language_list,
                )
                store_transcript_result(conn, result)
                conn.commit()
                status_counts[result.status] = status_counts.get(result.status, 0) + 1

                if result.status == "rate_limited" and attempts_for_video == 1:
                    rate_limit_errors += 1
                    if rate_limit_errors >= settings.max_rate_limit_errors_per_run:
                        stopped_reason = "rate_limited"
                        break
                    time.sleep(_backoff_seconds(rate_limit_errors))
                    continue
                if result.status == "rate_limited":
                    rate_limit_errors += 1
                    if rate_limit_errors >= settings.max_rate_limit_errors_per_run:
                        stopped_reason = "rate_limited"
                    break
                if result.status == "request_blocked":
                    blocked_errors += 1
                    if blocked_errors >= settings.max_blocked_errors_per_run:
                        stopped_reason = "request_blocked"
                    break
                if result.status == "ip_blocked":
                    stopped_reason = "ip_blocked"
                    break
                break

            if stopped_reason:
                break

    return TranscriptCollectionResult(
        selected_videos=selected,
        attempted_count=attempted,
        status_counts=status_counts,
        dry_run=False,
        stopped_reason=stopped_reason,
    )
