from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.event_validation import (
    EVENT_VALIDATION_SAMPLE_COLUMNS,
    build_event_validation_sample,
    summarize_event_validation,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "event_validation.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _insert_event_fixture(
    database_url: str,
    index: int,
    *,
    creator: str = "Creator A",
    year: int = 2026,
    category: str = "stock_picker",
    ticker: str | None = None,
    title: str = "Buy Nvidia stock now",
    stance: str = "bullish",
    detected_action: str = "bullish_recommendation",
    views: int = 150_000,
) -> None:
    video_id = f"video{index:06d}"
    ticker = ticker or f"T{index:03d}"
    window = f"I am buying {ticker} stock because revenue is improving."
    full_text = f"Intro context before. {window} More context after the recommendation."
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, creator_category, published_at,
              title, description, url, current_view_count, current_like_count,
              current_comment_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1000, 100)
            """,
            (
                video_id,
                f"channel_{creator}",
                creator,
                category,
                f"{year}-01-01T00:00:00Z",
                title,
                f"Discussion mentioning ${ticker}.",
                f"https://www.youtube.com/watch?v={video_id}",
                views,
            ),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (
              video_id, transcript_source, retrieval_method, provider_name,
              status, full_text, segment_count, source_confidence
            )
            VALUES (?, 'external_provider', 'provider_transcript_api',
                    'TranscriptAPI.com', 'available', ?, 1, 0.95)
            """,
            (video_id, full_text),
        )
        cursor = conn.execute(
            """
            INSERT INTO transcript_recommendation_events (
              video_id, transcript_source, provider_name, ticker, company_name,
              stance, detected_action, actionability_score, confidence_score,
              confidence_label, evidence_start_seconds, evidence_end_seconds,
              evidence_window, classifier_version
            )
            VALUES (?, 'external_provider', 'TranscriptAPI.com', ?, ?, ?, ?, 3,
                    0.9, 'high', 10, 20, ?, 'transcript_rules_v2')
            """,
            (
                video_id,
                ticker,
                f"{ticker} Corp",
                stance,
                detected_action,
                window,
            ),
        )
        event_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO transcript_candidate_windows (
              video_id, transcript_source, provider_name, ticker, company_name,
              mention_text, evidence_start_seconds, evidence_end_seconds,
              evidence_window, focused_action_text, stance, detected_action,
              actionability_score, confidence_score, confidence_label,
              accepted_event_flag, transcript_event_id, classifier_version
            )
            VALUES (?, 'external_provider', 'TranscriptAPI.com', ?, ?, ?, 10, 20,
                    ?, ?, ?, ?, 3, 0.9, 'high', 1, ?, 'transcript_rules_v2')
            """,
            (
                video_id,
                ticker,
                f"{ticker} Corp",
                ticker,
                window,
                window,
                stance,
                detected_action,
                event_id,
            ),
        )
        conn.commit()


def _seed_events(database_url: str, count: int = 20) -> None:
    creators = ["Creator A", "Creator B", "Creator C", "Creator D"]
    categories = ["stock_picker", "macro_commentary", "news_attention"]
    years = [2023, 2024, 2025, 2026]
    for index in range(count):
        _insert_event_fixture(
            database_url,
            index,
            creator=creators[index % len(creators)],
            year=years[index % len(years)],
            category=categories[index % len(categories)],
            title="Buy Nvidia stock now" if index % 2 == 0 else "Market recap and portfolio notes",
            stance="bullish" if index % 3 else "bearish",
            detected_action="bullish_recommendation" if index % 3 else "bearish_recommendation",
            views=150_000 if index % 2 == 0 else 5_000,
        )


def test_validation_sample_file_creation(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    _seed_events(database_url, count=12)
    output_path = tmp_path / "validation" / "event_validation_sample.csv"
    readme_path = tmp_path / "validation" / "README.md"

    result = build_event_validation_sample(
        sample_size=8,
        seed=123,
        output_path=output_path,
        readme_path=readme_path,
    )
    df = pd.read_csv(result.sample_path)

    assert result.row_count == 8
    assert output_path.exists()
    assert readme_path.exists()
    assert "is_true_recommendation" in readme_path.read_text(encoding="utf-8")
    assert len(df) == 8


def test_validation_sample_required_columns(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    _seed_events(database_url, count=5)
    result = build_event_validation_sample(
        sample_size=5,
        output_path=tmp_path / "sample.csv",
        readme_path=tmp_path / "README.md",
    )
    df = pd.read_csv(result.sample_path)

    assert list(df.columns) == EVENT_VALIDATION_SAMPLE_COLUMNS
    for column in [
        "event_id",
        "video_id",
        "creator",
        "ticker",
        "transcript_window_text",
        "context_before",
        "context_after",
        "is_true_recommendation",
        "labeler_notes",
    ]:
        assert column in df.columns


def test_validation_sample_deterministic(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    _seed_events(database_url, count=24)

    first = build_event_validation_sample(
        sample_size=10,
        seed=77,
        output_path=tmp_path / "first.csv",
        readme_path=tmp_path / "first.md",
    )
    second = build_event_validation_sample(
        sample_size=10,
        seed=77,
        output_path=tmp_path / "second.csv",
        readme_path=tmp_path / "second.md",
    )

    assert first.sample_path.read_text(encoding="utf-8") == second.sample_path.read_text(
        encoding="utf-8"
    )


def test_validation_sample_has_no_duplicate_event_rows_when_unique_available(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    _seed_events(database_url, count=20)

    result = build_event_validation_sample(
        sample_size=15,
        seed=1,
        output_path=tmp_path / "sample.csv",
        readme_path=tmp_path / "README.md",
    )
    df = pd.read_csv(result.sample_path)

    assert not df.duplicated(subset=["event_id", "video_id", "ticker"]).any()


def _write_labeled_validation_csv(path: Path) -> None:
    rows = [
        {
            "event_id": "1",
            "video_id": "video1",
            "creator": "Creator A",
            "year": "2026",
            "title_keyword_signal": "high_signal",
            "recommendation_type": "buy",
            "is_true_recommendation": "yes",
            "evidence_quality": "strong",
            "conviction": "high",
            "ticker": "AAA",
            "transcript_window_text": "I am buying AAA.",
        },
        {
            "event_id": "2",
            "video_id": "video2",
            "creator": "Creator A",
            "year": "2026",
            "title_keyword_signal": "low_signal",
            "recommendation_type": "casual_mention",
            "is_true_recommendation": "no",
            "evidence_quality": "weak",
            "conviction": "low",
            "ticker": "BBB",
            "transcript_window_text": "BBB was in the news.",
        },
        {
            "event_id": "3",
            "video_id": "video3",
            "creator": "Creator B",
            "year": "2025",
            "title_keyword_signal": "high_signal",
            "recommendation_type": "unclear",
            "is_true_recommendation": "unclear",
            "evidence_quality": "medium",
            "conviction": "unclear",
            "ticker": "CCC",
            "transcript_window_text": "Maybe CCC matters.",
        },
        {
            "event_id": "4",
            "video_id": "video4",
            "creator": "Creator B",
            "year": "2025",
            "title_keyword_signal": "low_signal",
            "recommendation_type": "",
            "is_true_recommendation": "",
            "evidence_quality": "",
            "conviction": "",
            "ticker": "DDD",
            "transcript_window_text": "Unlabeled row.",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = EVENT_VALIDATION_SAMPLE_COLUMNS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def test_summary_metric_calculations(tmp_path: Path) -> None:
    labeled_path = tmp_path / "event_validation_sample_labeled.csv"
    _write_labeled_validation_csv(labeled_path)

    result = summarize_event_validation(
        labeled_path=labeled_path,
        sample_path=tmp_path / "missing_sample.csv",
        markdown_path=tmp_path / "summary.md",
        csv_path=tmp_path / "summary.csv",
    )
    summary = pd.read_csv(result.csv_path)
    overall = summary[(summary["section"] == "overall") & (summary["segment"] == "all")].iloc[0]
    creator_a = summary[
        (summary["section"] == "precision_by_creator") & (summary["segment"] == "Creator A")
    ].iloc[0]

    assert result.sample_size == 4
    assert result.labeled_count == 3
    assert overall["true_recommendation_rate"] == 0.333
    assert overall["false_positive_rate"] == 0.333
    assert overall["unclear_rate"] == 0.333
    assert creator_a["precision"] == 0.5
    assert "casual_mention: 1" in result.markdown_path.read_text(encoding="utf-8")


def test_summary_empty_missing_label_handling(tmp_path: Path) -> None:
    sample_path = tmp_path / "event_validation_sample.csv"
    rows = [
        {
            "event_id": "1",
            "video_id": "video1",
            "creator": "Creator A",
            "year": "2026",
            "title_keyword_signal": "high_signal",
        }
    ]
    with sample_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["event_id", "video_id", "creator", "year", "title_keyword_signal"])
        writer.writeheader()
        writer.writerows(rows)

    result = summarize_event_validation(
        labeled_path=tmp_path / "missing_labeled.csv",
        sample_path=sample_path,
        markdown_path=tmp_path / "summary.md",
        csv_path=tmp_path / "summary.csv",
    )
    summary = pd.read_csv(result.csv_path)
    overall = summary[(summary["section"] == "overall") & (summary["segment"] == "all")].iloc[0]

    assert result.sample_size == 1
    assert result.labeled_count == 0
    assert overall["true_recommendation_rate"] == 0.0
    assert overall["false_positive_rate"] == 0.0
    assert overall["unclear_rate"] == 0.0
