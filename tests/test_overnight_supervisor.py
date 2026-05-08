from pathlib import Path

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.overnight_supervisor import (
    OvernightSupervisorResult,
    _compute_recommended_action,
    _is_lock_stale,
    acquire_lock,
    release_lock,
    run_overnight_transcript_collection,
    write_final_summary,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "supervisor.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _insert_video(database_url: str, video_id: str, channel_title: str = "Test Channel",
                   published_at: str = "2026-01-01T00:00:00Z") -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                video_id, f"ch_{video_id}", channel_title, published_at,
                f"Title {video_id}", f"https://www.youtube.com/watch?v={video_id}",
            ),
        )
        conn.execute(
            """
            INSERT INTO transcript_fetch_queue (video_id, priority_score, transcript_status)
            VALUES (?, ?, NULL)
            """,
            (video_id, 10.0),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# dry-run tests
# ---------------------------------------------------------------------------


def test_dry_run_does_not_fetch_transcripts(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "dry_run.db")
    _insert_video(database_url, "dry_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    result = run_overnight_transcript_collection(
        batches=1, batch_limit=5, dry_run=True,
        log_path=log_path, summary_path=summary_path,
    )

    assert result.total_attempted == 0
    assert result.total_available == 0
    assert result.batches_completed == 0
    assert summary_path.exists()


# ---------------------------------------------------------------------------
# lock tests
# ---------------------------------------------------------------------------


def test_lock_prevents_duplicate_run(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "supervisor.lock"

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_supervisor.LOCK_PATH", lock_path
    )
    monkeypatch.setattr(
        "finfluencer_alpha.overnight_supervisor._setup_file_logging",
        lambda *a, **kw: __import__("logging").getLogger("test"),
    )

    assert lock_path.exists() is False

    acquired = acquire_lock()
    assert acquired is True
    assert lock_path.exists()

    acquired2 = acquire_lock()
    assert acquired2 is False

    release_lock()
    assert lock_path.exists() is False


def test_stale_lock_is_removed(monkeypatch, tmp_path: Path) -> None:
    import json

    lock_path = tmp_path / "stale.lock"

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_supervisor.LOCK_PATH", lock_path
    )
    monkeypatch.setattr(
        "finfluencer_alpha.overnight_supervisor._setup_file_logging",
        lambda *a, **kw: __import__("logging").getLogger("test"),
    )

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": 99999, "started_at": "2020-01-01T00:00:00Z"}))

    acquired = acquire_lock()
    assert acquired is True
    assert lock_path.exists()

    release_lock()


def test_is_lock_stale_dead_pid() -> None:
    data = {"pid": 99999}
    assert _is_lock_stale(data) is True


# ---------------------------------------------------------------------------
# readiness failure tests
# ---------------------------------------------------------------------------


def test_readiness_failure_stops_before_collection(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "notready.db")
    _insert_video(database_url, "notready_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    from finfluencer_alpha.overnight_readiness import OvernightReadiness

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.overnight_readiness_check",
        lambda: OvernightReadiness(
            ready=False,
            reasons=["DISK_TOO_LOW: 100 MB free (need 500 MB)"],
            free_disk_mb=100,
            cooldown_active=False,
            attempts_last_24h=0,
            max_daily_attempts=50,
            queue_eligible=1,
            high_risk_only_targets=0,
            false_positive_quarantine_count=0,
            recommended_command="DO NOT RUN",
        ),
    )

    result = run_overnight_transcript_collection(
        batches=3, batch_limit=5, dry_run=False,
        log_path=log_path, summary_path=summary_path,
        between_batch_sleep_seconds=0,
    )

    assert result.batches_completed == 0
    assert result.total_attempted == 0
    assert result.stopped_reason == "NOT_READY_FOR_OVERNIGHT"
    assert summary_path.exists()


# ---------------------------------------------------------------------------
# block stop-condition tests
# ---------------------------------------------------------------------------


def test_ip_blocked_stops_future_batches(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "blockstop.db")
    _insert_video(database_url, "block_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    from finfluencer_alpha.overnight_readiness import OvernightReadiness

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.overnight_readiness_check",
        lambda: OvernightReadiness(
            ready=True,
            reasons=["ALL_CLEAR"],
            free_disk_mb=50000,
            cooldown_active=False,
            attempts_last_24h=0,
            max_daily_attempts=50,
            queue_eligible=1,
            high_risk_only_targets=0,
            false_positive_quarantine_count=0,
            recommended_command="run",
        ),
    )

    call_count = [0]

    def fake_collect(*args, **kwargs):
        call_count[0] += 1
        from finfluencer_alpha.overtime_collection import OvertimeCollectionResult
        return OvertimeCollectionResult(
            run_id=call_count[0],
            attempted_count=1,
            available_count=0,
            status_counts={"ip_blocked": 1},
            stopped_reason="ip_blocked",
        )

    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection.collect_native_transcripts_overtime",
        fake_collect,
    )

    result = run_overnight_transcript_collection(
        batches=5, batch_limit=1, dry_run=False,
        log_path=log_path, summary_path=summary_path,
        between_batch_sleep_seconds=0, sleep_seconds=0, jitter_seconds=0,
        min_disk_mb=0,
    )

    assert call_count[0] == 1
    assert result.total_ip_blocked == 1
    assert result.batches_completed == 1
    assert result.stopped_reason == "block_detected:ip_blocked"
    assert result.recommended_next_action == "WAIT_FOR_COOLDOWN"
    assert summary_path.exists()


# ---------------------------------------------------------------------------
# disk guard tests
# ---------------------------------------------------------------------------


def test_disk_guard_stops_future_batches(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "diskstop.db")
    _insert_video(database_url, "disk_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    from finfluencer_alpha.overnight_readiness import OvernightReadiness

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.overnight_readiness_check",
        lambda: OvernightReadiness(
            ready=True,
            reasons=["ALL_CLEAR"],
            free_disk_mb=50000,
            cooldown_active=False,
            attempts_last_24h=0,
            max_daily_attempts=50,
            queue_eligible=1,
            high_risk_only_targets=0,
            false_positive_quarantine_count=0,
            recommended_command="run",
        ),
    )

    call_count = [0]

    def fake_collect(*args, **kwargs):
        call_count[0] += 1
        from finfluencer_alpha.overtime_collection import OvertimeCollectionResult
        return OvertimeCollectionResult(
            run_id=call_count[0],
            attempted_count=1,
            available_count=0,
            status_counts={},
            stopped_reason="disk_below_500mb",
        )

    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection.collect_native_transcripts_overtime",
        fake_collect,
    )

    result = run_overnight_transcript_collection(
        batches=5, batch_limit=1, dry_run=False,
        log_path=log_path, summary_path=summary_path,
        between_batch_sleep_seconds=0, sleep_seconds=0, jitter_seconds=0,
        min_disk_mb=0,
    )

    assert call_count[0] == 1
    assert result.batches_completed == 1
    assert result.stopped_reason == "disk_below_500mb"
    assert summary_path.exists()


# ---------------------------------------------------------------------------
# summary tests
# ---------------------------------------------------------------------------


def test_summary_file_is_written(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    result = run_overnight_transcript_collection(
        batches=1, batch_limit=5, dry_run=True,
        log_path=log_path, summary_path=summary_path,
    )

    assert summary_path.exists()
    content = summary_path.read_text()
    assert "Overnight Transcript Collection Summary" in content
    assert result.started_at in content


def test_summary_includes_per_batch_detail(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "summary_detail.db")
    _insert_video(database_url, "detail_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    from finfluencer_alpha.overnight_readiness import OvernightReadiness

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.overnight_readiness_check",
        lambda: OvernightReadiness(
            ready=True,
            reasons=["ALL_CLEAR"],
            free_disk_mb=50000,
            cooldown_active=False,
            attempts_last_24h=0,
            max_daily_attempts=50,
            queue_eligible=1,
            high_risk_only_targets=0,
            false_positive_quarantine_count=0,
            recommended_command="run",
        ),
    )

    call_count = [0]

    def fake_collect(*args, **kwargs):
        call_count[0] += 1
        from finfluencer_alpha.overtime_collection import OvertimeCollectionResult
        return OvertimeCollectionResult(
            run_id=call_count[0],
            attempted_count=3,
            available_count=2,
            status_counts={"available": 2, "no_language": 1},
            stopped_reason=None,
        )

    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection.collect_native_transcripts_overtime",
        fake_collect,
    )

    result = run_overnight_transcript_collection(
        batches=2, batch_limit=3, dry_run=False,
        log_path=log_path, summary_path=summary_path,
        between_batch_sleep_seconds=0, sleep_seconds=0, jitter_seconds=0,
        min_disk_mb=0,
    )

    assert result.batches_completed == 2
    assert result.total_attempted == 6
    assert result.total_available == 4
    assert summary_path.exists()

    content = summary_path.read_text()
    assert "Total attempted:" in content
    assert "Total available:" in content
    assert "Per-Batch Detail" in content


# ---------------------------------------------------------------------------
# batch loop respects max batches
# ---------------------------------------------------------------------------


def test_batch_loop_respects_max_batches(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "max_batches.db")
    _insert_video(database_url, "batch_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    from finfluencer_alpha.overnight_readiness import OvernightReadiness

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.overnight_readiness_check",
        lambda: OvernightReadiness(
            ready=True,
            reasons=["ALL_CLEAR"],
            free_disk_mb=50000,
            cooldown_active=False,
            attempts_last_24h=0,
            max_daily_attempts=50,
            queue_eligible=1,
            high_risk_only_targets=0,
            false_positive_quarantine_count=0,
            recommended_command="run",
        ),
    )

    call_count = [0]

    def fake_collect(*args, **kwargs):
        call_count[0] += 1
        from finfluencer_alpha.overtime_collection import OvertimeCollectionResult
        return OvertimeCollectionResult(
            run_id=call_count[0],
            attempted_count=1,
            available_count=1,
            status_counts={"available": 1},
            stopped_reason=None,
        )

    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection.collect_native_transcripts_overtime",
        fake_collect,
    )

    result = run_overnight_transcript_collection(
        batches=3, batch_limit=1, dry_run=False,
        log_path=log_path, summary_path=summary_path,
        between_batch_sleep_seconds=0, sleep_seconds=0, jitter_seconds=0,
        min_disk_mb=0,
    )

    assert call_count[0] == 3
    assert result.batches_completed == 3
    assert result.stopped_reason == "completed_all_batches"
    assert summary_path.exists()


# ---------------------------------------------------------------------------
# no event rebuild by default
# ---------------------------------------------------------------------------


def test_no_event_rebuild_by_default(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "no_rebuild.db")
    _insert_video(database_url, "norebuild_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    from finfluencer_alpha.overnight_readiness import OvernightReadiness

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.overnight_readiness_check",
        lambda: OvernightReadiness(
            ready=True,
            reasons=["ALL_CLEAR"],
            free_disk_mb=50000,
            cooldown_active=False,
            attempts_last_24h=0,
            max_daily_attempts=50,
            queue_eligible=1,
            high_risk_only_targets=0,
            false_positive_quarantine_count=0,
            recommended_command="run",
        ),
    )

    rebuild_called = [False]

    def fake_rebuild(*args, **kwargs):
        rebuild_called[0] = True

    monkeypatch.setattr(
        "finfluencer_alpha.transcript_classify.build_transcript_recommendation_events",
        fake_rebuild,
    )
    monkeypatch.setattr(
        "finfluencer_alpha.transcript_exports.export_transcript_events",
        lambda: {},
    )

    call_count = [0]

    def fake_collect(*args, **kwargs):
        call_count[0] += 1
        from finfluencer_alpha.overtime_collection import OvertimeCollectionResult
        return OvertimeCollectionResult(
            run_id=call_count[0],
            attempted_count=1,
            available_count=1,
            status_counts={"available": 1},
            stopped_reason=None,
        )

    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection.collect_native_transcripts_overtime",
        fake_collect,
    )

    result = run_overnight_transcript_collection(
        batches=1, batch_limit=1, dry_run=False,
        rebuild_events_at_end=False,
        log_path=log_path, summary_path=summary_path,
        between_batch_sleep_seconds=0, sleep_seconds=0, jitter_seconds=0,
        min_disk_mb=0,
    )

    assert rebuild_called[0] is False
    assert result.batches_completed == 1
    assert summary_path.exists()


# ---------------------------------------------------------------------------
# event rebuild only when flag is passed
# ---------------------------------------------------------------------------


def test_event_rebuild_when_flag_passed(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "rebuild.db")
    _insert_video(database_url, "rebuild_vid")

    log_path = tmp_path / "overnight.log"
    summary_path = tmp_path / "summary.txt"

    from finfluencer_alpha.overnight_readiness import OvernightReadiness

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.overnight_readiness_check",
        lambda: OvernightReadiness(
            ready=True,
            reasons=["ALL_CLEAR"],
            free_disk_mb=50000,
            cooldown_active=False,
            attempts_last_24h=0,
            max_daily_attempts=50,
            queue_eligible=1,
            high_risk_only_targets=0,
            false_positive_quarantine_count=0,
            recommended_command="run",
        ),
    )

    rebuild_called = [False]

    def fake_rebuild(refresh_existing=False):
        rebuild_called[0] = True
        from finfluencer_alpha.transcript_classify import TranscriptBuildResult
        return TranscriptBuildResult(
            candidate_windows=0,
            events=0,
        )

    monkeypatch.setattr(
        "finfluencer_alpha.transcript_classify.build_transcript_recommendation_events",
        fake_rebuild,
    )
    monkeypatch.setattr(
        "finfluencer_alpha.transcript_exports.export_transcript_events",
        lambda: {},
    )

    call_count = [0]

    def fake_collect(*args, **kwargs):
        call_count[0] += 1
        from finfluencer_alpha.overtime_collection import OvertimeCollectionResult
        return OvertimeCollectionResult(
            run_id=call_count[0],
            attempted_count=1,
            available_count=1,
            status_counts={"available": 1},
            stopped_reason=None,
        )

    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection.collect_native_transcripts_overtime",
        fake_collect,
    )

    result = run_overnight_transcript_collection(
        batches=1, batch_limit=1, dry_run=False,
        rebuild_events_at_end=True,
        log_path=log_path, summary_path=summary_path,
        between_batch_sleep_seconds=0, sleep_seconds=0, jitter_seconds=0,
        min_disk_mb=0,
    )

    assert rebuild_called[0] is True
    assert result.batches_completed == 1
    assert summary_path.exists()


# ---------------------------------------------------------------------------
# recommended action logic
# ---------------------------------------------------------------------------


def test_recommended_action_wait_for_cooldown() -> None:
    action = _compute_recommended_action(
        stopped_reason="block_detected:ip_blocked",
        block_detected=True,
        total_attempted=1,
        total_available=0,
    )
    assert action == "WAIT_FOR_COOLDOWN"


def test_recommended_action_run_another() -> None:
    action = _compute_recommended_action(
        stopped_reason="completed_all_batches",
        block_detected=False,
        total_attempted=10,
        total_available=8,
    )
    assert action == "RUN_ANOTHER_OVERNIGHT"


def test_recommended_action_pay_provider() -> None:
    action = _compute_recommended_action(
        stopped_reason="completed_all_batches",
        block_detected=False,
        total_attempted=10,
        total_available=0,
    )
    assert action == "PAY_FOR_PROVIDER"


def test_recommended_action_move_to_classifier() -> None:
    action = _compute_recommended_action(
        stopped_reason="completed_all_batches",
        block_detected=False,
        total_attempted=0,
        total_available=0,
    )
    assert action == "MOVE_TO_CLASSIFIER_TRAINING"


# ---------------------------------------------------------------------------
# write_final_summary standalone
# ---------------------------------------------------------------------------


def test_write_final_summary_creates_file(tmp_path: Path) -> None:
    result = OvernightSupervisorResult(
        started_at="2026-05-07T00:00:00Z",
        ended_at="2026-05-07T06:00:00Z",
        batches_requested=8,
        batches_completed=8,
        total_attempted=40,
        total_available=30,
        total_no_transcript=5,
        total_ip_blocked=0,
        total_request_blocked=0,
        total_rate_limited=0,
        total_other_errors=5,
        starting_transcript_count=100,
        ending_transcript_count=130,
        starting_accepted_events=97,
        ending_accepted_events=97,
        disk_start_mb=1000,
        disk_end_mb=800,
        stopped_reason="completed_all_batches",
        recommended_next_action="RUN_ANOTHER_OVERNIGHT",
    )

    summary_path = tmp_path / "summary.txt"
    path = write_final_summary(result, summary_path)

    assert path == summary_path
    assert summary_path.exists()
    content = summary_path.read_text()
    assert "Transcript gain:            30" in content
    assert "Starting transcript count:  100" in content
    assert "Ending transcript count:    130" in content
    assert "RUN_ANOTHER_OVERNIGHT" in content
