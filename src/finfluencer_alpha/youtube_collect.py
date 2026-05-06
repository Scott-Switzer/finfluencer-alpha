from __future__ import annotations

import json
import sqlite3
from typing import Any

import requests

from .config import YOUTUBE_SEARCH_QUERIES, YOUTUBE_SEED_CHANNELS, get_settings
from .db import connect, init_db, upsert_creator
from .utils import chunked, get_logger, request_json, save_raw_json

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

logger = get_logger(__name__)


def _to_int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None


def _youtube_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.youtube_api_key:
        logger.warning("Skipping YouTube request because YOUTUBE_API_KEY is not set.")
        return None
    params = dict(params)
    params["key"] = settings.youtube_api_key
    session = requests.Session()
    return request_json(session, f"{YOUTUBE_API_BASE}/{endpoint}", params=params)


def _insert_youtube_videos(conn: sqlite3.Connection, items: list[dict[str, Any]]) -> int:
    inserted = 0
    for item in items:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        video_id = item.get("id")
        if not video_id:
            continue
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, description,
              view_count, like_count, comment_count,
              current_view_count, current_like_count, current_comment_count,
              url, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
              channel_id = excluded.channel_id,
              channel_title = excluded.channel_title,
              published_at = excluded.published_at,
              title = excluded.title,
              description = excluded.description,
              view_count = excluded.view_count,
              like_count = excluded.like_count,
              comment_count = excluded.comment_count,
              current_view_count = excluded.current_view_count,
              current_like_count = excluded.current_like_count,
              current_comment_count = excluded.current_comment_count,
              url = excluded.url,
              raw_json = excluded.raw_json
            """,
            (
                video_id,
                snippet.get("channelId"),
                snippet.get("channelTitle"),
                snippet.get("publishedAt"),
                snippet.get("title"),
                snippet.get("description"),
                _to_int_or_none(stats.get("viewCount")),
                _to_int_or_none(stats.get("likeCount")),
                _to_int_or_none(stats.get("commentCount")),
                _to_int_or_none(stats.get("viewCount")),
                _to_int_or_none(stats.get("likeCount")),
                _to_int_or_none(stats.get("commentCount")),
                f"https://www.youtube.com/watch?v={video_id}",
                json.dumps(item, sort_keys=True),
            ),
        )
        if snippet.get("channelId"):
            upsert_creator(
                conn,
                {
                    "platform": "youtube",
                    "handle": snippet.get("channelId"),
                    "display_name": snippet.get("channelTitle"),
                    "account_url": f"https://www.youtube.com/channel/{snippet.get('channelId')}",
                    "category": "candidate_finance_market_attention",
                    "source_method": "youtube_video_search",
                    "include_reason": "Appeared in YouTube finance/stock video search; pending filtering.",
                },
            )
        inserted += 1
    return inserted


def youtube_search_channels(query: str, max_results: int = 25) -> list[dict[str, Any]]:
    init_db()
    payload = _youtube_get(
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": min(max_results, 50),
        },
    )
    if not payload:
        return []
    save_raw_json("youtube", f"channel_search_{query}", payload)
    with connect() as conn:
        for item in payload.get("items", []):
            channel_id = item.get("id", {}).get("channelId")
            snippet = item.get("snippet", {})
            if not channel_id:
                continue
            upsert_creator(
                conn,
                {
                    "platform": "youtube",
                    "handle": channel_id,
                    "display_name": snippet.get("channelTitle") or snippet.get("title"),
                    "account_url": f"https://www.youtube.com/channel/{channel_id}",
                    "category": "candidate_finance_market_attention",
                    "source_method": "youtube_channel_search",
                    "include_reason": f"Matched YouTube channel search query: {query}",
                },
            )
        conn.commit()
    return payload.get("items", [])


def youtube_search_videos(query: str, max_results: int = 25) -> list[dict[str, Any]]:
    init_db()
    payload = _youtube_get(
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
        },
    )
    if not payload:
        return []
    save_raw_json("youtube", f"video_search_{query}", payload)

    video_ids = [
        item.get("id", {}).get("videoId")
        for item in payload.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    videos = get_videos(video_ids)
    with connect() as conn:
        _insert_youtube_videos(conn, videos)
        conn.commit()
    return videos


def get_videos(video_ids: list[str]) -> list[dict[str, Any]]:
    if not video_ids:
        return []
    all_items: list[dict[str, Any]] = []
    for batch in chunked(video_ids, 50):
        payload = _youtube_get(
            "videos",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "maxResults": 50,
            },
        )
        if not payload:
            continue
        save_raw_json("youtube", "videos_list", payload)
        all_items.extend(payload.get("items", []))
    return all_items


def get_channel_uploads_playlist(channel_id: str) -> str | None:
    init_db()
    payload = _youtube_get(
        "channels",
        {
            "part": "snippet,statistics,contentDetails",
            "id": channel_id,
            "maxResults": 1,
        },
    )
    if not payload:
        return None
    save_raw_json("youtube", f"channel_{channel_id}", payload)
    items = payload.get("items", [])
    if not items:
        return None
    item = items[0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    uploads = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    with connect() as conn:
        upsert_creator(
            conn,
            {
                "platform": "youtube",
                "handle": channel_id,
                "display_name": snippet.get("title"),
                "account_url": f"https://www.youtube.com/channel/{channel_id}",
                "category": "candidate_finance_market_attention",
                "source_method": "youtube_channels_list",
                "include_reason": "Resolved YouTube seed/search channel and uploads playlist.",
                "follower_count": int(stats.get("subscriberCount", 0))
                if stats.get("subscriberCount") is not None
                else None,
                "video_count": int(stats.get("videoCount", 0))
                if stats.get("videoCount") is not None
                else None,
            },
        )
        conn.commit()
    return uploads


def collect_channel_videos(channel_id: str, max_pages: int = 3) -> int:
    init_db()
    uploads_playlist = get_channel_uploads_playlist(channel_id)
    if not uploads_playlist:
        logger.warning("Could not resolve uploads playlist for YouTube channel %s.", channel_id)
        return 0

    video_ids: list[str] = []
    page_token: str | None = None
    for page in range(max(1, max_pages)):
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
            if video_id:
                video_ids.append(video_id)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break

    videos = get_videos(video_ids)
    with connect() as conn:
        inserted = _insert_youtube_videos(conn, videos)
        conn.commit()
    return inserted


def collect_channel_videos_between(
    channel_id: str,
    start_date: str,
    end_date: str,
    max_pages: int = 2,
) -> int:
    init_db()
    uploads_playlist = get_channel_uploads_playlist(channel_id)
    if not uploads_playlist:
        logger.warning("Could not resolve uploads playlist for YouTube channel %s.", channel_id)
        return 0

    start_cutoff = f"{start_date}T00:00:00Z"
    end_cutoff = f"{end_date}T23:59:59Z"
    video_ids: list[str] = []
    page_token: str | None = None
    reached_older_than_window = False
    for page in range(max(1, max_pages)):
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
        save_raw_json("youtube", f"history_playlist_{channel_id}_page_{page + 1}", payload)
        for item in payload.get("items", []):
            snippet = item.get("snippet", {})
            published_at = snippet.get("publishedAt") or item.get("contentDetails", {}).get(
                "videoPublishedAt"
            )
            if not published_at:
                continue
            if published_at < start_cutoff:
                reached_older_than_window = True
                continue
            if published_at <= end_cutoff:
                video_id = item.get("contentDetails", {}).get("videoId")
                if video_id:
                    video_ids.append(video_id)
        page_token = payload.get("nextPageToken")
        if not page_token or reached_older_than_window:
            break

    videos = get_videos(video_ids)
    with connect() as conn:
        inserted = _insert_youtube_videos(conn, videos)
        conn.commit()
    return inserted


def _resolve_seed_channel(seed: str) -> str | None:
    if seed.startswith("UC"):
        return seed
    if seed.startswith("@"):
        payload = _youtube_get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                "forHandle": seed,
                "maxResults": 1,
            },
        )
        if payload and payload.get("items"):
            channel_id = payload["items"][0].get("id")
            if channel_id:
                save_raw_json("youtube", f"handle_{seed}", payload)
                return channel_id
    items = youtube_search_channels(seed, max_results=1)
    if not items:
        return None
    return items[0].get("id", {}).get("channelId")


def collect_youtube_for_seed_channels(
    seed_channels: list[str] | None = None,
    max_pages: int = 3,
) -> int:
    seed_channels = seed_channels or YOUTUBE_SEED_CHANNELS
    total = 0
    for seed in seed_channels:
        channel_id = _resolve_seed_channel(seed)
        if not channel_id:
            logger.warning("Could not resolve YouTube seed channel: %s", seed)
            continue
        total += collect_channel_videos(channel_id, max_pages=max_pages)
    return total


def collect_youtube_history_for_seed_channels(
    seed_channels: list[str] | None = None,
    start_date: str = "2025-01-01",
    end_date: str = "2026-05-06",
    max_channels: int = 1,
    max_pages: int = 1,
) -> int:
    seed_channels = (seed_channels or YOUTUBE_SEED_CHANNELS)[:max_channels]
    total = 0
    for seed in seed_channels:
        channel_id = _resolve_seed_channel(seed)
        if not channel_id:
            logger.warning("Could not resolve YouTube seed channel: %s", seed)
            continue
        total += collect_channel_videos_between(
            channel_id,
            start_date=start_date,
            end_date=end_date,
            max_pages=max_pages,
        )
    return total


def discover_youtube_from_queries(
    queries: list[str] | None = None,
    max_results: int = 25,
) -> int:
    queries = queries or YOUTUBE_SEARCH_QUERIES
    total = 0
    for query in queries:
        total += len(youtube_search_channels(query, max_results=max_results))
        total += len(youtube_search_videos(query, max_results=max_results))
    return total
