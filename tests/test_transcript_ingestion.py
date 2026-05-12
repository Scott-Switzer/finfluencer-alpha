import hashlib
from pathlib import Path

import pandas as pd

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.transcript_ingestion import (
    build_transcript_provenance_report,
    import_manual_transcripts_with_summary,
    plan_next_paid_transcript_batch,
)
from finfluencer_alpha.youtube_transcripts import (
    TranscriptFetchResult,
    TranscriptSegment,
    store_transcript_result,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "ingestion.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _insert_video(
    database_url: str,
    video_id: str,
    *,
    creator: str = "Creator A",
    published_at: str = "2026-01-01T00:00:00Z",
    title: str = "Stocks to Buy Now",
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                f"channel_{creator}",
                creator,
                published_at,
                title,
                f"https://www.youtube.com/watch?v={video_id}",
            ),
        )
        conn.commit()


def _store_transcript(
    database_url: str,
    video_id: str,
    *,
    source: str = "youtube",
    text: str = "covered transcript text",
    provider: str = "youtube_transcript_api",
) -> None:
    with connect(database_url) as conn:
        store_transcript_result(
            conn,
            TranscriptFetchResult(
                video_id=video_id,
                provider_name=provider,
                provider_version="test",
                status="available",
                transcript_source=source,
                retrieval_method="test_import",
                retrieval_status="available",
                full_text=text,
                full_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                segments=[TranscriptSegment(video_id, 0, 0.0, None, text)],
                collected_at="2026-05-12T00:00:00Z",
                character_count=len(text),
                word_count=len(text.split()),
            ),
        )
        conn.commit()


def _write_manual_csv(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "video_id",
        "transcript_text",
        "transcript_source",
        "collected_at",
        "collector_notes",
    ]
    path.write_text(
        ",".join(columns)
        + "\n"
        + "\n".join(",".join(row.get(column, "") for column in columns) for row in rows)
        + "\n",
        encoding="utf-8",
    )


def _long_transcript() -> str:
    return "I am buying Nvidia stock because revenue growth and valuation look attractive. " * 8


def test_next_paid_batch_selection_is_deterministic(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "deterministic.db")
    _insert_video(database_url, "video_b", published_at="2026-01-01T00:00:00Z")
    _insert_video(database_url, "video_a", published_at="2026-01-01T00:00:00Z")
    _insert_video(database_url, "video_c", published_at="2025-12-31T00:00:00Z")

    result = plan_next_paid_transcript_batch(
        credit_budget=3,
        csv_path=tmp_path / "batch.csv",
        md_path=tmp_path / "batch.md",
    )
    df = pd.read_csv(result.csv_path)

    assert result.selected_count == 3
    assert list(df["video_id"]) == ["video_a", "video_b", "video_c"]
    assert list(df["selected_order"]) == [1, 2, 3]


def test_next_paid_batch_respects_credit_budget(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "budget.db")
    for index in range(5):
        _insert_video(database_url, f"video_{index}", published_at=f"2026-01-0{index + 1}T00:00:00Z")

    result = plan_next_paid_transcript_batch(
        credit_budget=2,
        csv_path=tmp_path / "batch.csv",
        md_path=tmp_path / "batch.md",
    )
    df = pd.read_csv(result.csv_path)

    assert result.selected_count == 2
    assert int(df["estimated_credit_cost"].sum()) == 2


def test_planning_mode_makes_no_provider_call(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "no_provider.db")
    _insert_video(database_url, "video_a")

    import finfluencer_alpha.provider_transcripts as provider_transcripts

    def fail_provider_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("planning mode should not call transcript providers")

    monkeypatch.setattr(provider_transcripts, "collect_provider_transcripts", fail_provider_call)

    result = plan_next_paid_transcript_batch(
        credit_budget=1,
        csv_path=tmp_path / "batch.csv",
        md_path=tmp_path / "batch.md",
    )

    assert result.selected_count == 1


def test_manual_import_rejects_unknown_video_id(monkeypatch, tmp_path: Path) -> None:
    _use_temp_db(monkeypatch, tmp_path, "manual_missing_id.db")
    csv_path = tmp_path / "manual.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "missing_video",
                "transcript_text": _long_transcript(),
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            }
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    summary = pd.read_csv(result.summary_csv_path)

    assert result.rejected_count == 1
    assert summary.loc[0, "status"] == "rejected_unknown_video_id"


def test_manual_import_rejects_empty_transcript(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "manual_empty.db")
    _insert_video(database_url, "video_a")
    csv_path = tmp_path / "manual.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "video_a",
                "transcript_text": "",
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            }
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    summary = pd.read_csv(result.summary_csv_path)

    assert result.rejected_count == 1
    assert summary.loc[0, "status"] == "rejected_empty_transcript"


def test_manual_import_detects_duplicate_checksum(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "manual_duplicate.db")
    _insert_video(database_url, "video_a")
    _insert_video(database_url, "video_b")
    csv_path = tmp_path / "manual.csv"
    transcript = _long_transcript()
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "video_a",
                "transcript_text": transcript,
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            },
            {
                "video_id": "video_b",
                "transcript_text": transcript,
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            },
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    summary = pd.read_csv(result.summary_csv_path)

    assert result.duplicate_checksum_count == 2
    assert set(summary["status"]) == {"rejected_duplicate_checksum"}


def test_manual_import_does_not_overwrite_by_default(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "manual_existing.db")
    _insert_video(database_url, "video_a")
    _store_transcript(database_url, "video_a", text="existing transcript")
    csv_path = tmp_path / "manual.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "video_a",
                "transcript_text": _long_transcript(),
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            }
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=False,
        confirm_import=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )

    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT full_text FROM youtube_transcripts WHERE video_id = 'video_a'"
        ).fetchone()
    assert result.imported_count == 0
    assert result.skipped_existing_count == 1
    assert row["full_text"] == "existing transcript"


def test_provenance_report_builds_from_fixtures(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "provenance.db")
    _insert_video(database_url, "video_paid", creator="Creator A", published_at="2026-01-01T00:00:00Z")
    _insert_video(database_url, "video_native", creator="Creator B", published_at="2025-01-01T00:00:00Z")
    _insert_video(database_url, "video_manual", creator="Creator B", published_at="2025-02-01T00:00:00Z")
    _insert_video(database_url, "video_missing", creator="Creator C", published_at="2024-01-01T00:00:00Z")
    _store_transcript(
        database_url,
        "video_paid",
        source="paid_provider",
        provider="TranscriptAPI.com",
        text=_long_transcript(),
    )
    _store_transcript(database_url, "video_native", source="youtube", text=_long_transcript())
    _store_transcript(
        database_url,
        "video_manual",
        source="manual_youtube_ui",
        provider="manual_youtube_ui",
        text=_long_transcript() + " extra",
    )

    result = build_transcript_provenance_report(
        csv_path=tmp_path / "provenance.csv",
        md_path=tmp_path / "provenance.md",
        methodology_note_path=tmp_path / "methodology.md",
    )
    summary = pd.read_csv(result.csv_path)

    assert result.total_videos == 4
    assert result.videos_with_transcripts == 3
    assert result.videos_missing_transcripts == 1
    assert "paid_provider_transcript_count" in set(summary["label"])
    assert result.md_path.exists()
    assert result.methodology_note_path.exists()
