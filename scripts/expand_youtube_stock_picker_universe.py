#!/usr/bin/env python3
"""Expand YouTube stock-picker metadata universe in staged mode."""
from __future__ import annotations

import csv
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "src"))

from finfluencer_alpha.db import connect, init_db  # noqa: E402
from finfluencer_alpha.youtube_collect import (  # noqa: E402
    _insert_youtube_videos,
    _youtube_get,
    get_channel_uploads_playlist,
    get_videos,
)
from finfluencer_alpha.youtube_stock_pick_scoring import (  # noqa: E402
    score_video_stock_pick_likelihood,
)

OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
OUT_CSV = OUT_DIR / "61_youtube_dynamic_metadata_expansion.csv"
OUT_MD = OUT_DIR / "61_youtube_dynamic_metadata_expansion.md"
SEED_CHANNELS = ROOT / "data" / "seeds" / "youtube_seed_channels.csv"

DISCOVERY_QUERIES = [
    "stocks to buy now",
    "best stocks to buy now",
    "top stocks to buy",
    "undervalued stocks to buy",
    "my stock portfolio update",
    "stock picks 2024",
    "stock picks 2023",
    "stock picks 2022",
    "Tesla stock buy now",
    "Nvidia stock buy now",
    "Palantir stock analysis buy",
    "AI stocks to buy",
    "growth stocks to buy",
    "dividend stocks to buy",
]


@dataclass
class ExpansionRow:
    cycle_id: str
    discovery_stage: str
    query_or_seed_source: str
    channel_id: str
    channel_title: str
    video_id: str
    video_title: str
    published_at: str
    duration_seconds: int
    stock_pick_score: float
    ticker_keyword_hit: int
    recommendation_keyword_hit: int
    existing_creator_prior_event_rate: float
    included_in_queue: int
    exclusion_reason: str
    youtube_quota_estimated: int
    youtube_quota_observed_if_available: int


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _duration_to_seconds(iso8601: str) -> int:
    text = _clean(iso8601)
    if not text:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mnt = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mnt * 60 + s


def _resolve_seed_channel_id(row: dict[str, str]) -> str:
    channel_id = _clean(row.get("channel_id"))
    if channel_id.startswith("UC"):
        return channel_id
    channel_url = _clean(row.get("channel_url"))
    if channel_url:
        parsed = urlparse(channel_url)
        path = parsed.path.strip("/")
        if path.startswith("channel/UC"):
            return path.split("/", 1)[1]
    return ""


def _creator_prior_stats() -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT rv.channel_id, rv.channel_title,
                   COUNT(tre.transcript_event_id) AS accepted_events
            FROM raw_youtube_videos rv
            LEFT JOIN transcript_recommendation_events tre
              ON tre.video_id = rv.video_id
            WHERE COALESCE(rv.channel_id,'') != ''
            GROUP BY rv.channel_id, rv.channel_title
            """
        ).fetchall()
        attempt_rows = conn.execute(
            """
            SELECT rv.channel_id, COUNT(*) AS transcript_count
            FROM raw_youtube_videos rv
            JOIN youtube_transcripts yt ON yt.video_id = rv.video_id
            WHERE COALESCE(rv.channel_id,'') != ''
              AND yt.status='available'
            GROUP BY rv.channel_id
            """
        ).fetchall()
    transcript_count = {str(r["channel_id"]): int(r["transcript_count"] or 0) for r in attempt_rows}
    for r in rows:
        cid = str(r["channel_id"])
        events = int(r["accepted_events"] or 0)
        trans = int(transcript_count.get(cid, 0))
        rate = (events / trans) if trans else 0.0
        stats[cid] = {
            "prior_accepted_events": float(events),
            "prior_conversion_rate": rate,
            "creator_type": "stock_picker" if rate >= 0.05 or events >= 3 else "unknown",
            "channel_title": _clean(r["channel_title"]),
        }
    return stats


def _fetch_playlist_video_ids(channel_id: str, max_pages: int) -> tuple[list[str], int]:
    playlist = get_channel_uploads_playlist(channel_id)
    if not playlist:
        return [], 1
    video_ids: list[str] = []
    quota = 1  # channels.list from get_channel_uploads_playlist
    page_token: str | None = None
    for _ in range(max_pages):
        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": playlist,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        payload = _youtube_get("playlistItems", params)
        quota += 1
        if not payload:
            break
        for item in payload.get("items", []):
            vid = _clean(item.get("contentDetails", {}).get("videoId"))
            if vid:
                video_ids.append(vid)
        page_token = _clean(payload.get("nextPageToken")) or None
        if not page_token:
            break
    return video_ids, quota


def _build_rows_for_videos(
    *,
    cycle_id: str,
    stage: str,
    source: str,
    videos: list[dict[str, Any]],
    creator_stats: dict[str, dict[str, float]],
    quota_est: int,
) -> list[ExpansionRow]:
    rows: list[ExpansionRow] = []
    for item in videos:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        channel_id = _clean(snippet.get("channelId"))
        channel_title = _clean(snippet.get("channelTitle"))
        title = _clean(snippet.get("title"))
        desc = _clean(snippet.get("description"))
        published = _clean(snippet.get("publishedAt"))
        video_id = _clean(item.get("id"))
        creator = creator_stats.get(channel_id, {})
        score = score_video_stock_pick_likelihood(
            title,
            desc,
            channel_title,
            _duration_to_seconds(_clean(content.get("duration"))),
            creator,
        )
        ticker_hit = int(any(tok in f"{title.lower()} {desc.lower()}" for tok in ("$", "tsla", "nvda", "aapl", "pltr")))
        rec_hit = int(any(tok in f"{title.lower()} {desc.lower()}" for tok in ("buy", "sell", "stock to buy", "price target", "portfolio")))
        included = int(score >= 35.0 and bool(video_id))
        excl = "" if included else "low_stock_pick_score"
        rows.append(
            ExpansionRow(
                cycle_id=cycle_id,
                discovery_stage=stage,
                query_or_seed_source=source,
                channel_id=channel_id,
                channel_title=channel_title,
                video_id=video_id,
                video_title=title,
                published_at=published,
                duration_seconds=_duration_to_seconds(_clean(content.get("duration"))),
                stock_pick_score=score,
                ticker_keyword_hit=ticker_hit,
                recommendation_keyword_hit=rec_hit,
                existing_creator_prior_event_rate=float(creator.get("prior_conversion_rate", 0.0) or 0.0),
                included_in_queue=included,
                exclusion_reason=excl,
                youtube_quota_estimated=quota_est,
                youtube_quota_observed_if_available=quota_est,
            )
        )
    return rows


def run_expansion() -> dict[str, Any]:
    init_db()
    cycle_id = _clean(os.getenv("YOUTUBE_AUTONOMOUS_CYCLE_ID")) or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    max_new_channels = int(os.getenv("YOUTUBE_AUTONOMOUS_MAX_NEW_CHANNELS_PER_CYCLE", "50") or "50")
    max_new_videos = int(os.getenv("YOUTUBE_AUTONOMOUS_MAX_NEW_VIDEOS_PER_CYCLE", "10000") or "10000")
    search_quota_cap = int(os.getenv("YOUTUBE_AUTONOMOUS_SEARCH_QUOTA_CAP", "2000") or "2000")
    enable_search = str(os.getenv("YOUTUBE_AUTONOMOUS_ENABLE_SEARCH_DISCOVERY", "1")).lower() in {"1", "true", "yes", "on"}
    dry_run = str(os.getenv("RUN_YOUTUBE_AUTONOMOUS_EXPANSION", "0")).lower() not in {"1", "true", "yes", "on"}

    creator_stats = _creator_prior_stats()
    rows: list[ExpansionRow] = []
    new_video_ids: set[str] = set()
    new_channel_ids: set[str] = set()
    seen_video_ids: set[str] = set()
    quota_total = 0

    # Stage A: known-channel backfill
    seed_rows: list[dict[str, str]] = []
    if SEED_CHANNELS.exists():
        with SEED_CHANNELS.open(newline="", encoding="utf-8") as fh:
            seed_rows = list(csv.DictReader(fh))
    for seed in seed_rows[:max_new_channels]:
        channel_id = _resolve_seed_channel_id(seed)
        if not channel_id:
            continue
        if dry_run:
            quota_total += 3
            continue
        vids, quota = _fetch_playlist_video_ids(channel_id, max_pages=3)
        quota_total += quota
        videos = get_videos(vids[:300])
        with connect() as conn:
            _insert_youtube_videos(
                conn,
                videos,
                creator_category=_clean(seed.get("category")) or "unknown",
                seed_source="dynamic_stage_a",
                seed_creator_name=_clean(seed.get("channel_name")),
            )
            conn.commit()
        row_objs = _build_rows_for_videos(
            cycle_id=cycle_id,
            stage="A_known_channel_backfill",
            source=_clean(seed.get("channel_name")) or channel_id,
            videos=videos,
            creator_stats=creator_stats,
            quota_est=quota,
        )
        for r in row_objs:
            if r.video_id in seen_video_ids:
                continue
            seen_video_ids.add(r.video_id)
            rows.append(r)
            if r.included_in_queue:
                new_video_ids.add(r.video_id)
                new_channel_ids.add(r.channel_id)

    # Stage B: high-yield creator expansion
    top_creators = sorted(
        creator_stats.items(),
        key=lambda kv: (kv[1].get("prior_conversion_rate", 0.0), kv[1].get("prior_accepted_events", 0.0)),
        reverse=True,
    )[:max_new_channels]
    for channel_id, st in top_creators:
        if not channel_id:
            continue
        if dry_run:
            quota_total += 3
            continue
        vids, quota = _fetch_playlist_video_ids(channel_id, max_pages=4)
        quota_total += quota
        videos = get_videos(vids[:500])
        with connect() as conn:
            _insert_youtube_videos(
                conn,
                videos,
                creator_category="stock_picker",
                seed_source="dynamic_stage_b",
                seed_creator_name=_clean(str(st.get("channel_title"))),
            )
            conn.commit()
        row_objs = _build_rows_for_videos(
            cycle_id=cycle_id,
            stage="B_high_yield_creator_expansion",
            source=_clean(str(st.get("channel_title"))) or channel_id,
            videos=videos,
            creator_stats=creator_stats,
            quota_est=quota,
        )
        for r in row_objs:
            if r.video_id in seen_video_ids:
                continue
            seen_video_ids.add(r.video_id)
            rows.append(r)
            if r.included_in_queue:
                new_video_ids.add(r.video_id)
                new_channel_ids.add(r.channel_id)

    # Stage C: targeted search discovery
    search_spent = 0
    if enable_search:
        for query in DISCOVERY_QUERIES:
            if search_spent + 100 > search_quota_cap:
                break
            if dry_run:
                search_spent += 100
                quota_total += 100
                continue
            payload = _youtube_get(
                "search",
                {
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": 50,
                    "order": "relevance",
                },
            )
            search_spent += 100
            quota_total += 100
            if not payload:
                continue
            ids = [
                _clean(item.get("id", {}).get("videoId"))
                for item in payload.get("items", [])
                if _clean(item.get("id", {}).get("videoId"))
            ]
            videos = get_videos(ids[:50])
            with connect() as conn:
                _insert_youtube_videos(
                    conn,
                    videos,
                    creator_category="stock_picker",
                    seed_source=f"dynamic_stage_c:{query}",
                    seed_creator_name="search_discovery",
                )
                conn.commit()
            row_objs = _build_rows_for_videos(
                cycle_id=cycle_id,
                stage="C_targeted_search_discovery",
                source=query,
                videos=videos,
                creator_stats=creator_stats,
                quota_est=100,
            )
            for r in row_objs:
                if r.video_id in seen_video_ids:
                    continue
                seen_video_ids.add(r.video_id)
                rows.append(r)
                if r.included_in_queue:
                    new_video_ids.add(r.video_id)
                    new_channel_ids.add(r.channel_id)
            if len(new_video_ids) >= max_new_videos:
                break

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = list(ExpansionRow.__annotations__.keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)

    lines = [
        "# YouTube dynamic metadata expansion",
        "",
        f"Generated (UTC): `{_now()}`",
        f"Cycle ID: `{cycle_id}`",
        f"Dry-run: `{dry_run}`",
        f"Rows emitted: `{len(rows)}`",
        f"New included videos: `{len(new_video_ids)}`",
        f"New discovered creators: `{len(new_channel_ids)}`",
        f"Estimated quota used: `{quota_total}`",
        f"Search quota spent: `{search_spent}` / `{search_quota_cap}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE_CSV={OUT_CSV.relative_to(ROOT)}")
    print(f"WROTE_MD={OUT_MD.relative_to(ROOT)}")
    print(f"NEW_INCLUDED_VIDEOS={len(new_video_ids)}")
    print(f"NEW_CREATORS={len(new_channel_ids)}")
    print(f"QUOTA_ESTIMATE={quota_total}")
    return {
        "cycle_id": cycle_id,
        "new_included_videos": len(new_video_ids),
        "new_creators": len(new_channel_ids),
        "quota_estimate": quota_total,
        "rows_emitted": len(rows),
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    run_expansion()
