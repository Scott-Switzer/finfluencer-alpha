from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, ensure_data_dirs, get_settings
from .x_youtube_schema import apply_x_youtube_schema


def sqlite_path_from_url(database_url: str | None = None) -> Path:
    url = database_url or get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// DATABASE_URL values are supported for the MVP.")
    raw_path = url.replace("sqlite:///", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def connect(database_url: str | None = None) -> sqlite3.Connection:
    ensure_data_dirs()
    db_path = sqlite_path_from_url(database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db(database_url: str | None = None) -> Path:
    db_path = sqlite_path_from_url(database_url)
    with connect(database_url) as conn:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        conn.executescript(schema)
        apply_x_youtube_schema(conn)
        _ensure_column(conn, "raw_youtube_videos", "current_view_count", "INTEGER")
        _ensure_column(conn, "raw_youtube_videos", "current_like_count", "INTEGER")
        _ensure_column(conn, "raw_youtube_videos", "current_comment_count", "INTEGER")
        _ensure_column(
            conn,
            "transcript_candidate_windows",
            "accepted_event_flag",
            "INTEGER DEFAULT 0",
        )
        _ensure_column(conn, "raw_youtube_videos", "creator_category", "TEXT")
        _ensure_column(conn, "raw_youtube_videos", "market_regime", "TEXT")
        _ensure_column(conn, "raw_youtube_videos", "seed_source", "TEXT")
        _ensure_column(conn, "raw_youtube_videos", "seed_creator_name", "TEXT")
        _ensure_column(conn, "raw_youtube_videos", "seed_priority", "INTEGER")
        _ensure_column(conn, "raw_youtube_videos", "excluded_flag", "INTEGER DEFAULT 0")
        _ensure_column(conn, "raw_youtube_videos", "exclusion_reason", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "transcript_source", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "retrieval_method", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "retrieval_status", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "provider_actor_id", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "provider_run_id", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "provider_notes", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "is_asr_generated", "INTEGER")
        _ensure_column(conn, "youtube_transcripts", "source_confidence", "REAL")
        _ensure_column(conn, "youtube_transcripts", "collected_at", "TEXT")
        _ensure_column(conn, "youtube_transcripts", "character_count", "INTEGER")
        _ensure_column(conn, "youtube_transcripts", "word_count", "INTEGER")
        _ensure_column(conn, "youtube_transcripts", "collector_notes", "TEXT")
        _ensure_column(conn, "transcript_candidate_windows", "transcript_source", "TEXT")
        _ensure_column(conn, "transcript_candidate_windows", "provider_name", "TEXT")
        _ensure_column(conn, "transcript_candidate_windows", "transcript_collected_at", "TEXT")
        _ensure_column(conn, "transcript_recommendation_events", "transcript_source", "TEXT")
        _ensure_column(conn, "transcript_recommendation_events", "provider_name", "TEXT")
        _ensure_column(conn, "transcript_recommendation_events", "transcript_collected_at", "TEXT")
        _backfill_transcript_provenance(conn)
        conn.commit()
    return db_path


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    column_type: str,
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def _backfill_transcript_provenance(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE youtube_transcripts
        SET transcript_source = CASE
              WHEN provider_name = 'youtube_transcript_api' THEN 'youtube'
              ELSE provider_name
            END
        WHERE transcript_source IS NULL
          AND provider_name IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE youtube_transcripts
        SET retrieval_method = provider_name
        WHERE retrieval_method IS NULL
          AND provider_name IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE youtube_transcripts
        SET retrieval_status = status
        WHERE retrieval_status IS NULL
          AND status IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE youtube_transcripts
        SET is_asr_generated = is_generated
        WHERE is_asr_generated IS NULL
          AND is_generated IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE youtube_transcripts
        SET source_confidence = CASE
              WHEN COALESCE(is_asr_generated, is_generated, 0) = 1 THEN 0.85
              ELSE 0.95
            END
        WHERE source_confidence IS NULL
          AND status = 'available'
        """
    )


def upsert_creator(conn: sqlite3.Connection, creator: dict[str, Any]) -> None:
    fields = [
        "platform",
        "handle",
        "display_name",
        "account_url",
        "category",
        "source_method",
        "include_reason",
        "follower_count",
        "video_count",
        "post_count",
        "relevance_score",
    ]
    values = {field: creator.get(field) for field in fields}
    conn.execute(
        f"""
        INSERT INTO creators ({", ".join(fields)})
        VALUES ({", ".join(":" + field for field in fields)})
        ON CONFLICT(platform, handle) DO UPDATE SET
          display_name = COALESCE(excluded.display_name, creators.display_name),
          account_url = COALESCE(excluded.account_url, creators.account_url),
          category = COALESCE(excluded.category, creators.category),
          source_method = COALESCE(excluded.source_method, creators.source_method),
          include_reason = COALESCE(excluded.include_reason, creators.include_reason),
          follower_count = COALESCE(excluded.follower_count, creators.follower_count),
          video_count = COALESCE(excluded.video_count, creators.video_count),
          post_count = COALESCE(excluded.post_count, creators.post_count),
          relevance_score = COALESCE(excluded.relevance_score, creators.relevance_score)
        """,
        values,
    )


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    allowed = {
        "creators",
        "raw_x_posts",
        "raw_youtube_videos",
        "ticker_mentions",
        "recommendation_candidates",
        "youtube_transcripts",
        "youtube_transcript_segments",
        "transcript_candidate_windows",
        "transcript_recommendation_events",
        "creator_scores",
    }
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])
