from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, ensure_data_dirs, get_settings


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
    return conn


def init_db(database_url: str | None = None) -> Path:
    db_path = sqlite_path_from_url(database_url)
    with connect(database_url) as conn:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        conn.executescript(schema)
        _ensure_column(conn, "raw_youtube_videos", "current_view_count", "INTEGER")
        _ensure_column(conn, "raw_youtube_videos", "current_like_count", "INTEGER")
        _ensure_column(conn, "raw_youtube_videos", "current_comment_count", "INTEGER")
        _ensure_column(
            conn,
            "transcript_candidate_windows",
            "accepted_event_flag",
            "INTEGER DEFAULT 0",
        )
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
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


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
