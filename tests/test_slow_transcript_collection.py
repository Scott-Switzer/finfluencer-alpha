from __future__ import annotations

import csv
from pathlib import Path

import pytest

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.slow_transcript_collection import (
    _resolve_database_url,
    build_manual_transcript_collection_packet,
    build_slow_collection_daily_plan,
    collect_youtube_transcripts_slow,
    plan_slow_youtube_transcript_queue,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def _init_test_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    _clear_settings_cache()
    from finfluencer_alpha.db import init_db

    init_db()
    return db_path


def test_plan_queue_excludes_videos_with_transcripts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)
    from finfluencer_alpha.db import connect

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
            VALUES (?, ?, ?, ?)
            """,
            ("ex_vid1", "Title 1", "Creator A", "2021-06-01T12:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
            VALUES (?, ?, ?, ?)
            """,
            ("ex_vid2", "Title 2", "Creator B", "2021-06-02T12:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("ex_vid1", "available", "youtube_transcript_api"),
        )
        conn.commit()

    result = plan_slow_youtube_transcript_queue(
        start_year=2021,
        end_year=2021,
        max_videos=10,
        output_path=tmp_path / "queue.csv",
        summary_md_path=tmp_path / "queue.md",
    )
    assert result.queue_size == 1
    queue = list(csv.DictReader((tmp_path / "queue.csv").open()))
    assert queue[0]["video_id"] == "ex_vid2"


def test_plan_queue_prioritizes_earlier_years(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)
    from finfluencer_alpha.db import connect

    with connect() as conn:
        for year, vid in [(2020, "py_vid2020"), (2021, "py_vid2021"), (2022, "py_vid2022")]:
            conn.execute(
                """
                INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
                VALUES (?, ?, ?, ?)
                """,
                (vid, f"Title {year}", "Creator", f"{year}-06-01T12:00:00Z"),
            )
        conn.commit()

    result = plan_slow_youtube_transcript_queue(
        start_year=2020,
        end_year=2022,
        max_videos=10,
        output_path=tmp_path / "queue.csv",
        summary_md_path=tmp_path / "queue.md",
    )
    assert result.queue_size == 3
    queue = list(csv.DictReader((tmp_path / "queue.csv").open()))
    years = [row["year"] for row in queue]
    assert years == ["2020", "2021", "2022"]


def test_plan_queue_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)
    from finfluencer_alpha.db import connect

    with connect() as conn:
        for i in range(5):
            conn.execute(
                """
                INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
                VALUES (?, ?, ?, ?)
                """,
                (f"det_vid{i}", f"Title {i}", "Creator", f"2021-06-0{i+1}T12:00:00Z"),
            )
        conn.commit()

    result1 = plan_slow_youtube_transcript_queue(
        start_year=2021,
        end_year=2021,
        max_videos=10,
        output_path=tmp_path / "q1.csv",
        summary_md_path=tmp_path / "q1.md",
    )
    result2 = plan_slow_youtube_transcript_queue(
        start_year=2021,
        end_year=2021,
        max_videos=10,
        output_path=tmp_path / "q2.csv",
        summary_md_path=tmp_path / "q2.md",
    )
    assert result1.queue_size == result2.queue_size == 5
    ids1 = [r["video_id"] for r in csv.DictReader((tmp_path / "q1.csv").open())]
    ids2 = [r["video_id"] for r in csv.DictReader((tmp_path / "q2.csv").open())]
    assert ids1 == ids2


def test_collect_dry_run_makes_no_db_writes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)

    _write_csv(
        tmp_path / "queue.csv",
        [
            {
                "video_id": "dry_vid1",
                "title": "Test",
                "channel_title": "Creator",
                "published_at": "2021-06-01T12:00:00Z",
                "year": "2021",
                "current_transcript_status": "missing",
            }
        ],
    )

    result = collect_youtube_transcripts_slow(
        input_path=tmp_path / "queue.csv",
        max_videos=10,
        delay_seconds=0,
        confirm_run=False,
        output_summary_csv=tmp_path / "summary.csv",
        output_summary_md=tmp_path / "summary.md",
    )
    assert result.attempted == 0
    assert result.stop_reason == "dry_run"


def test_collect_skips_existing_transcripts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)
    from finfluencer_alpha.db import connect

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
            VALUES (?, ?, ?, ?)
            """,
            ("skip_vid1", "Title", "Creator", "2021-06-01T12:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("skip_vid1", "available", "youtube_transcript_api"),
        )
        conn.commit()

    _write_csv(
        tmp_path / "queue.csv",
        [
            {
                "video_id": "skip_vid1",
                "title": "Test",
                "channel_title": "Creator",
                "published_at": "2021-06-01T12:00:00Z",
                "year": "2021",
                "current_transcript_status": "missing",
            }
        ],
    )

    result = collect_youtube_transcripts_slow(
        input_path=tmp_path / "queue.csv",
        max_videos=10,
        delay_seconds=0,
        confirm_run=True,
        output_summary_csv=tmp_path / "summary.csv",
        output_summary_md=tmp_path / "summary.md",
    )
    assert result.skipped_existing == 1
    assert result.imported == 0


def test_block_like_stop_triggers_manual_packet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)

    _write_csv(
        tmp_path / "queue.csv",
        [
            {
                "video_id": "blk_vid1",
                "title": "Test",
                "channel_title": "Creator",
                "published_at": "2021-06-01T12:00:00Z",
                "year": "2021",
                "current_transcript_status": "missing",
            }
        ],
    )

    def fake_fetch(*args: object, **kwargs: object) -> object:
        from finfluencer_alpha.youtube_transcripts import TranscriptFetchResult

        return TranscriptFetchResult(
            video_id=args[0] if args else "",
            provider_name="youtube_transcript_api",
            provider_version="0.0",
            status="request_blocked",
            error_type="RequestBlocked",
            error_message="blocked",
        )

    monkeypatch.setattr(
        "finfluencer_alpha.slow_transcript_collection.fetch_transcript_for_video", fake_fetch
    )

    result = collect_youtube_transcripts_slow(
        input_path=tmp_path / "queue.csv",
        max_videos=10,
        delay_seconds=0,
        stop_on_block=True,
        confirm_run=True,
        output_summary_csv=tmp_path / "summary.csv",
        output_summary_md=tmp_path / "summary.md",
    )
    assert result.block_detected is True
    assert result.stop_reason == "request_blocked"
    assert result.fallback_triggered is True
    assert result.fallback_route == "manual_packet_after_block"


def test_no_transcript_found_routes_to_manual_packet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)

    _write_csv(
        tmp_path / "queue.csv",
        [
            {
                "video_id": "nt_vid1",
                "title": "Test",
                "channel_title": "Creator",
                "published_at": "2021-06-01T12:00:00Z",
                "year": "2021",
                "current_transcript_status": "missing",
            }
        ],
    )

    def fake_fetch(*args: object, **kwargs: object) -> object:
        from finfluencer_alpha.youtube_transcripts import TranscriptFetchResult

        return TranscriptFetchResult(
            video_id=args[0] if args else "",
            provider_name="youtube_transcript_api",
            provider_version="0.0",
            status="no_language",
            error_type="NoTranscriptFound",
            error_message="not found",
        )

    monkeypatch.setattr(
        "finfluencer_alpha.slow_transcript_collection.fetch_transcript_for_video", fake_fetch
    )

    result = collect_youtube_transcripts_slow(
        input_path=tmp_path / "queue.csv",
        max_videos=10,
        delay_seconds=0,
        confirm_run=True,
        output_summary_csv=tmp_path / "summary.csv",
        output_summary_md=tmp_path / "summary.md",
    )
    assert result.terminal_failures == 1
    assert result.imported == 0


def test_manual_packet_builds_correctly(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "queue.csv",
        [
            {
                "video_id": "mp_vid1",
                "title": "Title 1",
                "channel_title": "Creator A",
                "published_at": "2021-06-01T12:00:00Z",
                "year": "2021",
                "current_transcript_status": "missing",
                "priority_reason": "older_year:2021",
            },
            {
                "video_id": "mp_vid2",
                "title": "Title 2",
                "channel_title": "Creator B",
                "published_at": "2020-01-01T12:00:00Z",
                "year": "2020",
                "current_transcript_status": "available",
                "priority_reason": "older_year:2020",
            },
        ],
    )

    result = build_manual_transcript_collection_packet(
        input_path=tmp_path / "queue.csv",
        max_videos=100,
        output_packet_csv=tmp_path / "packet.csv",
        output_packet_md=tmp_path / "packet.md",
        output_template_csv=tmp_path / "template.csv",
    )
    assert result.packet_size == 1
    packet = list(csv.DictReader((tmp_path / "packet.csv").open()))
    assert packet[0]["video_id"] == "mp_vid1"
    assert packet[0]["transcript_source"] == "manual_public_transcript_surface"
    assert "youtube.com/watch?v=mp_vid1" in packet[0]["youtube_url"]


def test_daily_plan_is_created(tmp_path: Path) -> None:
    path = build_slow_collection_daily_plan(output_path=tmp_path / "plan.md")
    assert path.exists()
    text = path.read_text()
    assert "10-Video Test Run" in text
    assert "Normal 25-Video Run" in text
    assert "build-transcript-provenance-report" in text


def test_summary_includes_recommended_next_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)

    _write_csv(
        tmp_path / "queue.csv",
        [
            {
                "video_id": "sum_vid1",
                "title": "Test",
                "channel_title": "Creator",
                "published_at": "2021-06-01T12:00:00Z",
                "year": "2021",
                "current_transcript_status": "missing",
            }
        ],
    )

    def fake_fetch(*args: object, **kwargs: object) -> object:
        from finfluencer_alpha.youtube_transcripts import TranscriptFetchResult

        return TranscriptFetchResult(
            video_id=args[0] if args else "",
            provider_name="youtube_transcript_api",
            provider_version="0.0",
            status="request_blocked",
            error_type="RequestBlocked",
            error_message="blocked",
        )

    monkeypatch.setattr(
        "finfluencer_alpha.slow_transcript_collection.fetch_transcript_for_video", fake_fetch
    )

    result = collect_youtube_transcripts_slow(
        input_path=tmp_path / "queue.csv",
        max_videos=10,
        delay_seconds=0,
        stop_on_block=True,
        confirm_run=True,
        output_summary_csv=tmp_path / "summary.csv",
        output_summary_md=tmp_path / "summary.md",
    )
    assert "build-manual-transcript-collection-packet" in result.recommended_next_command
    summary_md = (tmp_path / "summary.md").read_text()
    assert "build-manual-transcript-collection-packet" in summary_md


def test_resolve_database_url_uses_explicit_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit = f"sqlite:///{tmp_path / 'explicit.db'}"
    resolved, using_default = _resolve_database_url(explicit)
    assert resolved == explicit
    assert using_default is False


def test_resolve_database_url_fallback_on_missing_temp_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad_url = "sqlite:///tmp/pytest-of-user/test_0/test.db"
    monkeypatch.setenv("DATABASE_URL", bad_url)
    _clear_settings_cache()
    resolved, using_default = _resolve_database_url()
    assert resolved == "sqlite:///data/finfluencer_alpha.db"
    assert using_default is True


def test_collect_with_explicit_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "explicit_run.db"
    explicit_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/nonexistent_pytest_temp.db")
    _clear_settings_cache()

    from finfluencer_alpha.db import init_db

    init_db(database_url=explicit_url)

    _write_csv(
        tmp_path / "queue.csv",
        [
            {
                "video_id": "db_vid1",
                "title": "Test",
                "channel_title": "Creator",
                "published_at": "2021-06-01T12:00:00Z",
                "year": "2021",
                "current_transcript_status": "missing",
            }
        ],
    )

    def fake_fetch(*args: object, **kwargs: object) -> object:
        from finfluencer_alpha.youtube_transcripts import TranscriptFetchResult

        return TranscriptFetchResult(
            video_id=args[0] if args else "",
            provider_name="youtube_transcript_api",
            provider_version="0.0",
            status="request_blocked",
            error_type="RequestBlocked",
            error_message="blocked",
        )

    monkeypatch.setattr(
        "finfluencer_alpha.slow_transcript_collection.fetch_transcript_for_video", fake_fetch
    )

    result = collect_youtube_transcripts_slow(
        input_path=tmp_path / "queue.csv",
        max_videos=10,
        delay_seconds=0,
        stop_on_block=True,
        confirm_run=True,
        database_url=explicit_url,
        output_summary_csv=tmp_path / "summary.csv",
        output_summary_md=tmp_path / "summary.md",
    )
    assert result.block_detected is True
    summary_md = (tmp_path / "summary.md").read_text()
    assert "Resolved database URL" in summary_md
    assert "explicit_run.db" in summary_md
