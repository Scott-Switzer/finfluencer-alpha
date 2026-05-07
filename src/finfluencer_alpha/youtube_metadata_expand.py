from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import SEEDS_DIR
from .db import connect, init_db
from .utils import save_raw_json
from .youtube_collect import (
    _insert_youtube_videos,
    _resolve_seed_channel,
    _youtube_get,
    collect_channel_videos,
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
        quota_estimate = 0
        for _seed in seeds:
            quota_estimate += 4
            pages_estimate = min(10, max(1, max_videos_per_channel // 50) + 1)
            quota_estimate += pages_estimate * (
                3 + 1
            )
        return MetadataExpandResult(
            creators_processed=len(seeds),
            channels_resolved=0,
            videos_collected=0,
            dry_run=True,
            estimated_quota_units=quota_estimate,
        )

    init_db()
    total_videos = 0
    channels_resolved = 0

    for seed in seeds:
        identifier = seed.collection_identifier
        channel_id = _resolve_seed_channel(identifier)
        if not channel_id:
            continue
        channels_resolved += 1

        with connect() as conn:
            conn.execute(
                """
                UPDATE raw_youtube_videos SET
                  creator_category = ?, seed_source = ?
                WHERE channel_id = ?
                """,
                (seed.creator_category, seed.creator_name, channel_id),
            )
            conn.commit()

        pages = max(1, min(10, (max_videos_per_channel // 50) + 1))
        collected = collect_channel_videos(channel_id, max_pages=pages)
        total_videos += collected

    return MetadataExpandResult(
        creators_processed=len(seeds),
        channels_resolved=channels_resolved,
        videos_collected=total_videos,
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
    init_db()
    with connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM raw_youtube_videos"
        ).fetchone()["n"]

        available = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcripts WHERE status = 'available'"
        ).fetchone()["n"]

        failed = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcripts WHERE status != 'available'"
        ).fetchone()["n"]

        pending = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM transcript_fetch_queue
            WHERE transcript_status IS NULL
               OR transcript_status IN ('error', 'rate_limited', 'no_language')
            """
        ).fetchone()["n"]

        category_rows = conn.execute(
            """
            SELECT COALESCE(rv.creator_category, 'unknown') AS category,
                   COUNT(*) AS n
            FROM transcript_fetch_queue tfq
            LEFT JOIN raw_youtube_videos rv ON rv.video_id = tfq.video_id
            WHERE tfq.transcript_status IS NULL
               OR tfq.transcript_status IN ('error', 'rate_limited', 'no_language')
            GROUP BY category
            ORDER BY n DESC
            """
        ).fetchall()
        pending_by_category = {row["category"]: row["n"] for row in category_rows}

        recent_block = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM youtube_transcripts
            WHERE status IN ('ip_blocked', 'request_blocked')
              AND retrieved_at > datetime('now', '-24 hours')
            """
        ).fetchone()["n"]

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
        total_videos=total,
        available_transcripts=available,
        failed_transcripts=failed,
        pending_transcripts=pending,
        pending_by_category=pending_by_category,
        recommended_batch_size=recommended_batch,
        estimated_batches=estimated_batches,
        recently_blocked=recently_blocked,
        safe_to_collect=safe_to_collect,
    )
