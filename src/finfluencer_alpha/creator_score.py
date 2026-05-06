from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from .db import connect, init_db


@dataclass(frozen=True)
class CreatorScoreInput:
    platform: str
    total_items: int
    ticker_mentions: int
    actionable_mentions: int
    avg_engagement: float
    ticker_diversity: int


def compute_relevance_score(metrics: CreatorScoreInput) -> float:
    total_items = max(metrics.total_items, 0)
    ticker_mentions = max(metrics.ticker_mentions, 0)
    actionable_mentions = max(metrics.actionable_mentions, 0)
    avg_engagement = max(metrics.avg_engagement, 0.0)
    ticker_density = ticker_mentions / total_items if total_items else 0.0
    actionable_rate = actionable_mentions / total_items if total_items else 0.0

    item_component = min(total_items / 50, 1.0) * 15
    density_component = min(ticker_density / 2, 1.0) * 25
    action_component = min(actionable_rate, 1.0) * 25
    engagement_component = min(math.log10(avg_engagement + 1) / 6, 1.0) * 15
    diversity_component = min(metrics.ticker_diversity / 12, 1.0) * 10
    platform_component = 10 if metrics.platform == "x" else 8
    return round(
        item_component
        + density_component
        + action_component
        + engagement_component
        + diversity_component
        + platform_component,
        3,
    )


def _x_creator_metrics(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          p.creator_handle AS creator_handle,
          COUNT(DISTINCT p.post_id) AS total_items,
          COUNT(tm.mention_id) AS ticker_mentions,
          COUNT(DISTINCT rc.candidate_id) AS actionable_mentions,
          AVG(
            COALESCE(p.like_count, 0) + COALESCE(p.repost_count, 0) +
            COALESCE(p.reply_count, 0) + COALESCE(p.quote_count, 0)
          ) AS avg_engagement,
          COUNT(DISTINCT tm.ticker) AS ticker_diversity
        FROM raw_x_posts p
        LEFT JOIN ticker_mentions tm
          ON tm.platform = 'x' AND tm.source_id = p.post_id
        LEFT JOIN recommendation_candidates rc
          ON rc.platform = 'x' AND rc.source_id = p.post_id
        WHERE p.creator_handle IS NOT NULL
        GROUP BY p.creator_handle
        """
    ).fetchall()


def _youtube_creator_metrics(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          v.channel_id AS creator_handle,
          COUNT(DISTINCT v.video_id) AS total_items,
          COUNT(tm.mention_id) AS ticker_mentions,
          COUNT(DISTINCT rc.candidate_id) AS actionable_mentions,
          AVG(
            COALESCE(v.view_count, 0) + COALESCE(v.like_count, 0) +
            COALESCE(v.comment_count, 0)
          ) AS avg_engagement,
          COUNT(DISTINCT tm.ticker) AS ticker_diversity
        FROM raw_youtube_videos v
        LEFT JOIN ticker_mentions tm
          ON tm.platform = 'youtube' AND tm.source_id = v.video_id
        LEFT JOIN recommendation_candidates rc
          ON rc.platform = 'youtube' AND rc.source_id = v.video_id
        WHERE v.channel_id IS NOT NULL
        GROUP BY v.channel_id
        """
    ).fetchall()


def score_creators() -> int:
    init_db()
    rows_written = 0
    with connect() as conn:
        conn.execute("DELETE FROM creator_scores")
        for platform, rows in [("x", _x_creator_metrics(conn)), ("youtube", _youtube_creator_metrics(conn))]:
            for row in rows:
                metrics = CreatorScoreInput(
                    platform=platform,
                    total_items=int(row["total_items"] or 0),
                    ticker_mentions=int(row["ticker_mentions"] or 0),
                    actionable_mentions=int(row["actionable_mentions"] or 0),
                    avg_engagement=float(row["avg_engagement"] or 0.0),
                    ticker_diversity=int(row["ticker_diversity"] or 0),
                )
                score = compute_relevance_score(metrics)
                ticker_density = (
                    metrics.ticker_mentions / metrics.total_items if metrics.total_items else 0.0
                )
                notes = (
                    "Higher scores reflect stock-specific content, actionable recommendations, "
                    "engagement, and ticker diversity. Validate manually before final sample selection."
                )
                conn.execute(
                    """
                    INSERT INTO creator_scores (
                      creator_handle, platform, total_items, ticker_mentions,
                      actionable_mentions, ticker_density, avg_engagement,
                      relevance_score, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["creator_handle"],
                        platform,
                        metrics.total_items,
                        metrics.ticker_mentions,
                        metrics.actionable_mentions,
                        round(ticker_density, 4),
                        round(metrics.avg_engagement, 3),
                        score,
                        notes,
                    ),
                )
                conn.execute(
                    """
                    UPDATE creators
                    SET relevance_score = ?, post_count = CASE WHEN platform = 'x' THEN ? ELSE post_count END,
                        video_count = CASE WHEN platform = 'youtube' THEN ? ELSE video_count END
                    WHERE platform = ? AND handle = ?
                    """,
                    (
                        score,
                        metrics.total_items,
                        metrics.total_items,
                        platform,
                        row["creator_handle"],
                    ),
                )
                rows_written += 1
        conn.commit()
    return rows_written
