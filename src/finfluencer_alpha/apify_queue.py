from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .db import connect, init_db


@dataclass(frozen=True)
class ApifyQueueSelection:
    video_id: str
    channel_title: str
    published_at: str
    title: str
    year: int
    creator: str
    stratum: str


@dataclass(frozen=True)
class ApifyQueueResult:
    selected: list[ApifyQueueSelection]
    total_videos_in_range: int
    already_available: int
    excluded_permanent: int
    selected_count: int
    by_creator: dict[str, int]
    by_year: dict[str, int]


def select_apify_transcript_queue(
    *,
    start_date: str = "2020-01-01",
    end_date: str = "2026-05-12",
    max_videos: int = 50,
    creator: str | None = None,
    year: int | None = None,
    retry_permanent: bool = False,
    dry_run: bool = False,
    segments: list[str] | None = None,
    exclude_segments: list[str] | None = None,
    title_keywords: list[str] | None = None,
) -> ApifyQueueResult:
    init_db()
    with connect() as conn:
        where_clauses = [
            "COALESCE(rv.excluded_flag, 0) = 0",
            "rv.seed_source IS NOT NULL",
            "rv.seed_source != ''",
            "rv.published_at >= ?",
            "rv.published_at <= ?",
        ]
        params: list[object] = [start_date, end_date]

        if creator:
            where_clauses.append("rv.channel_title = ?")
            params.append(creator)

        if year is not None:
            where_clauses.append(
                "CAST(substr(rv.published_at, 1, 4) AS INTEGER) = ?"
            )
            params.append(year)

        if segments:
            placeholders = ", ".join("?" for _ in segments)
            where_clauses.append(f"rv.creator_category IN ({placeholders})")
            params.extend(segments)

        if exclude_segments:
            placeholders = ", ".join("?" for _ in exclude_segments)
            where_clauses.append(
                f"(rv.creator_category IS NULL OR rv.creator_category NOT IN ({placeholders}))"
            )
            params.extend(exclude_segments)

        if title_keywords:
            or_clauses = []
            for kw in title_keywords:
                or_clauses.append("LOWER(rv.title) LIKE ?")
                params.append(f"%{kw.lower()}%")
            where_clauses.append(f"({' OR '.join(or_clauses)})")

        where_sql = " AND ".join(where_clauses)

        total_in_range = conn.execute(
            f"SELECT COUNT(*) AS n FROM raw_youtube_videos rv WHERE {where_sql}",
            params,
        ).fetchone()["n"]

        already_available = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM raw_youtube_videos rv
            JOIN youtube_transcripts yt ON yt.video_id = rv.video_id
            WHERE {where_sql}
              AND yt.status = 'available'
              AND COALESCE(yt.full_text, '') != ''
            """,
            params,
        ).fetchone()["n"]

        if not retry_permanent:
            permanent_unavailable = conn.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM raw_youtube_videos rv
                JOIN youtube_transcripts yt ON yt.video_id = rv.video_id
                WHERE {where_sql}
                  AND yt.status IN ('disabled', 'unavailable')
                  AND NOT (
                    yt.status = 'available'
                    AND COALESCE(yt.full_text, '') != ''
                  )
                """,
                params,
            ).fetchone()["n"]
        else:
            permanent_unavailable = 0

        eligible_sql = f"""
            SELECT rv.video_id, rv.channel_title, rv.published_at, rv.title
            FROM raw_youtube_videos rv
            WHERE {where_sql}
              AND rv.video_id NOT IN (
                  SELECT yt.video_id FROM youtube_transcripts yt
                  WHERE yt.status = 'available'
                    AND COALESCE(yt.full_text, '') != ''
              )
        """
        if not retry_permanent:
            eligible_sql += """
              AND rv.video_id NOT IN (
                  SELECT yt.video_id FROM youtube_transcripts yt
                  WHERE yt.status IN ('disabled', 'unavailable')
              )
            """
        eligible_sql += " ORDER BY rv.channel_title, rv.published_at DESC"

        eligible_rows = conn.execute(eligible_sql, params).fetchall()

    by_creator: dict[str, list[Any]] = defaultdict(list)
    for row in eligible_rows:
        creator_name = row["channel_title"] or "unknown"
        by_creator[creator_name].append(row)

    selected: list[ApifyQueueSelection] = []
    creator_counts: dict[str, int] = defaultdict(int)
    year_counts: dict[str, int] = defaultdict(int)
    seen_ids: set[str] = set()

    # Track per-creator pick index for round-robin stratification
    creator_indices: dict[str, int] = {}
    for c in sorted(by_creator.keys()):
        creator_indices[c] = 0

    creator_list = sorted(by_creator.keys())

    # Round-robin: pick one from each creator, advancing index
    slot = 0
    while len(selected) < max_videos:
        picked_this_round = False
        for c in creator_list:
            queue = by_creator[c]
            idx = creator_indices[c]
            while idx < len(queue):
                row = queue[idx]
                idx += 1
                if row["video_id"] not in seen_ids:
                    seen_ids.add(row["video_id"])
                    pub_at = row["published_at"] or ""
                    pub_year = int(pub_at[:4]) if len(pub_at) >= 4 and pub_at[:4].isdigit() else 0
                    selected.append(
                        ApifyQueueSelection(
                            video_id=row["video_id"],
                            channel_title=row["channel_title"] or "unknown",
                            published_at=pub_at,
                            title=row["title"] or "",
                            year=pub_year,
                            creator=row["channel_title"] or "unknown",
                            stratum=f"{row['channel_title'] or 'unknown'}_{pub_year}",
                        )
                    )
                    creator_counts[row["channel_title"] or "unknown"] += 1
                    year_counts[str(pub_year)] += 1
                    picked_this_round = True
                    break
            creator_indices[c] = idx
            if len(selected) >= max_videos:
                break
        if not picked_this_round:
            break
        slot += 1

    return ApifyQueueResult(
        selected=selected,
        total_videos_in_range=total_in_range,
        already_available=already_available,
        excluded_permanent=permanent_unavailable,
        selected_count=len(selected),
        by_creator=dict(creator_counts),
        by_year=dict(year_counts),
    )
