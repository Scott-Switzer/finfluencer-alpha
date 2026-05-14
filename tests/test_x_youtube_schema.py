import sqlite3

from finfluencer_alpha.x_youtube_schema import (
    apply_x_youtube_schema,
    insert_apify_collection_run,
    insert_x_post,
)


def test_schema_can_be_applied_twice_safely() -> None:
    conn = sqlite3.connect(":memory:")
    apply_x_youtube_schema(conn)
    apply_x_youtube_schema(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'x_%'"
        )
    }
    assert {"x_posts", "x_post_ticker_mentions", "x_recommendation_events"}.issubset(tables)


def test_x_posts_dedupes_by_post_id() -> None:
    conn = sqlite3.connect(":memory:")
    apply_x_youtube_schema(conn)
    post = {
        "post_id": "1",
        "author_handle": "tester",
        "text": "Buying $TSLA",
        "created_at": "2026-01-01T00:00:00Z",
        "normalized_text_hash": "hash1",
    }

    assert insert_x_post(conn, post)
    assert not insert_x_post(conn, post)
    assert conn.execute("SELECT COUNT(*) FROM x_posts").fetchone()[0] == 1


def test_x_post_ticker_mentions_primary_key_prevents_duplicates() -> None:
    conn = sqlite3.connect(":memory:")
    apply_x_youtube_schema(conn)
    conn.execute(
        """
        INSERT INTO x_post_ticker_mentions (post_id, ticker, cashtag, mention_type, confidence)
        VALUES ('1', 'TSLA', '$TSLA', 'cashtag', 0.95)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO x_post_ticker_mentions
          (post_id, ticker, cashtag, mention_type, confidence)
        VALUES ('1', 'TSLA', '$TSLA', 'cashtag', 0.95)
        """
    )

    assert conn.execute("SELECT COUNT(*) FROM x_post_ticker_mentions").fetchone()[0] == 1


def test_apify_collection_ledger_inserts_work() -> None:
    conn = sqlite3.connect(":memory:")
    apply_x_youtube_schema(conn)
    insert_apify_collection_run(
        conn,
        {
            "run_id": "run1",
            "platform": "x",
            "actor_id": "actor/test",
            "key_label": "label",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "status": "SUCCEEDED",
            "input_hash": "abc",
            "source_type": "profile",
            "source_query": "test",
            "requested_items": 10,
            "imported_items": 5,
            "duplicates": 0,
            "cost_usd": 0.01,
            "error_message": "",
        },
    )
    assert conn.execute("SELECT COUNT(*) FROM apify_collection_runs").fetchone()[0] == 1
