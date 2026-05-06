from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db

CREATOR_COLUMNS = [
    "creator_handle",
    "platform",
    "display_name",
    "account_url",
    "total_items",
    "ticker_mentions",
    "actionable_mentions",
    "ticker_density",
    "avg_engagement",
    "relevance_score",
    "notes",
]

RECOMMENDATION_COLUMNS = [
    "platform",
    "source_id",
    "creator_handle",
    "ticker",
    "event_time",
    "stance",
    "actionability_score",
    "recommendation_type",
    "horizon",
    "disclosure_flag",
    "risk_discussion_flag",
    "valuation_discussion_flag",
    "classifier_confidence",
    "manual_validated",
]

MANUAL_VALIDATION_COLUMNS = [
    "event_id",
    "platform",
    "video_id",
    "post_id",
    "video_url",
    "post_url",
    "channel_title",
    "x_handle",
    "creator_category",
    "published_at",
    "title",
    "post_text",
    "ticker",
    "company_name",
    "detected_action",
    "detected_direction",
    "confidence_score",
    "confidence_label",
    "source_layer",
    "evidence_snippet",
    "transcript_timestamp_start",
    "transcript_timestamp_end",
    "current_view_count",
    "current_like_count",
    "current_comment_count",
    "manual_label",
    "manual_direction",
    "manual_action",
    "manual_confidence",
    "manual_notes",
    "reviewer",
    "reviewed_at",
]


def _write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> Path:
    if df.empty:
        df = pd.DataFrame(columns=columns)
    df.to_csv(path, index=False)
    return path


def export_csvs() -> dict[str, Path]:
    init_db()
    ensure_data_dirs()
    paths = {
        "x_creator_candidates": EXPORTS_DIR / "x_creator_candidates.csv",
        "youtube_creator_candidates": EXPORTS_DIR / "youtube_creator_candidates.csv",
        "recommendation_candidates": EXPORTS_DIR / "recommendation_candidates.csv",
    }
    with connect() as conn:
        creator_query = """
            SELECT
              cs.creator_handle,
              cs.platform,
              c.display_name,
              c.account_url,
              cs.total_items,
              cs.ticker_mentions,
              cs.actionable_mentions,
              cs.ticker_density,
              cs.avg_engagement,
              cs.relevance_score,
              cs.notes
            FROM creator_scores cs
            LEFT JOIN creators c
              ON c.platform = cs.platform AND c.handle = cs.creator_handle
            WHERE cs.platform = ?
            ORDER BY cs.relevance_score DESC, cs.actionable_mentions DESC
        """
        x_df = pd.read_sql_query(creator_query, conn, params=("x",))
        youtube_df = pd.read_sql_query(creator_query, conn, params=("youtube",))
        rec_df = pd.read_sql_query(
            """
            SELECT
              platform, source_id, creator_handle, ticker, event_time, stance,
              actionability_score, recommendation_type, horizon, disclosure_flag,
              risk_discussion_flag, valuation_discussion_flag, classifier_confidence,
              manual_validated
            FROM recommendation_candidates
            ORDER BY event_time DESC, platform, creator_handle
            """,
            conn,
        )

    _write_csv(x_df, paths["x_creator_candidates"], CREATOR_COLUMNS)
    _write_csv(youtube_df, paths["youtube_creator_candidates"], CREATOR_COLUMNS)
    _write_csv(rec_df, paths["recommendation_candidates"], RECOMMENDATION_COLUMNS)
    return paths
