from pathlib import Path

from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.youtube_collect import _insert_youtube_videos


def test_youtube_insert_uses_current_metric_columns_and_allows_missing_comments(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'youtube.db'}"
    init_db(database_url)
    item = {
        "id": "video123",
        "snippet": {
            "channelId": "channel123",
            "channelTitle": "Test Channel",
            "publishedAt": "2025-01-01T00:00:00Z",
            "title": "Buying $NVDA",
            "description": "Test description",
        },
        "statistics": {
            "viewCount": "100",
            "likeCount": "7",
        },
    }
    with connect(database_url) as conn:
        assert _insert_youtube_videos(conn, [item]) == 1
        conn.commit()
        row = conn.execute(
            """
            SELECT current_view_count, current_like_count, current_comment_count
            FROM raw_youtube_videos
            WHERE video_id = 'video123'
            """
        ).fetchone()
    assert row["current_view_count"] == 100
    assert row["current_like_count"] == 7
    assert row["current_comment_count"] is None
