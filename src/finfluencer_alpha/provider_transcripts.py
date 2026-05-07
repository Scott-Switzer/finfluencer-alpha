from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from .config import EXPORTS_DIR, IMPORTS_DIR, PROJECT_ROOT, ensure_data_dirs, get_settings
from .db import connect, init_db

YOUTUBETRANSCRIPT_DEV_BASE_URL = "https://www.youtubetranscript.dev/api/v2"
TRANSCRIPTAPI_BASE_URL = "https://transcriptapi.com/api/v2"
MAX_YOUTUBETRANSCRIPT_DEV_BATCH_SIZE = 100
PROVIDER_FAILURE_COLUMNS = [
    "video_id",
    "provider",
    "status",
    "error_type",
    "error_message",
    "retryable",
]
PROVIDER_IMPORT_COLUMNS = [
    "video_id",
    "transcript_text",
    "transcript_source",
    "provider_name",
    "retrieval_method",
    "is_asr_generated",
    "retrieved_at",
    "notes",
    "language",
    "raw_provider_source",
    "segment_json",
    "source_confidence",
]


@dataclass(frozen=True)
class ProviderVideo:
    video_id: str
    url: str


@dataclass(frozen=True)
class ProviderTranscriptRecord:
    video_id: str
    transcript_text: str
    transcript_source: str
    provider_name: str
    retrieval_method: str
    is_asr_generated: bool
    retrieved_at: str
    notes: str
    language: str
    raw_provider_source: str
    segments: list[dict[str, object]]
    source_confidence: str

    def as_csv_row(self) -> dict[str, object]:
        return {
            "video_id": self.video_id,
            "transcript_text": self.transcript_text,
            "transcript_source": self.transcript_source,
            "provider_name": self.provider_name,
            "retrieval_method": self.retrieval_method,
            "is_asr_generated": int(self.is_asr_generated),
            "retrieved_at": self.retrieved_at,
            "notes": self.notes,
            "language": self.language,
            "raw_provider_source": self.raw_provider_source,
            "segment_json": json.dumps(self.segments, ensure_ascii=False),
            "source_confidence": self.source_confidence,
        }


@dataclass(frozen=True)
class ProviderFailure:
    video_id: str
    provider: str
    status: str
    error_type: str
    error_message: str
    retryable: bool = False

    def as_csv_row(self) -> dict[str, object]:
        return {
            "video_id": self.video_id,
            "provider": self.provider,
            "status": self.status,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "retryable": int(self.retryable),
        }


@dataclass(frozen=True)
class ProviderCollectionResult:
    provider: str
    attempted_count: int
    successful_count: int
    failed_count: int
    skipped_existing_count: int
    output_path: Path
    failure_path: Path


class ProviderConfigError(ValueError):
    pass


class ProviderRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _chunks(values: list[ProviderVideo], size: int) -> list[list[ProviderVideo]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _load_vendor_videos(path: Path, limit: int | None) -> list[ProviderVideo]:
    path = _resolve_project_path(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"video_id", "url"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise ValueError("Provider input CSV must include video_id and url columns")
        seen: set[str] = set()
        videos: list[ProviderVideo] = []
        for row in reader:
            video_id = _clean(row.get("video_id"))
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            videos.append(
                ProviderVideo(
                    video_id=video_id,
                    url=_clean(row.get("url")) or f"https://www.youtube.com/watch?v={video_id}",
                )
            )
            if limit is not None and len(videos) >= limit:
                break
    return videos


def _existing_available_video_ids(video_ids: list[str]) -> set[str]:
    if not video_ids:
        return set()
    init_db()
    with connect() as conn:
        placeholders = ",".join("?" for _ in video_ids)
        rows = conn.execute(
            f"""
            SELECT video_id
            FROM youtube_transcripts
            WHERE video_id IN ({placeholders})
              AND status = 'available'
              AND COALESCE(full_text, '') != ''
            """,
            video_ids,
        ).fetchall()
    return {row["video_id"] for row in rows}


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, object] | None = None,
    payload: dict[str, object] | None = None,
    max_retries: int = 2,
    timeout: int = 60,
) -> tuple[dict[str, Any], int]:
    retryable_statuses = {429, 500, 502, 503, 504}
    for attempt in range(max_retries + 1):
        response = session.request(
            method,
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=timeout,
        )
        if response.status_code in retryable_statuses and attempt < max_retries:
            retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
            try:
                sleep_seconds = int(retry_after) if retry_after else 2**attempt
            except ValueError:
                sleep_seconds = 2**attempt
            time.sleep(max(1, sleep_seconds))
            continue
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {"error": response.text[:500]}
            message = json.dumps(body, ensure_ascii=False)[:1000]
            raise ProviderRequestError(
                f"Provider request failed with HTTP {response.status_code}: {message}",
                status_code=response.status_code,
                retryable=response.status_code in retryable_statuses,
            )
        return response.json(), response.status_code
    raise ProviderRequestError("Provider request exhausted retry attempts", retryable=True)


def _provider_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _time_number(value: object, *, scale: float = 1.0) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value) / scale
    except (TypeError, ValueError):
        return None


def _normalized_segment(
    item: dict[str, Any],
    *,
    time_scale: float,
) -> dict[str, object] | None:
    text = _clean(item.get("text"))
    if not text:
        return None
    start = _time_number(item.get("start_seconds", item.get("start")), scale=time_scale)
    duration = _time_number(item.get("duration_seconds", item.get("duration")), scale=time_scale)
    end = _time_number(item.get("end_seconds", item.get("end")), scale=time_scale)
    if duration is None and start is not None and end is not None:
        duration = max(0.0, end - start)
    if end is None and start is not None and duration is not None:
        end = start + duration
    return {
        "text": text,
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": duration,
    }


def _segments_from_transcript_value(
    transcript: Any,
    *,
    time_scale: float,
) -> list[dict[str, object]]:
    if isinstance(transcript, list):
        raw_segments = transcript
    elif isinstance(transcript, dict):
        raw_segments = transcript.get("segments") or transcript.get("transcript") or []
    else:
        raw_segments = []
    segments: list[dict[str, object]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        segment = _normalized_segment(item, time_scale=time_scale)
        if segment:
            segments.append(segment)
    return segments


def _text_from_transcript_value(transcript: Any, segments: list[dict[str, object]]) -> str:
    if isinstance(transcript, dict):
        text = _clean(transcript.get("text"))
        if text:
            return text
    if isinstance(transcript, str):
        text = _clean(transcript)
        if text:
            return text
    return " ".join(_clean(segment.get("text")) for segment in segments if segment.get("text")).strip()


def _failure_from_result(
    video_id: str,
    provider: str,
    result: dict[str, Any],
) -> ProviderFailure:
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    message = (
        _clean(error.get("message"))
        or _clean(result.get("error_message"))
        or _clean(result.get("message"))
        or "provider did not return a transcript"
    )
    error_type = _clean(error.get("code")) or _clean(result.get("status")) or "provider_failure"
    return ProviderFailure(
        video_id=video_id,
        provider=provider,
        status=_clean(result.get("status")) or "failed",
        error_type=error_type,
        error_message=message[:1000],
        retryable=False,
    )


def _record_from_youtubetranscript_dev_result(
    result: dict[str, Any],
    *,
    allow_asr: bool,
    retrieved_at: str,
) -> ProviderTranscriptRecord | ProviderFailure:
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    video_id = _clean(data.get("video_id") or result.get("video_id"))
    transcript = data.get("transcript") if isinstance(data.get("transcript"), dict) else {}
    raw_source = _clean(transcript.get("source") or data.get("source"))
    is_asr = raw_source.lower() == "asr"
    if is_asr and not allow_asr:
        return ProviderFailure(
            video_id=video_id,
            provider="YouTubeTranscript.dev",
            status="failed",
            error_type="asr_not_allowed",
            error_message="Provider returned ASR output while --allow-asr was not set.",
        )
    segments = _segments_from_transcript_value(transcript, time_scale=1000.0)
    text = _text_from_transcript_value(transcript, segments)
    if not video_id or not text:
        return _failure_from_result(video_id, "YouTubeTranscript.dev", result)
    request_id = _clean(result.get("request_id"))
    notes = [
        "provider_status=completed",
        f"provider_source={raw_source or 'unknown'}",
    ]
    if request_id:
        notes.append(f"request_id={request_id}")
    return ProviderTranscriptRecord(
        video_id=video_id,
        transcript_text=text,
        transcript_source="external_provider",
        provider_name="YouTubeTranscript.dev",
        retrieval_method="provider_caption_api",
        is_asr_generated=is_asr,
        retrieved_at=retrieved_at,
        notes="; ".join(notes),
        language=_clean(transcript.get("language") or data.get("language")),
        raw_provider_source=raw_source,
        segments=segments or [{"text": text, "start_seconds": 0.0, "end_seconds": None, "duration_seconds": None}],
        source_confidence="medium" if is_asr else "high",
    )


def _collect_youtubetranscript_dev_batch(
    session: requests.Session,
    videos: list[ProviderVideo],
    *,
    api_key: str,
    language: str,
    timestamps: bool,
    captions_only: bool,
    allow_asr: bool,
) -> tuple[list[ProviderTranscriptRecord], list[ProviderFailure]]:
    if captions_only and allow_asr:
        raise ProviderConfigError("--captions-only cannot be combined with --allow-asr")
    payload: dict[str, object] = {
        "video_ids": [video.video_id for video in videos],
        "source": "auto",
        "allow_asr": bool(allow_asr),
    }
    if language:
        payload["language"] = language
    if timestamps:
        payload["format"] = {"timestamp": True}
    response, _status_code = _request_json(
        session,
        "POST",
        f"{YOUTUBETRANSCRIPT_DEV_BASE_URL}/batch",
        headers=_provider_headers(api_key),
        payload=payload,
    )
    batch_id = _clean(response.get("batch_id"))
    results = response.get("results") if isinstance(response.get("results"), list) else []
    processing = sum(1 for result in results if _clean(result.get("status")) == "processing")
    poll_url = _clean(response.get("poll_url")) or (
        f"{YOUTUBETRANSCRIPT_DEV_BASE_URL}/batch/{batch_id}" if batch_id else ""
    )
    poll_attempts = 0
    while processing and poll_url and poll_attempts < 24:
        poll_attempts += 1
        time.sleep(5)
        response, _status_code = _request_json(
            session,
            "GET",
            poll_url,
            headers=_provider_headers(api_key),
        )
        results = response.get("results") if isinstance(response.get("results"), list) else results
        processing = sum(1 for result in results if _clean(result.get("status")) == "processing")

    retrieved_at = _utc_now_iso()
    records: list[ProviderTranscriptRecord] = []
    failures: list[ProviderFailure] = []
    returned_ids: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        video_id = _clean(data.get("video_id") or result.get("video_id"))
        if video_id:
            returned_ids.add(video_id)
        status = _clean(result.get("status"))
        if status not in {"completed", "success"}:
            failures.append(_failure_from_result(video_id, "YouTubeTranscript.dev", result))
            continue
        record = _record_from_youtubetranscript_dev_result(
            result,
            allow_asr=allow_asr,
            retrieved_at=retrieved_at,
        )
        if isinstance(record, ProviderFailure):
            failures.append(record)
        else:
            records.append(record)
    for video in videos:
        if video.video_id not in returned_ids:
            failures.append(
                ProviderFailure(
                    video_id=video.video_id,
                    provider="YouTubeTranscript.dev",
                    status="missing",
                    error_type="missing_result",
                    error_message="Provider response did not include this video_id.",
                    retryable=True,
                )
            )
    return records, failures


def _record_from_transcriptapi_payload(
    video: ProviderVideo,
    payload: dict[str, Any],
    *,
    retrieved_at: str,
) -> ProviderTranscriptRecord | ProviderFailure:
    transcript = payload.get("transcript")
    segments = _segments_from_transcript_value(transcript, time_scale=1.0)
    text = _text_from_transcript_value(transcript, segments)
    if not text:
        return ProviderFailure(
            video_id=video.video_id,
            provider="TranscriptAPI.com",
            status="failed",
            error_type="no_transcript_text",
            error_message="Provider response did not include transcript text.",
        )
    return ProviderTranscriptRecord(
        video_id=_clean(payload.get("video_id")) or video.video_id,
        transcript_text=text,
        transcript_source="external_provider",
        provider_name="TranscriptAPI.com",
        retrieval_method="provider_transcript_api",
        is_asr_generated=False,
        retrieved_at=retrieved_at,
        notes="provider_status=completed",
        language=_clean(payload.get("language")),
        raw_provider_source=_clean(payload.get("source") or "caption"),
        segments=segments or [{"text": text, "start_seconds": 0.0, "end_seconds": None, "duration_seconds": None}],
        source_confidence="high",
    )


def _collect_transcriptapi_video(
    session: requests.Session,
    video: ProviderVideo,
    *,
    api_key: str,
    timestamps: bool,
) -> tuple[list[ProviderTranscriptRecord], list[ProviderFailure]]:
    try:
        payload, _status_code = _request_json(
            session,
            "GET",
            f"{TRANSCRIPTAPI_BASE_URL}/youtube/transcript",
            headers={"Authorization": f"Bearer {api_key}"},
            params={
                "video_url": video.url or video.video_id,
                "format": "json",
                "include_timestamp": str(bool(timestamps)).lower(),
                "send_metadata": "true",
            },
        )
    except ProviderRequestError as exc:
        return [], [
            ProviderFailure(
                video_id=video.video_id,
                provider="TranscriptAPI.com",
                status=f"http_{exc.status_code or 'error'}",
                error_type="provider_request_error",
                error_message=str(exc)[:1000],
                retryable=exc.retryable,
            )
        ]
    record = _record_from_transcriptapi_payload(video, payload, retrieved_at=_utc_now_iso())
    if isinstance(record, ProviderFailure):
        return [], [record]
    return [record], []


def _write_import_csv(path: Path, records: list[ProviderTranscriptRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVIDER_IMPORT_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_csv_row())


def _write_failure_csv(path: Path, failures: list[ProviderFailure]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVIDER_FAILURE_COLUMNS)
        writer.writeheader()
        for failure in failures:
            writer.writerow(failure.as_csv_row())


def collect_provider_transcripts(
    *,
    provider: str,
    input_path: Path,
    output_path: Path,
    limit: int,
    batch_size: int,
    language: str,
    timestamps: bool,
    captions_only: bool,
    allow_asr: bool,
    confirm_provider_run: bool,
    skip_existing: bool = True,
) -> ProviderCollectionResult:
    if not confirm_provider_run:
        raise ProviderConfigError("Refusing provider transcript run without --confirm-provider-run.")
    provider = provider.strip().lower()
    if provider not in {"youtubetranscript_dev", "transcriptapi"}:
        raise ProviderConfigError(f"Unsupported provider: {provider}")
    if limit < 1:
        raise ProviderConfigError("--limit must be at least 1")
    if batch_size < 1:
        raise ProviderConfigError("--batch-size must be at least 1")
    if provider == "youtubetranscript_dev" and batch_size > MAX_YOUTUBETRANSCRIPT_DEV_BATCH_SIZE:
        raise ProviderConfigError("YouTubeTranscript.dev batch-size must be <= 100")

    ensure_data_dirs()
    output_path = _resolve_project_path(output_path)
    failure_path = EXPORTS_DIR / "provider_transcript_failures.csv"
    videos = _load_vendor_videos(input_path, limit=limit)
    existing = _existing_available_video_ids([video.video_id for video in videos]) if skip_existing else set()
    selected = [video for video in videos if video.video_id not in existing]
    settings = get_settings()

    records: list[ProviderTranscriptRecord] = []
    failures: list[ProviderFailure] = []
    with requests.Session() as session:
        if provider == "youtubetranscript_dev":
            api_key = settings.youtubetranscript_dev_api_key
            if not api_key:
                raise ProviderConfigError("Missing YOUTUBETRANSCRIPT_DEV_API_KEY.")
            for group in _chunks(selected, batch_size):
                try:
                    group_records, group_failures = _collect_youtubetranscript_dev_batch(
                        session,
                        group,
                        api_key=api_key,
                        language=language,
                        timestamps=timestamps,
                        captions_only=captions_only,
                        allow_asr=allow_asr,
                    )
                except ProviderRequestError as exc:
                    if exc.status_code in {401, 402}:
                        raise
                    group_records = []
                    group_failures = [
                        ProviderFailure(
                            video_id=video.video_id,
                            provider="YouTubeTranscript.dev",
                            status=f"http_{exc.status_code or 'error'}",
                            error_type="provider_request_error",
                            error_message=str(exc)[:1000],
                            retryable=exc.retryable,
                        )
                        for video in group
                    ]
                records.extend(group_records)
                failures.extend(group_failures)
        else:
            api_key = settings.transcriptapi_key
            if not api_key:
                raise ProviderConfigError("Missing TRANSCRIPTAPI_KEY.")
            for video in selected[:limit]:
                group_records, group_failures = _collect_transcriptapi_video(
                    session,
                    video,
                    api_key=api_key,
                    timestamps=timestamps,
                )
                records.extend(group_records)
                failures.extend(group_failures)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.parent == (PROJECT_ROOT / "data" / "imports") and not IMPORTS_DIR.exists():
        IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_import_csv(output_path, records)
    _write_failure_csv(failure_path, failures)
    return ProviderCollectionResult(
        provider=provider,
        attempted_count=len(selected),
        successful_count=len(records),
        failed_count=len(failures),
        skipped_existing_count=len(existing),
        output_path=output_path,
        failure_path=failure_path,
    )
