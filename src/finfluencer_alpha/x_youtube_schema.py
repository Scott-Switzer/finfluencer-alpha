from __future__ import annotations

import sqlite3
from typing import Any


def apply_x_youtube_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS x_posts (
          post_id TEXT PRIMARY KEY,
          author_handle TEXT,
          author_name TEXT,
          author_id TEXT,
          text TEXT,
          created_at TEXT,
          url TEXT,
          like_count INTEGER,
          repost_count INTEGER,
          reply_count INTEGER,
          quote_count INTEGER,
          view_count INTEGER,
          language TEXT,
          scraped_at TEXT,
          apify_actor TEXT,
          apify_key_label TEXT,
          source_query TEXT,
          source_type TEXT,
          raw_json_path TEXT,
          normalized_text_hash TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_x_posts_url
        ON x_posts(url)
        WHERE url IS NOT NULL AND url != '';

        CREATE UNIQUE INDEX IF NOT EXISTS idx_x_posts_author_created_hash
        ON x_posts(author_handle, created_at, normalized_text_hash)
        WHERE author_handle IS NOT NULL
          AND author_handle != ''
          AND created_at IS NOT NULL
          AND created_at != ''
          AND normalized_text_hash IS NOT NULL
          AND normalized_text_hash != '';

        CREATE INDEX IF NOT EXISTS idx_x_posts_author_date
        ON x_posts(author_handle, created_at);

        CREATE INDEX IF NOT EXISTS idx_x_posts_source
        ON x_posts(source_type, source_query);

        CREATE TABLE IF NOT EXISTS x_post_ticker_mentions (
          post_id TEXT,
          ticker TEXT,
          cashtag TEXT,
          mention_type TEXT,
          confidence REAL,
          PRIMARY KEY(post_id, ticker)
        );

        CREATE INDEX IF NOT EXISTS idx_x_post_ticker_mentions_ticker
        ON x_post_ticker_mentions(ticker);

        CREATE TABLE IF NOT EXISTS x_recommendation_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          post_id TEXT,
          author_handle TEXT,
          ticker TEXT,
          event_datetime TEXT,
          event_date TEXT,
          recommendation_type TEXT,
          direction TEXT,
          confidence REAL,
          source_method TEXT,
          evidence_text TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_x_recommendation_events_unique
        ON x_recommendation_events(post_id, ticker, recommendation_type, direction);

        CREATE INDEX IF NOT EXISTS idx_x_recommendation_events_ticker_date
        ON x_recommendation_events(ticker, event_date);

        CREATE TABLE IF NOT EXISTS apify_collection_runs (
          run_id TEXT PRIMARY KEY,
          platform TEXT,
          actor_id TEXT,
          key_label TEXT,
          started_at TEXT,
          finished_at TEXT,
          status TEXT,
          input_hash TEXT,
          source_type TEXT,
          source_query TEXT,
          requested_items INTEGER,
          imported_items INTEGER,
          duplicates INTEGER,
          cost_usd REAL,
          error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_apify_collection_runs_platform
        ON apify_collection_runs(platform, started_at);

        CREATE TABLE IF NOT EXISTS x_collection_progress (
          source_type TEXT,
          source_value TEXT,
          last_collected_at TEXT,
          earliest_collected_at TEXT,
          posts_imported INTEGER,
          status TEXT,
          PRIMARY KEY(source_type, source_value)
        );

        CREATE TABLE IF NOT EXISTS youtube_metadata_expansion_runs (
          run_id TEXT PRIMARY KEY,
          source_name TEXT,
          source_type TEXT,
          started_at TEXT,
          finished_at TEXT,
          videos_found INTEGER,
          videos_imported INTEGER,
          duplicates INTEGER,
          status TEXT,
          error_message TEXT
        );
        """
    )


def insert_x_post(conn: sqlite3.Connection, post: dict[str, Any]) -> bool:
    before = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO x_posts (
          post_id, author_handle, author_name, author_id, text, created_at, url,
          like_count, repost_count, reply_count, quote_count, view_count, language,
          scraped_at, apify_actor, apify_key_label, source_query, source_type,
          raw_json_path, normalized_text_hash
        ) VALUES (
          :post_id, :author_handle, :author_name, :author_id, :text, :created_at, :url,
          :like_count, :repost_count, :reply_count, :quote_count, :view_count, :language,
          :scraped_at, :apify_actor, :apify_key_label, :source_query, :source_type,
          :raw_json_path, :normalized_text_hash
        )
        """,
        {
            "post_id": post.get("post_id"),
            "author_handle": post.get("author_handle"),
            "author_name": post.get("author_name"),
            "author_id": post.get("author_id"),
            "text": post.get("text"),
            "created_at": post.get("created_at"),
            "url": post.get("url"),
            "like_count": post.get("like_count"),
            "repost_count": post.get("repost_count"),
            "reply_count": post.get("reply_count"),
            "quote_count": post.get("quote_count"),
            "view_count": post.get("view_count"),
            "language": post.get("language"),
            "scraped_at": post.get("scraped_at"),
            "apify_actor": post.get("apify_actor"),
            "apify_key_label": post.get("apify_key_label"),
            "source_query": post.get("source_query"),
            "source_type": post.get("source_type"),
            "raw_json_path": post.get("raw_json_path"),
            "normalized_text_hash": post.get("normalized_text_hash"),
        },
    )
    return conn.total_changes > before


def insert_apify_collection_run(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO apify_collection_runs (
          run_id, platform, actor_id, key_label, started_at, finished_at, status,
          input_hash, source_type, source_query, requested_items, imported_items,
          duplicates, cost_usd, error_message
        ) VALUES (
          :run_id, :platform, :actor_id, :key_label, :started_at, :finished_at, :status,
          :input_hash, :source_type, :source_query, :requested_items, :imported_items,
          :duplicates, :cost_usd, :error_message
        )
        ON CONFLICT(run_id) DO UPDATE SET
          finished_at = excluded.finished_at,
          status = excluded.status,
          imported_items = excluded.imported_items,
          duplicates = excluded.duplicates,
          cost_usd = excluded.cost_usd,
          error_message = excluded.error_message
        """,
        row,
    )
