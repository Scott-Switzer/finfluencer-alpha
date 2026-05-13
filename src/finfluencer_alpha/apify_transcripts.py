from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from .config import DATA_DIR, ensure_data_dirs, get_settings
from .db import connect, init_db
from .youtube_transcripts import (
    TranscriptFetchResult,
    TranscriptSegment,
    store_transcript_result,
)

APIFY_BASE_URL = "https://api.apify.com/v2"
APIFY_RAW_DIR = DATA_DIR / "raw" / "apify"

DEFAULT_ACTOR_IDS = [
    "supreme_coder~youtube-transcript-scraper",
    "hgservices~youtube-transcript-scraper",
    "scrape-creators~best-youtube-transcripts-scraper",
]

# Also accept /-separated names for convenience
ACTOR_ALIASES = {
    "supreme_coder/youtube-transcript-scraper": "supreme_coder~youtube-transcript-scraper",
    "hgservices/youtube-transcript-scraper": "hgservices~youtube-transcript-scraper",
    "scrape-creators/best-youtube-transcripts-scraper": "scrape-creators~best-youtube-transcripts-scraper",
    "seemuapps/youtube-transcript-scraper": "seemuapps~youtube-transcript-scraper",
    "curious_coder/youtube-transcript-scraper": "curious_coder~youtube-transcript-scraper",
    "muhammad_noman_riaz/youtube-video-transcript-super-scraper": "muhammad_noman_riaz~youtube-video-transcript-super-scraper",
    "powerai/youtube-transcript-scraper": "powerai~youtube-transcript-scraper",
    "pintostudio/youtube-transcript-scraper": "pintostudio~youtube-transcript-scraper",
}


def _normalize_actor_id(actor_id: str) -> str:
    """Convert /-separated actor IDs to ~-separated for the Apify API."""
    if actor_id in ACTOR_ALIASES:
        return ACTOR_ALIASES[actor_id]
    if "/" in actor_id and "~" not in actor_id:
        return actor_id.replace("/", "~", 1)
    return actor_id


def _canonical_actor_id(actor_id: str) -> str:
    return _normalize_actor_id(actor_id).replace("~", "/", 1)

APIFY_RUN_STATUS_TERMINAL = frozenset(
    {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}
)

APIFY_VIDEO_ERROR_CATEGORIES = {
    "captions_unavailable": "no_transcript",
    "age_restricted": "unavailable",
    "private": "unavailable",
    "removed": "unavailable",
    "blocked": "blocked",
    "malformed_output": "error",
}


@dataclass(frozen=True)
class ApifyActorSpec:
    actor_id: str
    price_signal: str
    max_urls_per_run: int | None = None


APIFY_ACTOR_SPECS = {
    "seemuapps/youtube-transcript-scraper": ApifyActorSpec(
        actor_id="seemuapps/youtube-transcript-scraper",
        price_signal="$0.10 / 1,000 transcripts",
        max_urls_per_run=10,
    ),
    "curious_coder/youtube-transcript-scraper": ApifyActorSpec(
        actor_id="curious_coder/youtube-transcript-scraper",
        price_signal="~$0.30 / 1,000 transcripts",
    ),
    "muhammad_noman_riaz/youtube-video-transcript-super-scraper": ApifyActorSpec(
        actor_id="muhammad_noman_riaz/youtube-video-transcript-super-scraper",
        price_signal="store pricing varies; transcript actor exposes free trial",
    ),
    "powerai/youtube-transcript-scraper": ApifyActorSpec(
        actor_id="powerai/youtube-transcript-scraper",
        price_signal="store pricing varies",
    ),
    "pintostudio/youtube-transcript-scraper": ApifyActorSpec(
        actor_id="pintostudio/youtube-transcript-scraper",
        price_signal="$10.00 / 1,000 results",
        max_urls_per_run=1,
    ),
}


class ApifyConfigError(ValueError):
    pass


class ApifyRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ApifyCollectionResult:
    run_id: str
    actor_id: str
    attempted_count: int
    available_count: int
    no_transcript_count: int
    error_count: int
    blocked_count: int
    skipped_existing_count: int
    dry_run: bool
    cost_usd: float | None
    run_ledger: list[dict[str, object]]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _apify_headers(api_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def _resolve_apify_token() -> str:
    settings = get_settings()
    token = settings.apify_token
    if not token:
        raise ApifyConfigError(
            "Missing APIFY_TOKEN environment variable. "
            "Set it in .env or export APIFY_TOKEN=<your-token>. "
            "Get your token from https://console.apify.com/account#/integrations."
        )
    return token


def _build_apify_input(actor_id: str, video_urls: list[str]) -> dict[str, Any]:
    canonical_id = _canonical_actor_id(actor_id)
    if canonical_id == "muhammad_noman_riaz/youtube-video-transcript-super-scraper":
        return {
            "startUrls": [{"url": url} for url in video_urls],
            "includeTranscript": True,
            "language": "en",
        }
    if canonical_id == "powerai/youtube-transcript-scraper":
        return {
            "videoUrls": [{"url": url} for url in video_urls],
        }
    if canonical_id == "pintostudio/youtube-transcript-scraper":
        return {
            "videoUrl": video_urls[0] if video_urls else "",
            "language": "en",
        }
    if canonical_id == "curious_coder/youtube-transcript-scraper":
        return {
            "urls": [{"url": url} for url in video_urls],
            "languages": ["en"],
            "outputFormat": "json",
        }
    if canonical_id == "seemuapps/youtube-transcript-scraper":
        return {
            "videoUrls": video_urls,
            "languages": ["en"],
        }
    return {
        "videoUrls": video_urls,
    }


def _start_apify_run(
    actor_id: str,
    video_urls: list[str],
    api_token: str,
    *,
    max_total_charge_usd: float | None = None,
) -> dict[str, Any]:
    normalized_id = _normalize_actor_id(actor_id)
    input_payload = _build_apify_input(actor_id, video_urls)
    if max_total_charge_usd is not None:
        input_payload["maxResultVideos"] = len(video_urls)
    response = requests.post(
        f"{APIFY_BASE_URL}/acts/{normalized_id}/runs",
        headers=_apify_headers(api_token),
        json=input_payload,
        params={"maxTotalChargeUsd": str(max_total_charge_usd)}
        if max_total_charge_usd is not None
        else None,
        timeout=60,
    )
    if response.status_code == 404:
        raise ApifyConfigError(
            f"Actor '{actor_id}' not found. Verify the actor ID is correct."
        )
    if response.status_code == 401:
        raise ApifyConfigError(
            "APIFY_TOKEN is invalid or unauthorized. "
            "Check your token at https://console.apify.com/account#/integrations."
        )
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = {"error": response.text[:500]}
        raise ApifyRequestError(
            f"Apify run start failed (HTTP {response.status_code}): "
            f"{json.dumps(body, ensure_ascii=False)[:1000]}",
            status_code=response.status_code,
        )
    return response.json()


def _wait_for_run(
    run_id: str,
    api_token: str,
    *,
    poll_seconds: int = 5,
    max_wait_seconds: int = 600,
) -> dict[str, Any]:
    elapsed = 0
    while elapsed < max_wait_seconds:
        response = requests.get(
            f"{APIFY_BASE_URL}/actor-runs/{run_id}",
            headers=_apify_headers(api_token),
            timeout=30,
        )
        if response.status_code >= 400:
            raise ApifyRequestError(
                f"Apify run status check failed (HTTP {response.status_code})",
                status_code=response.status_code,
            )
        payload = response.json()
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        status = _clean(data.get("status", ""))
        if status in APIFY_RUN_STATUS_TERMINAL:
            return data
        time.sleep(poll_seconds)
        elapsed += poll_seconds
    raise ApifyRequestError(
        f"Apify run {run_id} did not complete within {max_wait_seconds} seconds."
    )


def _fetch_run_results(run_id: str, api_token: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    response = requests.get(
        f"{APIFY_BASE_URL}/actor-runs/{run_id}/dataset/items",
        headers=_apify_headers(api_token),
        params={"format": "json", "clean": "1"},
        timeout=120,
    )
    if response.status_code >= 400:
        raise ApifyRequestError(
            f"Failed to fetch Apify dataset items (HTTP {response.status_code})",
            status_code=response.status_code,
        )
    raw = response.json()
    if isinstance(raw, list):
        results = raw
    elif isinstance(raw, dict):
        results = raw.get("items") or raw.get("data") or []
    return results


def _extract_video_id(url: str) -> str:
    import re
    match = re.search(
        r"(?:v=|/)([a-zA-Z0-9_-]{11})(?:[&?#]|$)", url
    )
    if match:
        return match.group(1)
    stripped = url.strip("/").split("/")[-1].split("?")[0]
    if len(stripped) == 11:
        return stripped
    return url


def _timestamp_to_seconds(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    parts = text.split(":")
    if not all(part.isdigit() for part in parts):
        return None
    if len(parts) == 2:
        minutes, seconds = parts
        return float(int(minutes) * 60 + int(seconds))
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(int(hours) * 3600 + int(minutes) * 60 + int(seconds))
    return None


def _normalize_apify_segments(
    segments: list[dict[str, Any]],
) -> list[TranscriptSegment]:
    normalized: list[TranscriptSegment] = []
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            continue
        text = _clean(item.get("text") or item.get("subtitle"))
        if not text:
            continue
        start = None
        duration = None
        for key in ("start_seconds", "start", "offset"):
            val = item.get(key)
            if val is not None:
                try:
                    start = float(val)
                except (TypeError, ValueError):
                    pass
                break
        for key in ("duration_seconds", "duration"):
            val = item.get(key)
            if val is not None:
                try:
                    duration = float(val)
                except (TypeError, ValueError):
                    pass
                break
        if start is None and item.get("startMs") is not None:
            try:
                start = float(item["startMs"]) / 1000.0
            except (TypeError, ValueError):
                pass
        if duration is None and item.get("durationMs") is not None:
            try:
                duration = float(item["durationMs"]) / 1000.0
            except (TypeError, ValueError):
                pass
        if duration is None and item.get("endMs") is not None and item.get("startMs") is not None:
            try:
                duration = (float(item["endMs"]) - float(item["startMs"])) / 1000.0
            except (TypeError, ValueError):
                pass
        if start is None:
            start = _timestamp_to_seconds(item.get("timestamp"))
        if duration is None and item.get("dur") is not None:
            try:
                duration = float(item["dur"])
            except (TypeError, ValueError):
                pass
        normalized.append(
            TranscriptSegment(
                video_id="",
                segment_index=index,
                start_seconds=start,
                duration_seconds=duration,
                text=text,
            )
        )
    return normalized


def _segments_from_item(item: dict[str, Any]) -> list[TranscriptSegment]:
    transcript_value = item.get("transcript")
    if isinstance(transcript_value, list):
        return _normalize_apify_segments(transcript_value)
    search_result = item.get("searchResult")
    if isinstance(search_result, list):
        return _normalize_apify_segments(search_result)
    segments_raw = (
        item.get("segments")
        or item.get("transcriptSegments")
        or item.get("timestamps")
        or []
    )
    return _normalize_apify_segments(segments_raw) if isinstance(segments_raw, list) else []


def _transcript_text_from_item(
    item: dict[str, Any],
    segments: list[TranscriptSegment],
) -> str:
    direct_fields = (
        item.get("transcript_only_text"),
        item.get("transcriptText"),
        item.get("fullTranscript"),
        item.get("text"),
        item.get("caption"),
        item.get("subtitles"),
    )
    for value in direct_fields:
        if isinstance(value, str) and value.strip():
            return value.strip()
    transcript_value = item.get("transcript")
    if isinstance(transcript_value, str) and transcript_value.strip():
        return transcript_value.strip()
    return " ".join(segment.text for segment in segments if segment.text).strip()


def _item_error(item: dict[str, Any]) -> str:
    status = _clean(item.get("status")).lower()
    error = item.get("error") or item.get("errorMessage") or item.get("message")
    if error:
        return _clean(error)
    if status and status not in {"success", "available", "ok"}:
        return status
    return ""


def _map_error_type(error_text: str) -> str:
    lowered = error_text.lower()
    for keyword, category in APIFY_VIDEO_ERROR_CATEGORIES.items():
        if keyword in lowered:
            return category
    if "caption" in lowered or "transcript" in lowered or "subtitle" in lowered:
        return "no_transcript"
    if "private" in lowered or "restricted" in lowered or "unavailable" in lowered:
        return "unavailable"
    return "provider_failure"


def _normalize_apify_output(
    raw_results: list[dict[str, Any]],
    video_ids_sent: set[str],
    *,
    actor_id: str,
    retrieved_at: str,
    provider_run_id: str | None = None,
) -> tuple[list[TranscriptFetchResult], list[dict[str, object]]]:
    results: list[TranscriptFetchResult] = []
    failures: list[dict[str, object]] = []
    matched_video_ids: set[str] = set()
    successful_video_ids: set[str] = set()
    canonical_actor_id = _canonical_actor_id(actor_id)

    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = _clean(
            item.get("inputUrl")
            or
            item.get("url")
            or item.get("videoUrl")
            or item.get("video_url")
            or item.get("videoUrlNoShortlink")
        )
        video_id = _extract_video_id(url)
        if not video_id:
            raw_vid = _clean(item.get("videoId") or item.get("videoID") or item.get("id"))
            if raw_vid and len(raw_vid) == 11:
                video_id = raw_vid
        if not video_id and len(video_ids_sent) == 1:
            video_id = next(iter(video_ids_sent))
        if not video_id:
            failures.append(
                {
                    "video_id": "",
                    "status": "error",
                    "error_type": "malformed_output",
                    "error_message": "Could not extract video_id from Apify result item.",
                    "provider_name": actor_id,
                }
            )
            continue

        matched_video_ids.add(video_id)

        error_str = _item_error(item)
        if error_str:
            error_type = _map_error_type(error_str)
            failures.append(
                {
                    "video_id": video_id,
                    "status": "error",
                    "error_type": error_type,
                    "error_message": error_str[:1000],
                    "provider_name": actor_id,
                }
            )
            continue

        segments = _segments_from_item(item)
        transcript_text = _transcript_text_from_item(item, segments)

        if not transcript_text and not segments:
            failures.append(
                {
                    "video_id": video_id,
                    "status": "unavailable",
                    "error_type": "no_transcript",
                    "error_message": "No transcript text or segments in Apify result.",
                    "provider_name": actor_id,
                }
            )
            continue

        if not transcript_text:
            failures.append(
                {
                    "video_id": video_id,
                    "status": "unavailable",
                    "error_type": "no_transcript",
                    "error_message": "Transcript text empty after normalization.",
                    "provider_name": actor_id,
                }
            )
            continue
        if video_id in successful_video_ids:
            failures.append(
                {
                    "video_id": video_id,
                    "status": "error",
                    "error_type": "duplicate_result",
                    "error_message": "Apify returned more than one successful transcript item for the same video.",
                    "provider_name": actor_id,
                }
            )
            continue
        successful_video_ids.add(video_id)

        segments_with_video = [
            TranscriptSegment(
                video_id=video_id,
                segment_index=seg.segment_index,
                start_seconds=seg.start_seconds,
                duration_seconds=seg.duration_seconds,
                text=seg.text,
            )
            for seg in segments
        ]

        full_text_sha256 = hashlib.sha256(
            transcript_text.encode("utf-8")
        ).hexdigest()
        language = _clean(item.get("language") or item.get("lang") or item.get("languageCode"))
        is_asr = bool(
            item.get("isAsr")
            or item.get("isGenerated")
            or item.get("isAutoGenerated")
            or False
        )
        source_confidence = 0.82 if is_asr else 0.92
        character_count = len(transcript_text)
        word_count = len(transcript_text.split())
        raw_segment_payload = (
            item.get("transcript")
            if isinstance(item.get("transcript"), list)
            else item.get("searchResult")
            if isinstance(item.get("searchResult"), list)
            else item.get("segments")
            or item.get("transcriptSegments")
            or item.get("timestamps")
            or []
        )

        result = TranscriptFetchResult(
            video_id=video_id,
            provider_name=f"apify/{canonical_actor_id}",
            provider_version="1",
            status="available",
            transcript_source="external_provider",
            retrieval_method="provider_apify_actor",
            retrieval_status="available",
            retrieved_at=retrieved_at,
            provider_actor_id=canonical_actor_id,
            provider_run_id=provider_run_id,
            provider_notes=f"actor_id={canonical_actor_id};apify_run_id={provider_run_id or ''}",
            is_asr_generated=is_asr,
            source_confidence=source_confidence,
            language=language,
            language_code=language[:2] if language else None,
            is_generated=is_asr,
            full_text=transcript_text,
            full_text_sha256=full_text_sha256,
            raw_json=json.dumps(raw_segment_payload, ensure_ascii=False),
            collected_at=retrieved_at,
            character_count=character_count,
            word_count=word_count,
            collector_notes=f"apify_actor={canonical_actor_id};apify_run_id={provider_run_id or ''}",
            segments=segments_with_video,
        )
        results.append(result)

    for video_id in video_ids_sent - matched_video_ids:
        failures.append(
            {
                "video_id": video_id,
                "status": "missing",
                "error_type": "missing_result",
                "error_message": "Apify run completed but did not return a result for this video.",
                "provider_name": actor_id,
            }
        )

    return results, failures


def _save_raw_response(
    run_id: str, actor_id: str, raw_results: list[dict[str, Any]]
) -> Path:
    # Skip writing raw responses to conserve disk space during bulk collection
    return Path()


def _record_run_start(
    conn,
    run_id: str,
    command_name: str,
    requested_count: int,
) -> int:
    now = _utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO transcript_collection_runs (
          started_at, command_name, input_source, requested_limit,
          attempted_count, available_count, no_transcript_count,
          ip_blocked_count, request_blocked_count, rate_limited_count,
          other_error_count, notes
        )
        VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, ?)
        """,
        (
            now,
            command_name,
            f"apify:{run_id}",
            requested_count,
            f"apify_actor_run_id={run_id}",
        ),
    )
    conn.commit()
    return cursor.lastrowid


def _record_attempt(
    conn,
    db_run_id: int,
    result: TranscriptFetchResult,
    creator: str | None,
    published_at: str | None,
    ticker_signal_count: int | None,
) -> None:
    conn.execute(
        """
        INSERT INTO transcript_collection_attempts (
          run_id, video_id, creator, published_at, ticker_signal_count,
          attempted_at, status, error_type, error_message,
          transcript_source, provider_name, retrieval_method,
          is_asr_generated, language, source_confidence,
          word_count, segment_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            db_run_id,
            result.video_id,
            creator,
            published_at,
            ticker_signal_count,
            _utc_now_iso(),
            result.status,
            result.error_type,
            result.error_message,
            result.transcript_source,
            result.provider_name,
            result.retrieval_method,
            int(result.is_asr_generated) if result.is_asr_generated is not None else None,
            result.language,
            result.source_confidence,
            result.word_count,
            result.segment_count,
        ),
    )


def _record_attempt_failure(
    conn,
    db_run_id: int,
    video_id: str,
    failure: dict[str, object],
    creator: str | None,
    published_at: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO transcript_collection_attempts (
          run_id, video_id, creator, published_at, attempted_at,
          status, error_type, error_message, provider_name
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            db_run_id,
            video_id,
            creator,
            published_at,
            _utc_now_iso(),
            failure.get("status", "error"),
            failure.get("error_type", "unknown"),
            failure.get("error_message", ""),
            failure.get("provider_name", "apify"),
        ),
    )


def collect_apify_transcripts(
    *,
    video_ids: list[str],
    actor_id: str,
    batch_size: int = 25,
    max_total_charge_usd: float | None = None,
    dry_run: bool = False,
) -> ApifyCollectionResult:
    if not video_ids:
        return ApifyCollectionResult(
            run_id="",
            actor_id=actor_id,
            attempted_count=0,
            available_count=0,
            no_transcript_count=0,
            error_count=0,
            blocked_count=0,
            skipped_existing_count=0,
            dry_run=dry_run,
            cost_usd=None,
            run_ledger=[],
        )

    api_token = _resolve_apify_token()
    ensure_data_dirs()
    init_db()

    if dry_run:
        init_db()
        with connect() as conn:
            existing_ids = {
                row["video_id"]
                for row in conn.execute(
                    f"""
                    SELECT video_id FROM youtube_transcripts
                    WHERE video_id IN ({
                        ",".join("?" for _ in video_ids)
                    })
                      AND status = 'available'
                      AND COALESCE(full_text, '') != ''
                    """,
                    video_ids,
                ).fetchall()
            }
        remaining = [v for v in video_ids if v not in existing_ids]
        return ApifyCollectionResult(
            run_id="dry_run",
            actor_id=actor_id,
            attempted_count=len(remaining),
            available_count=0,
            no_transcript_count=0,
            error_count=0,
            blocked_count=0,
            skipped_existing_count=len(video_ids) - len(remaining),
            dry_run=True,
            cost_usd=None,
            run_ledger=[
                {
                    "video_id": v,
                    "status": "would_attempt",
                    "note": "Dry run: no Apify call made.",
                }
                for v in remaining
            ],
        )

    retrieved_at = _utc_now_iso()
    run_ledger: list[dict[str, object]] = []
    all_results: list[TranscriptFetchResult] = []
    all_failures: list[dict[str, object]] = []
    apify_run_ids: list[str] = []
    costs: list[float] = []
    actor_spec = APIFY_ACTOR_SPECS.get(_canonical_actor_id(actor_id))
    effective_batch_size = max(1, batch_size)
    if actor_spec and actor_spec.max_urls_per_run is not None:
        effective_batch_size = min(effective_batch_size, actor_spec.max_urls_per_run)

    for batch_video_ids in _chunks(video_ids, effective_batch_size):
        batch_video_urls = [
            f"https://www.youtube.com/watch?v={video_id}"
            for video_id in batch_video_ids
        ]
        run_response = _start_apify_run(
            actor_id,
            batch_video_urls,
            api_token,
            max_total_charge_usd=max_total_charge_usd,
        )
        apify_run_id = _clean(
            run_response.get("data", {}).get("id") or run_response.get("id")
        )
        apify_run_ids.append(apify_run_id)
        run_ledger.append(
            {
                "phase": "start",
                "actor_id": actor_id,
                "apify_run_id": apify_run_id,
                "video_count": len(batch_video_urls),
                "timestamp": retrieved_at,
            }
        )

        run_status = _wait_for_run(apify_run_id, api_token)
        run_ledger.append(
            {
                "phase": "completed",
                "apify_run_id": apify_run_id,
                "status": run_status.get("status"),
                "finished_at": run_status.get("finishedAt"),
            }
        )
        raw_cost = run_status.get("usageTotalUsd") or run_status.get("stats", {}).get(
            "totalCostUsd"
        )
        if raw_cost:
            try:
                costs.append(float(raw_cost))
            except (TypeError, ValueError):
                pass

        cumulative_cost = sum(costs)
        if max_total_charge_usd is not None and cumulative_cost >= max_total_charge_usd:
            run_ledger.append(
                {
                    "phase": "stopped",
                    "reason": "max_total_charge_usd reached",
                    "cumulative_cost": cumulative_cost,
                }
            )
            break

        raw_results = _fetch_run_results(apify_run_id, api_token)
        if run_status.get("status") != "SUCCEEDED" and not raw_results:
            raise ApifyRequestError(
                f"Apify actor run {apify_run_id} ended with status "
                f"{run_status.get('status')} and returned no dataset items."
            )
        _save_raw_response(apify_run_id, actor_id, raw_results)
        run_ledger.append(
            {
                "phase": "results_fetched",
                "apify_run_id": apify_run_id,
                "result_count": len(raw_results),
            }
        )

        results, failures = _normalize_apify_output(
            raw_results,
            set(batch_video_ids),
            actor_id=actor_id,
            retrieved_at=retrieved_at,
            provider_run_id=apify_run_id,
        )
        all_results.extend(results)
        all_failures.extend(failures)

    with connect() as conn:
        creator_cache: dict[str, tuple[str | None, str | None, int | None]] = {}
        for video_id in video_ids:
            if video_id not in creator_cache:
                row = conn.execute(
                    """
                    SELECT channel_title, published_at
                    FROM raw_youtube_videos
                    WHERE video_id = ?
                    """,
                    (video_id,),
                ).fetchone()
                if row:
                    creator_cache[video_id] = (
                        row["channel_title"],
                        row["published_at"],
                        None,
                    )
                else:
                    creator_cache[video_id] = (None, None, None)

        run_id_note = ",".join(apify_run_ids)
        db_run_id = _record_run_start(
            conn, run_id_note, "collect-apify-transcripts", len(video_ids)
        )

        available_count = 0
        no_transcript_count = 0
        error_count = 0
        blocked_count = 0
        skipped_existing = 0

        existing_ids = {
            row["video_id"]
            for row in conn.execute(
                f"""
                SELECT video_id FROM youtube_transcripts
                WHERE video_id IN ({
                    ",".join("?" for _ in video_ids)
                })
                  AND status = 'available'
                  AND COALESCE(full_text, '') != ''
                """,
                video_ids,
            ).fetchall()
        }

        for result in all_results:
            if result.video_id in existing_ids:
                skipped_existing += 1
                continue
            creator, published_at, ticker_signal = creator_cache.get(
                result.video_id, (None, None, None)
            )
            store_transcript_result(conn, result)
            _record_attempt(
                conn, db_run_id, result, creator, published_at, ticker_signal
            )
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
            available_count += 1
            run_ledger.append(
                {
                    "video_id": result.video_id,
                    "status": "available",
                    "word_count": result.word_count,
                }
            )

        for failure in all_failures:
            video_id = str(failure.get("video_id") or "")
            if video_id in existing_ids:
                skipped_existing += 1
                continue
            creator, published_at, _ = creator_cache.get(
                video_id, (None, None, None)
            )
            _record_attempt_failure(
                conn, db_run_id, video_id, failure, creator, published_at
            )
            error_type = str(failure.get("error_type", "unknown"))
            if error_type in ("no_transcript",):
                no_transcript_count += 1
            elif error_type in ("blocked",):
                blocked_count += 1
            else:
                error_count += 1
            run_ledger.append(
                {
                    "video_id": video_id,
                    "status": failure.get("status"),
                    "error_type": error_type,
                    "error_message": str(failure.get("error_message", ""))[:200],
                }
            )

        conn.execute(
            """
            UPDATE transcript_collection_runs
            SET ended_at = ?,
                attempted_count = ?,
                available_count = ?,
                no_transcript_count = ?,
                other_error_count = ?,
                request_blocked_count = ?
            WHERE run_id = ?
            """,
            (
                _utc_now_iso(),
                len(video_ids) - skipped_existing,
                available_count,
                no_transcript_count,
                error_count,
                blocked_count,
                db_run_id,
            ),
        )
        conn.commit()

    return ApifyCollectionResult(
        run_id=",".join(apify_run_ids),
        actor_id=actor_id,
        attempted_count=len(all_results) + len(all_failures),
        available_count=available_count,
        no_transcript_count=no_transcript_count,
        error_count=error_count,
        blocked_count=blocked_count,
        skipped_existing_count=skipped_existing,
        dry_run=False,
        cost_usd=round(sum(costs), 6) if costs else None,
        run_ledger=run_ledger,
    )
