from pathlib import Path

import pandas as pd

from finfluencer_alpha.config import EXPORTS_DIR, get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.transcript_exports import (
    TRANSCRIPT_COVERAGE_BY_CREATOR_COLUMNS,
    TRANSCRIPT_EVENT_COLUMNS,
    export_transcript_events,
)


def _use_temp_db(monkeypatch, tmp_path: Path) -> str:
    database_url = f"sqlite:///{tmp_path / 'exports.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def test_transcript_event_export_has_blank_finbert_fields(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url
            )
            VALUES ('video123', 'channel123', 'Test Channel', '2026-01-01T00:00:00Z',
                    'Buying Nvidia', 'https://www.youtube.com/watch?v=video123')
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_recommendation_events (
              video_id, ticker, company_name, stance, detected_action,
              actionability_score, confidence_score, confidence_label,
              evidence_start_seconds, evidence_end_seconds, evidence_window,
              classifier_version
            )
            VALUES ('video123', 'NVDA', 'Nvidia', 'bullish', 'bullish_recommendation',
                    3, 0.75, 'high', 10, 20, 'I am buying Nvidia stock',
                    'transcript_rules_v1')
            """
        )
        conn.commit()

    paths = export_transcript_events()
    df = pd.read_csv(paths["transcript_recommendation_events"], keep_default_na=False)

    assert list(df.columns) == TRANSCRIPT_EVENT_COLUMNS
    assert df.loc[0, "finbert_label"] == ""
    assert df.loc[0, "finbert_positive_prob"] == ""
    assert df.loc[0, "finbert_negative_prob"] == ""
    assert df.loc[0, "finbert_neutral_prob"] == ""


def test_transcript_coverage_by_creator_export(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    with connect(database_url) as conn:
        conn.executemany(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "available_video",
                    "channel123",
                    "Test Channel",
                    "2026-01-02T00:00:00Z",
                    "Video 1",
                    "https://www.youtube.com/watch?v=available_video",
                ),
                (
                    "disabled_video",
                    "channel123",
                    "Test Channel",
                    "2026-01-01T00:00:00Z",
                    "Video 2",
                    "https://www.youtube.com/watch?v=disabled_video",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO youtube_transcripts (
              video_id, provider_name, provider_version, language_code, status,
              segment_count, full_text_sha256
            )
            VALUES (?, 'youtube_transcript_api', '1.2.4', 'en', ?, ?, ?)
            """,
            [
                ("available_video", "available", 2, "hash"),
                ("disabled_video", "disabled", 0, None),
            ],
        )
        conn.commit()

    paths = export_transcript_events()
    df = pd.read_csv(paths["transcript_coverage_by_creator"])

    assert list(df.columns) == TRANSCRIPT_COVERAGE_BY_CREATOR_COLUMNS
    assert df.loc[0, "channel_title"] == "Test Channel"
    assert df.loc[0, "videos_attempted"] == 2
    assert df.loc[0, "transcripts_available"] == 1
    assert df.loc[0, "disabled"] == 1
    assert df.loc[0, "availability_rate"] == 0.5


def test_transcript_export_paths_are_ignored() -> None:
    assert "data/exports/" in Path(".gitignore").read_text(encoding="utf-8")
    assert EXPORTS_DIR.name == "exports"
