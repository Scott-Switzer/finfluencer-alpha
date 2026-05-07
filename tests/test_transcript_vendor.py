from pathlib import Path

import pandas as pd
import pytest

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.transcript_classify import build_transcript_recommendation_events
from finfluencer_alpha.transcript_exports import export_transcript_events
from finfluencer_alpha.transcript_vendor import (
    build_transcript_coverage_bias_report,
    export_transcript_vendor_batch,
    import_transcripts_csv,
)
from finfluencer_alpha.youtube_transcripts import (
    TranscriptFetchResult,
    TranscriptSegment,
    store_transcript_result,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "vendor.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _insert_video(
    database_url: str,
    video_id: str,
    creator: str = "Creator A",
    title: str = "3 Stocks to Buy Now",
    excluded: bool = False,
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, creator_category, published_at,
              title, description, url, current_view_count, current_like_count,
              current_comment_count, excluded_flag, exclusion_reason
            )
            VALUES (?, ?, ?, 'stock_picker', '2026-01-01T00:00:00Z',
                    ?, 'I am buying Nvidia stock and adding AMD.',
                    ?, 10000, 500, 50, ?, ?)
            """,
            (
                video_id,
                f"channel_{creator}",
                creator,
                title,
                f"https://www.youtube.com/watch?v={video_id}",
                int(excluded),
                "bad_resolution" if excluded else None,
            ),
        )
        conn.commit()


def _write_import_csv(path: Path, video_id: str, text: str = "I am buying Nvidia stock") -> None:
    path.write_text(
        "video_id,transcript_text,transcript_source,provider_name,"
        "retrieval_method,is_asr_generated,retrieved_at,notes\n"
        f"{video_id},{text},external_provider,Transcript Vendor,"
        "provider_csv,false,2026-05-07T00:00:00Z,delivered batch 1\n",
        encoding="utf-8",
    )


def test_vendor_batch_export_excludes_bad_resolution_rows(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "bad_resolution.db")
    _insert_video(database_url, "good_video")
    _insert_video(database_url, "bad_video", excluded=True)

    result = export_transcript_vendor_batch(100, tmp_path / "batch.csv")
    df = pd.read_csv(result.output_path)

    assert list(df["video_id"]) == ["good_video"]


def test_vendor_batch_export_excludes_already_covered_videos(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "covered.db")
    _insert_video(database_url, "covered_video")
    _insert_video(database_url, "pending_video")
    with connect(database_url) as conn:
        store_transcript_result(
            conn,
            TranscriptFetchResult(
                video_id="covered_video",
                provider_name="youtube_transcript_api",
                provider_version="1.2.4",
                status="available",
                transcript_source="youtube",
                retrieval_method="youtube_transcript_api",
                full_text="covered",
                full_text_sha256="hash",
                segments=[TranscriptSegment("covered_video", 0, 0.0, None, "covered")],
            ),
        )
        conn.commit()

    result = export_transcript_vendor_batch(100, tmp_path / "batch.csv")
    df = pd.read_csv(result.output_path)

    assert list(df["video_id"]) == ["pending_video"]


def test_vendor_batch_export_diversifies_creators(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "diverse.db")
    for index in range(6):
        _insert_video(database_url, f"creator_a_{index}", "Creator A")
    for index in range(2):
        _insert_video(database_url, f"creator_b_{index}", "Creator B", "Weekly Market Update")

    result = export_transcript_vendor_batch(4, tmp_path / "batch.csv")
    df = pd.read_csv(result.output_path)

    assert set(df["creator"]) == {"Creator A", "Creator B"}
    assert df["creator"].value_counts().max() <= 2


def test_import_rejects_unknown_video_id(monkeypatch, tmp_path: Path) -> None:
    _use_temp_db(monkeypatch, tmp_path, "unknown.db")
    csv_path = tmp_path / "transcripts.csv"
    _write_import_csv(csv_path, "missing_video")

    with pytest.raises(ValueError, match="unknown video_id"):
        import_transcripts_csv(csv_path, source="external_provider")


def test_import_rejects_empty_transcript_text(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "empty.db")
    _insert_video(database_url, "video123")
    csv_path = tmp_path / "transcripts.csv"
    _write_import_csv(csv_path, "video123", "")

    with pytest.raises(ValueError, match="empty transcript_text"):
        import_transcripts_csv(csv_path, source="external_provider")


def test_import_preserves_transcript_source(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "preserve.db")
    _insert_video(database_url, "video123")
    csv_path = tmp_path / "transcripts.csv"
    _write_import_csv(csv_path, "video123")

    result = import_transcripts_csv(csv_path, source="external_provider")

    with connect(database_url) as conn:
        row = conn.execute(
            """
            SELECT transcript_source, provider_name, retrieval_method, status
            FROM youtube_transcripts
            WHERE video_id = 'video123'
            """
        ).fetchone()
    assert result.imported_count == 1
    assert row["transcript_source"] == "external_provider"
    assert row["provider_name"] == "Transcript Vendor"
    assert row["retrieval_method"] == "provider_csv"
    assert row["status"] == "available"


def test_import_does_not_overwrite_by_default(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "overwrite.db")
    _insert_video(database_url, "video123")
    with connect(database_url) as conn:
        store_transcript_result(
            conn,
            TranscriptFetchResult(
                video_id="video123",
                provider_name="youtube_transcript_api",
                provider_version="1.2.4",
                status="available",
                transcript_source="youtube",
                retrieval_method="youtube_transcript_api",
                full_text="existing transcript",
                full_text_sha256="hash",
                segments=[TranscriptSegment("video123", 0, 0.0, None, "existing transcript")],
            ),
        )
        conn.commit()
    csv_path = tmp_path / "transcripts.csv"
    _write_import_csv(csv_path, "video123")

    with pytest.raises(ValueError, match="already exists"):
        import_transcripts_csv(csv_path, source="external_provider")


def test_source_labels_flow_into_event_exports(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "source_export.db")
    _insert_video(database_url, "video123")
    csv_path = tmp_path / "transcripts.csv"
    _write_import_csv(csv_path, "video123")
    import_transcripts_csv(csv_path, source="external_provider")

    build_transcript_recommendation_events(refresh_existing=True)
    paths = export_transcript_events()
    events = pd.read_csv(paths["transcript_recommendation_events"])
    windows = pd.read_csv(paths["transcript_candidate_windows"])

    assert events.loc[0, "transcript_source"] == "external_provider"
    assert events.loc[0, "provider_name"] == "Transcript Vendor"
    assert windows.loc[0, "transcript_source"] == "external_provider"
    assert windows.loc[0, "provider_name"] == "Transcript Vendor"


def test_coverage_bias_report_runs(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "coverage.db")
    _insert_video(database_url, "covered_video")
    _insert_video(database_url, "uncovered_video", "Creator B")
    with connect(database_url) as conn:
        store_transcript_result(
            conn,
            TranscriptFetchResult(
                video_id="covered_video",
                provider_name="youtube_transcript_api",
                provider_version="1.2.4",
                status="available",
                transcript_source="youtube",
                retrieval_method="youtube_transcript_api",
                full_text="covered",
                full_text_sha256="hash",
                segments=[TranscriptSegment("covered_video", 0, 0.0, None, "covered")],
            ),
        )
        conn.commit()

    report = build_transcript_coverage_bias_report()

    assert {"creator", "creator_category", "year", "title_keyword_signal"} <= set(report)
    assert sum(row["total"] for row in report["creator"]) == 2


def test_no_bypass_related_code_paths_exist() -> None:
    banned = [
        "yt-dlp",
        "yt_dlp",
        "whisper",
        "selenium",
        "playwright",
        "youtubei/v1",
        "cookies",
        "proxies",
        "rotating ip",
        "audio download",
    ]
    source_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("src/finfluencer_alpha").glob("**/*.py")
    )
    for term in banned:
        assert term not in source_text
