from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from finfluencer_alpha import provider_autopilot as autopilot
from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.provider_transcripts import (
    PROVIDER_FAILURE_COLUMNS,
    PROVIDER_IMPORT_COLUMNS,
    ProviderCollectionResult,
)
from finfluencer_alpha.youtube_transcripts import (
    TranscriptFetchResult,
    TranscriptSegment,
    store_transcript_result,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "autopilot.db") -> str:
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
    creator_category: str = "stock_picker",
    published_at: str = "2026-01-01T00:00:00Z",
    title: str = "Buy Nvidia stock now",
    description: str = "I am buying Nvidia stock and adding AMD.",
    views: int = 10_000,
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, creator_category, published_at,
              title, description, url, current_view_count, current_like_count,
              current_comment_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 100, 10)
            """,
            (
                video_id,
                f"channel_{creator}",
                creator,
                creator_category,
                published_at,
                title,
                description,
                f"https://www.youtube.com/watch?v={video_id}",
                views,
            ),
        )
        conn.commit()


def _insert_available_transcript(database_url: str, video_id: str) -> None:
    with connect(database_url) as conn:
        store_transcript_result(
            conn,
            TranscriptFetchResult(
                video_id=video_id,
                provider_name="TranscriptAPI.com",
                provider_version="",
                status="available",
                transcript_source="external_provider",
                retrieval_method="provider_transcript_api",
                full_text="covered transcript",
                full_text_sha256="hash",
                segments=[TranscriptSegment(video_id, 0, 0.0, None, "covered transcript")],
            ),
        )
        conn.commit()


def _seed_balanced_videos(database_url: str, count: int = 12) -> None:
    years = ["2022", "2023", "2024"]
    creators = ["Creator A", "Creator B", "Creator C", "Creator D"]
    categories = ["stock_picker", "macro_commentary", "news_attention"]
    for index in range(count):
        high_signal = index % 2 == 0
        _insert_video(
            database_url,
            f"video{index:06d}",
            creator=creators[index % len(creators)],
            creator_category=categories[index % len(categories)],
            published_at=f"{years[index % len(years)]}-01-01T00:00:00Z",
            title="Buy Nvidia stock now" if high_signal else "Personal finance habits",
            description=(
                "I am buying Nvidia stock and adding AMD."
                if high_signal
                else "A broad discussion about budgeting and planning."
            ),
            views=500 * (index + 1),
        )


def _base_config(tmp_path: Path, **overrides: Any) -> autopilot.ProviderAutopilotConfig:
    values: dict[str, Any] = {
        "provider": "transcriptapi",
        "target_new_transcripts": 3,
        "max_attempts": 6,
        "chunk_size": 2,
        "queue_size": 6,
        "min_low_signal_share": 0.5,
        "max_per_creator": 2,
        "max_per_year": 3,
        "sleep_seconds": 0.0,
        "confirm_provider_run": False,
        "dry_run": True,
        "run_root": tmp_path / "runs",
    }
    values.update(overrides)
    return autopilot.ProviderAutopilotConfig(**values)


def _write_provider_output(path: Path, video_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVIDER_IMPORT_COLUMNS)
        writer.writeheader()
        for video_id in video_ids:
            writer.writerow(
                {
                    "video_id": video_id,
                    "transcript_text": "I am buying Nvidia stock",
                    "transcript_source": "external_provider",
                    "provider_name": "TranscriptAPI.com",
                    "retrieval_method": "provider_transcript_api",
                    "is_asr_generated": "0",
                    "retrieved_at": "2026-05-11T00:00:00Z",
                    "notes": "provider_status=completed",
                    "language": "en",
                    "raw_provider_source": "caption",
                    "segment_json": json.dumps(
                        [
                            {
                                "text": "I am buying Nvidia stock",
                                "start_seconds": 0.0,
                                "duration_seconds": 2.0,
                            }
                        ]
                    ),
                    "source_confidence": "0.95",
                }
            )


def _write_provider_failures(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVIDER_FAILURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _fake_collect_factory(tmp_path: Path, outcomes: dict[str, list[str]]):
    calls: list[list[str]] = []
    failure_path = tmp_path / "provider_failures.csv"

    def fake_collect(
        *,
        config: autopilot.ProviderAutopilotConfig,
        input_path: Path,
        output_path: Path,
        limit: int,
    ) -> ProviderCollectionResult:
        del config, limit
        with input_path.open(newline="", encoding="utf-8") as handle:
            video_ids = [row["video_id"] for row in csv.DictReader(handle)]
        calls.append(video_ids)
        successes: list[str] = []
        failures: list[dict[str, str]] = []
        for video_id in video_ids:
            sequence = outcomes.setdefault(video_id, ["success"])
            outcome = sequence.pop(0) if sequence else "success"
            if outcome == "success":
                successes.append(video_id)
                continue
            failures.append(
                {
                    "video_id": video_id,
                    "provider": "TranscriptAPI.com",
                    "status": outcome,
                    "error_type": "provider_request_error",
                    "error_message": f"failed with {outcome}",
                    "retryable": "1" if outcome == "http_408" else "0",
                }
            )
        _write_provider_output(output_path, successes)
        _write_provider_failures(failure_path, failures)
        return ProviderCollectionResult(
            provider="transcriptapi",
            attempted_count=len(video_ids),
            successful_count=len(successes),
            failed_count=len(failures),
            skipped_existing_count=0,
            output_path=output_path,
            failure_path=failure_path,
        )

    return calls, fake_collect


def _patch_side_effects(monkeypatch) -> None:
    monkeypatch.setattr(autopilot, "_run_backup", lambda: {"status": "skipped_for_test"})
    monkeypatch.setattr(
        autopilot,
        "_run_post_run_tasks",
        lambda: {"status": "skipped_for_test"},
    )


def test_dry_run_queue_creation_balances_metadata(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "queue.db")
    _seed_balanced_videos(database_url)

    result = autopilot.run_provider_transcript_autopilot(_base_config(tmp_path))
    df = pd.read_csv(result.run_dir / "selected_queue.csv")

    assert result.dry_run is True
    assert len(df) == 6
    assert (df["title_signal"] == "low_signal").sum() >= 3
    assert df["creator"].value_counts().max() <= 2
    assert df["year"].value_counts().max() <= 3
    assert (result.run_dir / "chunk_001_input.csv").exists()
    assert (result.run_dir / "manifest.json").exists()


def test_autopilot_queue_has_no_duplicate_video_ids(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "duplicates.db")
    _seed_balanced_videos(database_url)

    result = autopilot.run_provider_transcript_autopilot(_base_config(tmp_path))
    df = pd.read_csv(result.run_dir / "selected_queue.csv")

    assert df["video_id"].is_unique


def test_autopilot_skips_existing_transcripts(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "existing.db")
    _insert_video(database_url, "covered_video")
    _insert_video(database_url, "pending_video", title="Personal finance habits", description="Budgeting.")
    _insert_available_transcript(database_url, "covered_video")

    result = autopilot.run_provider_transcript_autopilot(
        _base_config(tmp_path, queue_size=2, max_attempts=2, max_per_creator=0, max_per_year=0)
    )
    df = pd.read_csv(result.run_dir / "selected_queue.csv")
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert "covered_video" not in set(df["video_id"])
    assert "pending_video" in set(df["video_id"])
    assert manifest["totals"]["skipped_existing"] == 1


def test_http_404_is_not_retried(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "http404.db")
    _insert_video(database_url, "video404")
    calls, fake_collect = _fake_collect_factory(tmp_path, {"video404": ["http_404"]})
    monkeypatch.setattr(autopilot, "_collect_provider_chunk", fake_collect)
    _patch_side_effects(monkeypatch)

    result = autopilot.run_provider_transcript_autopilot(
        _base_config(
            tmp_path,
            dry_run=False,
            confirm_provider_run=True,
            queue_size=1,
            max_attempts=1,
            chunk_size=1,
            target_new_transcripts=1,
            max_retries=2,
            retry_statuses=("http_408",),
            max_per_creator=0,
            max_per_year=0,
        )
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert calls == [["video404"]]
    assert manifest["totals"]["failed"] == 1
    assert manifest["totals"]["retries"] == 0


def test_http_408_is_retried_up_to_max_retries(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "http408.db")
    _insert_video(database_url, "video408")
    calls, fake_collect = _fake_collect_factory(
        tmp_path,
        {"video408": ["http_408", "http_408", "success"]},
    )
    monkeypatch.setattr(autopilot, "_collect_provider_chunk", fake_collect)
    _patch_side_effects(monkeypatch)

    result = autopilot.run_provider_transcript_autopilot(
        _base_config(
            tmp_path,
            dry_run=False,
            confirm_provider_run=True,
            queue_size=1,
            max_attempts=1,
            chunk_size=1,
            target_new_transcripts=1,
            max_retries=2,
            retry_statuses=("http_408",),
            max_per_creator=0,
            max_per_year=0,
        )
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert calls == [["video408"], ["video408"], ["video408"]]
    assert manifest["totals"]["successful"] == 1
    assert manifest["totals"]["retries"] == 2


def test_resume_skips_completed_chunks(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "resume.db")
    for index in range(1, 4):
        _insert_video(database_url, f"video{index:06d}")
    run_dir = tmp_path / "runs" / "resume_run"
    run_dir.mkdir(parents=True)
    queue_rows = [
        {
            "queue_rank": index,
            "video_id": f"video{index:06d}",
            "url": f"https://www.youtube.com/watch?v=video{index:06d}",
            "creator": "Creator A",
            "creator_category": "stock_picker",
            "published_at": "2026-01-01T00:00:00Z",
            "year": "2026",
            "title": "Buy Nvidia stock now",
            "description": "I am buying Nvidia stock.",
            "priority_score": "10",
            "ticker_signal_count": "1",
            "recommendation_keyword_signal": "1",
            "title_signal": "high_signal",
            "engagement_bucket": "10k-99k",
            "current_view_count": "10000",
            "current_like_count": "100",
            "current_comment_count": "10",
            "sampling_stratum": "year=2026",
            "sampling_reason": "test",
        }
        for index in range(1, 4)
    ]
    autopilot._write_rows(run_dir / "selected_queue.csv", queue_rows, autopilot.QUEUE_COLUMNS)
    manifest = {
        "run_dir": str(run_dir),
        "status": "started",
        "started_at": "2026-05-11T00:00:00Z",
        "updated_at": "2026-05-11T00:00:00Z",
        "completed_at": None,
        "config": {
            "provider": "transcriptapi",
            "target_new_transcripts": 3,
            "max_attempts": 3,
            "chunk_size": 1,
            "queue_size": 3,
            "min_low_signal_share": 0.0,
            "max_per_creator": 0,
            "max_per_year": 0,
            "language": "en",
            "timestamps": False,
            "captions_only": False,
            "retry_statuses": ["http_408"],
            "max_retries": 2,
            "sleep_seconds": 0.0,
            "confirm_provider_run": True,
            "dry_run": False,
            "run_name": None,
            "resume": None,
            "run_root": str(tmp_path / "runs"),
        },
        "queue": {
            "selected_queue_path": str(run_dir / "selected_queue.csv"),
            "selected_count": 3,
            "eligible_count": 3,
            "skipped_existing_count": 0,
        },
        "chunks": [
            {
                "index": 1,
                "status": "completed",
                "attempted": 1,
                "provider_attempts_including_retries": 1,
                "successful": 1,
                "failed": 0,
                "skipped_existing": 0,
                "retries": 0,
            }
        ],
        "totals": {},
        "post_run": {},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    calls, fake_collect = _fake_collect_factory(tmp_path, {})
    monkeypatch.setattr(autopilot, "_collect_provider_chunk", fake_collect)
    _patch_side_effects(monkeypatch)

    result = autopilot.run_provider_transcript_autopilot(
        autopilot.ProviderAutopilotConfig(
            resume=run_dir,
            confirm_provider_run=True,
            sleep_seconds=0.0,
        )
    )

    assert calls == [["video000002"], ["video000003"]]
    assert result.successful == 3


def test_final_manifest_is_written(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "manifest.db")
    _insert_video(database_url, "video_manifest")
    calls, fake_collect = _fake_collect_factory(tmp_path, {"video_manifest": ["success"]})
    monkeypatch.setattr(autopilot, "_collect_provider_chunk", fake_collect)
    _patch_side_effects(monkeypatch)

    result = autopilot.run_provider_transcript_autopilot(
        _base_config(
            tmp_path,
            dry_run=False,
            confirm_provider_run=True,
            queue_size=1,
            max_attempts=1,
            chunk_size=1,
            target_new_transcripts=1,
            max_per_creator=0,
            max_per_year=0,
        )
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert calls == [["video_manifest"]]
    assert manifest["status"] == "completed"
    assert result.final_summary_path.exists()
