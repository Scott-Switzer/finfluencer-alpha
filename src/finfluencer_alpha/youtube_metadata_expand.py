from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import SEEDS_DIR, get_settings
from .db import connect, init_db
from .utils import save_raw_json
from .youtube_collect import (
    _insert_youtube_videos,
    _youtube_get,
    get_channel_uploads_playlist,
    get_videos,
)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

CREATOR_RECOMMENDED_CATEGORIES = {
    "stock_picker", "personal_finance",
}
CREATOR_CONTROL_CATEGORIES = {
    "news_commentary",
}


@dataclass(frozen=True)
class CreatorSeed:
    creator_name: str
    channel_id: str | None
    channel_url: str | None
    handle: str | None
    creator_category: str
    priority: int
    notes: str

    @property
    def collection_identifier(self) -> str:
        return self.channel_id or self.handle or self.channel_url or self.creator_name


@dataclass(frozen=True)
class SearchQuery:
    query: str
    category: str
    recommended: bool


@dataclass(frozen=True)
class MetadataExpandResult:
    creators_processed: int
    channels_resolved: int
    videos_collected: int
    dry_run: bool = False
    estimated_quota_units: int = 0
    expected_max_videos: int = 0
    unresolved_creators: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchDiscoverResult:
    queries_processed: int
    videos_collected: int
    dry_run: bool = False
    estimated_quota_units: int = 0


@dataclass(frozen=True)
class TranscriptCollectionPlan:
    total_videos: int
    available_transcripts: int
    failed_transcripts: int
    pending_transcripts: int
    pending_by_category: dict[str, int]
    recommended_batch_size: int
    estimated_batches: dict[int, int]
    recently_blocked: bool
    safe_to_collect: bool
    total_pending_raw_videos: int = 0
    blocked_or_cooldown_transcripts: int = 0


@dataclass(frozen=True)
class ChannelResolution:
    seed: CreatorSeed
    channel_id: str | None
    channel_title: str | None = None
    custom_url: str | None = None
    valid: bool = False
    warning: str | None = None


@dataclass(frozen=True)
class AttributionBackfillResult:
    seeds_processed: int
    channels_resolved: int
    rows_updated: int
    unresolved_creators: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class YoutubeExclusionResult:
    channel_id: str
    rows_excluded: int
    queue_rows_marked: int
    reason: str


def load_creator_seeds(path: Path | None = None) -> list[CreatorSeed]:
    seed_path = path or SEEDS_DIR / "youtube_creator_seeds.csv"
    if not seed_path.exists():
        raise FileNotFoundError(f"Creator seed file not found: {seed_path}")
    seeds: list[CreatorSeed] = []
    with seed_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            seeds.append(
                CreatorSeed(
                    creator_name=(row.get("creator_name") or "").strip(),
                    channel_id=(row.get("channel_id") or "").strip() or None,
                    channel_url=(row.get("channel_url") or "").strip() or None,
                    handle=(row.get("handle") or "").strip() or None,
                    creator_category=(row.get("creator_category") or "unknown").strip(),
                    priority=int(row.get("priority", 0) or 0),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return seeds


def load_search_queries(path: Path | None = None) -> list[SearchQuery]:
    query_path = path or SEEDS_DIR / "youtube_search_queries.csv"
    if not query_path.exists():
        queries: list[SearchQuery] = []
        return queries
    queries: list[SearchQuery] = []
    with query_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            queries.append(
                SearchQuery(
                    query=(row.get("query") or "").strip(),
                    category=(row.get("category") or "stock_pick").strip(),
                    recommended=(row.get("recommended") or "yes").strip().lower() == "yes",
                )
            )
    return queries


def _pages_for_video_cap(max_videos_per_channel: int) -> int:
    return max(1, math.ceil(max_videos_per_channel / 50))


def _seed_source_label(seed_path: Path | None) -> str:
    return (seed_path or (SEEDS_DIR / "youtube_creator_seeds.csv")).name


def _normalized_tokens(value: str | None) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return {token for token in normalized.split() if len(token) > 1}


def _reasonable_title_match(expected: str, actual: str | None) -> bool:
    expected_tokens = _normalized_tokens(expected)
    actual_tokens = _normalized_tokens(actual)
    if not expected_tokens or not actual_tokens:
        return False
    if expected_tokens.issubset(actual_tokens):
        return True
    overlap = len(expected_tokens & actual_tokens) / len(expected_tokens)
    ratio = SequenceMatcher(
        None,
        " ".join(sorted(expected_tokens)),
        " ".join(sorted(actual_tokens)),
    ).ratio()
    return overlap >= 0.75 or ratio >= 0.82


def _channel_id_from_url(channel_url: str | None) -> str | None:
    if not channel_url:
        return None
    parsed = urlparse(channel_url.strip())
    path = parsed.path.strip("/")
    if path.startswith("channel/UC"):
        return path.replace("channel/", "", 1)
    return None


def _handle_from_url(channel_url: str | None) -> str | None:
    if not channel_url:
        return None
    parsed = urlparse(channel_url.strip())
    path = parsed.path.strip("/")
    if path.startswith("@"):
        return path
    return None


def _channel_item_from_id(channel_id: str) -> dict[str, Any] | None:
    payload = _youtube_get(
        "channels",
        {
            "part": "snippet,statistics,contentDetails",
            "id": channel_id,
            "maxResults": 1,
        },
    )
    if payload:
        save_raw_json("youtube", f"validated_channel_{channel_id}", payload)
    items = payload.get("items", []) if payload else []
    return items[0] if items else None


def _channel_item_from_handle(handle: str) -> dict[str, Any] | None:
    payload = _youtube_get(
        "channels",
        {
            "part": "snippet,statistics,contentDetails",
            "forHandle": handle,
            "maxResults": 1,
        },
    )
    if payload:
        save_raw_json("youtube", f"validated_handle_{handle}", payload)
    items = payload.get("items", []) if payload else []
    return items[0] if items else None


def _channel_item_from_search(query: str) -> dict[str, Any] | None:
    payload = _youtube_get(
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": 1,
        },
    )
    if payload:
        save_raw_json("youtube", f"validated_channel_search_{query}", payload)
    items = payload.get("items", []) if payload else []
    channel_id = items[0].get("id", {}).get("channelId") if items else None
    if not channel_id:
        return None
    return _channel_item_from_id(channel_id)


def _validate_channel_item(
    seed: CreatorSeed,
    item: dict[str, Any] | None,
    *,
    explicit_channel_id: str | None = None,
) -> ChannelResolution:
    if not item:
        return ChannelResolution(
            seed=seed,
            channel_id=None,
            valid=False,
            warning=f"{seed.creator_name}: no channel returned for {seed.collection_identifier}",
        )

    channel_id = item.get("id")
    snippet = item.get("snippet", {})
    title = snippet.get("title")
    custom_url = snippet.get("customUrl")

    if explicit_channel_id:
        if channel_id == explicit_channel_id:
            return ChannelResolution(seed, channel_id, title, custom_url, True)
        return ChannelResolution(
            seed=seed,
            channel_id=channel_id,
            channel_title=title,
            custom_url=custom_url,
            valid=False,
            warning=(
                f"{seed.creator_name}: explicit channel_id {explicit_channel_id} "
                f"returned {channel_id or 'none'}"
            ),
        )

    if _reasonable_title_match(seed.creator_name, title):
        return ChannelResolution(seed, channel_id, title, custom_url, True)

    return ChannelResolution(
        seed=seed,
        channel_id=channel_id,
        channel_title=title,
        custom_url=custom_url,
        valid=False,
        warning=(
            f"{seed.creator_name}: suspicious channel resolution for "
            f"{seed.collection_identifier}; returned title={title!r}, "
            f"channel_id={channel_id!r}, custom_url={custom_url!r}"
        ),
    )


def resolve_creator_seed_channel(seed: CreatorSeed) -> ChannelResolution:
    explicit_channel_id = seed.channel_id or _channel_id_from_url(seed.channel_url)
    if explicit_channel_id:
        return _validate_channel_item(
            seed,
            _channel_item_from_id(explicit_channel_id),
            explicit_channel_id=explicit_channel_id,
        )

    handle = seed.handle or _handle_from_url(seed.channel_url)
    if handle:
        return _validate_channel_item(seed, _channel_item_from_handle(handle))

    return _validate_channel_item(seed, _channel_item_from_search(seed.creator_name))


def _estimate_seed_quota_units(seed: CreatorSeed, max_videos_per_channel: int) -> int:
    pages = _pages_for_video_cap(max_videos_per_channel)
    resolution_units = 1 if seed.channel_id or seed.handle or seed.channel_url else 100
    return resolution_units + 1 + pages + pages


def _collect_seed_channel_videos(
    seed: CreatorSeed,
    channel_id: str,
    max_videos_per_channel: int,
    seed_source: str,
) -> int:
    init_db()
    uploads_playlist = get_channel_uploads_playlist(channel_id)
    if not uploads_playlist:
        return 0

    video_ids: list[str] = []
    page_token: str | None = None
    pages = _pages_for_video_cap(max_videos_per_channel)
    for page in range(pages):
        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        payload = _youtube_get("playlistItems", params)
        if not payload:
            break
        save_raw_json("youtube", f"playlist_{channel_id}_page_{page + 1}", payload)
        for item in payload.get("items", []):
            video_id = item.get("contentDetails", {}).get("videoId")
            if video_id and len(video_ids) < max_videos_per_channel:
                video_ids.append(video_id)
        page_token = payload.get("nextPageToken")
        if not page_token or len(video_ids) >= max_videos_per_channel:
            break

    videos = get_videos(video_ids[:max_videos_per_channel])
    with connect() as conn:
        inserted = _insert_youtube_videos(
            conn,
            videos,
            creator_category=seed.creator_category,
            seed_source=seed_source,
            seed_creator_name=seed.creator_name,
            seed_priority=seed.priority,
        )
        conn.commit()
    return inserted


def expand_metadata_from_seeds(
    seed_path: Path | None = None,
    max_videos_per_channel: int = 500,
    published_after: str = "2019-01-01",
    dry_run: bool = False,
    only_channels: list[str] | None = None,
) -> MetadataExpandResult:
    seeds = load_creator_seeds(seed_path)
    if only_channels:
        seeds = [s for s in seeds if s.creator_name in only_channels]

    if dry_run:
        quota_estimate = sum(
            _estimate_seed_quota_units(seed, max_videos_per_channel) for seed in seeds
        )
        return MetadataExpandResult(
            creators_processed=len(seeds),
            channels_resolved=0,
            videos_collected=0,
            dry_run=True,
            estimated_quota_units=quota_estimate,
            expected_max_videos=len(seeds) * max_videos_per_channel,
        )

    init_db()
    total_videos = 0
    channels_resolved = 0
    unresolved: list[str] = []
    warnings: list[str] = []
    seed_source = _seed_source_label(seed_path)

    for seed in seeds:
        resolution = resolve_creator_seed_channel(seed)
        if not resolution.valid or not resolution.channel_id:
            unresolved.append(seed.creator_name)
            if resolution.warning:
                warnings.append(resolution.warning)
            continue
        channels_resolved += 1

        collected = _collect_seed_channel_videos(
            seed,
            resolution.channel_id,
            max_videos_per_channel=max_videos_per_channel,
            seed_source=seed_source,
        )
        total_videos += collected

    return MetadataExpandResult(
        creators_processed=len(seeds),
        channels_resolved=channels_resolved,
        videos_collected=total_videos,
        expected_max_videos=len(seeds) * max_videos_per_channel,
        unresolved_creators=tuple(unresolved),
        warnings=tuple(warnings),
    )


def backfill_youtube_seed_attribution(
    seed_path: Path | None = None,
    refresh_attribution: bool = False,
) -> AttributionBackfillResult:
    seeds = load_creator_seeds(seed_path)
    seed_source = _seed_source_label(seed_path)
    init_db()
    rows_updated = 0
    channels_resolved = 0
    unresolved: list[str] = []
    warnings: list[str] = []

    for seed in seeds:
        resolution = resolve_creator_seed_channel(seed)
        if not resolution.valid or not resolution.channel_id:
            unresolved.append(seed.creator_name)
            if resolution.warning:
                warnings.append(resolution.warning)
            continue
        channels_resolved += 1
        with connect() as conn:
            cursor = conn.execute(
                """
                UPDATE raw_youtube_videos SET
                  creator_category = CASE
                    WHEN ? OR creator_category IS NULL OR TRIM(creator_category) = ''
                    THEN ? ELSE creator_category END,
                  seed_source = CASE
                    WHEN ? OR seed_source IS NULL OR TRIM(seed_source) = ''
                    THEN ? ELSE seed_source END,
                  seed_creator_name = CASE
                    WHEN ? OR seed_creator_name IS NULL OR TRIM(seed_creator_name) = ''
                    THEN ? ELSE seed_creator_name END,
                  seed_priority = CASE
                    WHEN ? OR seed_priority IS NULL THEN ? ELSE seed_priority END
                WHERE channel_id = ?
                  AND (
                    ? OR creator_category IS NULL OR TRIM(creator_category) = ''
                    OR seed_source IS NULL OR TRIM(seed_source) = ''
                    OR seed_creator_name IS NULL OR TRIM(seed_creator_name) = ''
                    OR seed_priority IS NULL
                  )
                """,
                (
                    int(refresh_attribution),
                    seed.creator_category,
                    int(refresh_attribution),
                    seed_source,
                    int(refresh_attribution),
                    seed.creator_name,
                    int(refresh_attribution),
                    seed.priority,
                    resolution.channel_id,
                    int(refresh_attribution),
                ),
            )
            rows_updated += cursor.rowcount
            conn.commit()

    return AttributionBackfillResult(
        seeds_processed=len(seeds),
        channels_resolved=channels_resolved,
        rows_updated=rows_updated,
        unresolved_creators=tuple(unresolved),
        warnings=tuple(warnings),
    )


def exclude_youtube_channel(
    channel_id: str,
    reason: str = "bad_resolution",
) -> YoutubeExclusionResult:
    init_db()
    normalized_reason = reason.strip() or "bad_resolution"
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE raw_youtube_videos SET
              excluded_flag = 1,
              exclusion_reason = ?
            WHERE channel_id = ?
              AND COALESCE(excluded_flag, 0) = 0
            """,
            (normalized_reason, channel_id),
        )
        rows_excluded = cursor.rowcount
        queue_cursor = conn.execute(
            """
            UPDATE transcript_fetch_queue SET
              transcript_status = 'excluded',
              priority_score = 0,
              priority_reason = ?
            WHERE video_id IN (
              SELECT video_id
              FROM raw_youtube_videos
              WHERE channel_id = ?
                AND COALESCE(excluded_flag, 0) = 1
            )
              AND COALESCE(transcript_status, '') NOT IN ('available', 'excluded')
            """,
            (f"excluded:{normalized_reason}", channel_id),
        )
        queue_rows_marked = queue_cursor.rowcount
        conn.commit()

    return YoutubeExclusionResult(
        channel_id=channel_id,
        rows_excluded=rows_excluded,
        queue_rows_marked=queue_rows_marked,
        reason=normalized_reason,
    )


def discover_videos_from_queries(
    query_path: Path | None = None,
    published_after: str = "2019-01-01",
    max_results_per_query: int = 50,
    dry_run: bool = False,
) -> SearchDiscoverResult:
    queries = load_search_queries(query_path)
    if not queries:
        return SearchDiscoverResult(queries_processed=0, videos_collected=0, dry_run=dry_run)

    if dry_run:
        return SearchDiscoverResult(
            queries_processed=len(queries),
            videos_collected=0,
            dry_run=True,
            estimated_quota_units=len(queries) * 100 * 2,
        )

    init_db()
    total_videos = 0

    for sq in queries:
        payload = _youtube_get(
            "search",
            {
                "part": "snippet",
                "q": sq.query,
                "type": "video",
                "maxResults": min(max_results_per_query, 50),
                "publishedAfter": f"{published_after}T00:00:00Z",
                "relevanceLanguage": "en",
            },
        )
        if not payload:
            continue

        save_raw_json("youtube", f"video_search_{sq.query[:30]}", payload)
        video_ids = [
            item.get("id", {}).get("videoId")
            for item in payload.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            continue

        videos = get_videos(video_ids)
        with connect() as conn:
            inserted = _insert_youtube_videos(conn, videos)
            if sq.recommended:
                conn.executemany(
                    """
                    UPDATE raw_youtube_videos SET
                      creator_category = COALESCE(creator_category, ?),
                      seed_source = COALESCE(seed_source, ?)
                    WHERE video_id = ?
                    """,
                    [(sq.category, f"search:{sq.query}", row["id"])
                     for row in (videos or []) if row.get("id")],
                )
            conn.commit()
            total_videos += inserted

    return SearchDiscoverResult(
        queries_processed=len(queries),
        videos_collected=total_videos,
    )


def build_transcript_collection_plan(
    target_limit: int = 100,
    batch_sizes: tuple[int, ...] = (5, 10, 20),
    max_live_fetches: int = 20,
) -> TranscriptCollectionPlan:
    from .youtube_transcripts import (
        RETRY_ELIGIBLE_TRANSCRIPT_STATUSES,
        _pending_cooldown,
        _queue_stats,
    )

    init_db()
    stats = _queue_stats()
    with connect() as conn:
        queue_rows = conn.execute(
            """
            SELECT COALESCE(rv.creator_category, 'unknown') AS category,
                   tfq.transcript_status,
                   tfq.next_eligible_attempt_at
            FROM transcript_fetch_queue tfq
            LEFT JOIN raw_youtube_videos rv ON rv.video_id = tfq.video_id
            WHERE COALESCE(rv.excluded_flag, 0) = 0
            """
        ).fetchall()
        pending_by_category: dict[str, int] = {}
        for row in queue_rows:
            status = row["transcript_status"]
            if _pending_cooldown(row, get_settings().transcript_queue_cooldown_hours):
                continue
            if status is None or status in RETRY_ELIGIBLE_TRANSCRIPT_STATUSES:
                category = row["category"]
                pending_by_category[category] = pending_by_category.get(category, 0) + 1

        recent_block = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM youtube_transcripts
            WHERE status IN ('ip_blocked', 'request_blocked')
              AND retrieved_at > datetime('now', '-24 hours')
            """
        ).fetchone()["n"]

    pending = stats["retry_eligible_pending"]
    recently_blocked = recent_block > 0
    safe_to_collect = pending > 0 and not recently_blocked

    estimated_batches: dict[int, int] = {}
    remaining = pending
    for batch_size in sorted(batch_sizes, reverse=True):
        if remaining <= 0:
            break
        num_batches = (remaining + batch_size - 1) // batch_size
        estimated_batches[batch_size] = min(num_batches, target_limit // batch_size + 1)
        remaining = 0

    recommended_batch = batch_sizes[-1] if safe_to_collect else 0

    return TranscriptCollectionPlan(
        total_videos=stats["total_videos"],
        available_transcripts=stats["available_transcripts"],
        failed_transcripts=stats["failed_transcripts"],
        pending_transcripts=pending,
        pending_by_category=pending_by_category,
        recommended_batch_size=recommended_batch,
        estimated_batches=estimated_batches,
        recently_blocked=recently_blocked,
        safe_to_collect=safe_to_collect,
        total_pending_raw_videos=stats["total_pending_raw_videos"],
        blocked_or_cooldown_transcripts=stats["blocked_or_cooldown"],
    )
