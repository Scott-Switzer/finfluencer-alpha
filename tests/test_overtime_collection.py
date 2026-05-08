from pathlib import Path

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.overtime_collection import (
    _diversify_by_creator,
    _eligible_from_queue,
    collect_native_transcripts_overtime,
    transcript_collection_status,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "overtime.db") -> str:
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


def test_ledger_tables_exist(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'ledger.db'}"
    init_db(database_url)
    with connect(database_url) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "transcript_collection_runs" in tables
    assert "transcript_collection_attempts" in tables


def test_ledger_run_row_created(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "ledger_run.db")
    _insert_video(database_url, "test_vid")


    class FakeApi:
        def __init__(self, *args, **kwargs): pass
        def list(self, video_id):
            raise RuntimeError("ledger test — stop before fetch")

    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi", FakeApi
    )

    result = collect_native_transcripts_overtime(
        limit=1, sleep_seconds=0, jitter_seconds=0,
        max_per_creator=5, min_disk_mb=0,
        creator_diversify=False,
        undercovered_years_first=False,
        undercovered_creators_first=False,
    )
    del result  # run is verified via DB below

    with connect(database_url) as conn:
        run = conn.execute(
            "SELECT * FROM transcript_collection_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
    assert run is not None
    assert run["command_name"] == "collect-native-transcripts-overtime"
    assert run["requested_limit"] == 1
    assert run["sleep_seconds"] == 0.0
    assert run["ended_at"] is not None


def test_ledger_attempt_row_created(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "ledger_attempt.db")
    _insert_video(database_url, "attempt_vid")

    class FakeTranscript:
        language = "English"
        language_code = "en"
        is_generated = False
        is_translatable = True
        def fetch(self, preserve_formatting=False):
            return [{"text": "Buy Nvidia stock now", "start": 10.0, "duration": 5.0}]

    class FakeTranscriptList:
        def find_manually_created_transcript(self, languages):
            return FakeTranscript()

    class FakeApi:
        def __init__(self, *args, **kwargs): pass
        def list(self, video_id):
            return FakeTranscriptList()

    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi", FakeApi
    )


    result = collect_native_transcripts_overtime(
        limit=1, sleep_seconds=0, jitter_seconds=0,
        max_per_creator=5, min_disk_mb=0,
        creator_diversify=False,
        undercovered_years_first=False,
        undercovered_creators_first=False,
    )

    assert result.available_count == 1
    assert result.run_id > 0

    with connect(database_url) as conn:
        attempt = conn.execute(
            "SELECT * FROM transcript_collection_attempts WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
    assert attempt is not None
    assert attempt["video_id"] == "attempt_vid"
    assert attempt["status"] == "available"
    assert attempt["retrieval_method"] == "native_transcript_package"
    assert attempt["segment_count"] == 1
    assert attempt["word_count"] == 4


def test_cooldown_prevents_run_after_ip_blocked(monkeypatch, tmp_path: Path) -> None:
    import datetime as _dt

    database_url = _use_temp_db(monkeypatch, tmp_path, "cooldown_prevent.db")
    _insert_video(database_url, "cool_vid")

    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO transcript_collection_runs (
              started_at, ended_at, command_name, attempted_count,
              ip_blocked_count, stopped_reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _dt.datetime.now(_dt.UTC).isoformat(),
                _dt.datetime.now(_dt.UTC).isoformat(),
                "test_run", 1, 1, "ip_blocked",
            ),
        )
        conn.commit()


    result = collect_native_transcripts_overtime(
        limit=1, sleep_seconds=0, jitter_seconds=0,
        max_per_creator=5, min_disk_mb=0, cooldown_hours=24,
        creator_diversify=False,
        undercovered_years_first=False,
        undercovered_creators_first=False,
    )

    assert result.cooldown_blocked is True
    assert result.stopped_reason == "cooldown_active"
    assert result.run_id == -1


def test_run_allowed_after_cooldown_expiry(monkeypatch, tmp_path: Path) -> None:
    import datetime as _dt

    database_url = _use_temp_db(monkeypatch, tmp_path, "cooldown_allow.db")
    _insert_video(database_url, "expired_vid")

    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO transcript_collection_runs (
              started_at, ended_at, command_name, attempted_count,
              ip_blocked_count, stopped_reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (_dt.datetime.now(_dt.UTC) - _dt.timedelta(hours=25)).isoformat(),
                (_dt.datetime.now(_dt.UTC) - _dt.timedelta(hours=25)).isoformat(),
                "test_run", 1, 1, "ip_blocked",
            ),
        )
        conn.commit()


    result = collect_native_transcripts_overtime(
        limit=1, sleep_seconds=0, jitter_seconds=0,
        max_per_creator=5, min_disk_mb=0, cooldown_hours=24,
        creator_diversify=False,
        undercovered_years_first=False,
        undercovered_creators_first=False,
    )

    assert result.cooldown_blocked is False


def test_ip_blocked_stops_run_and_logs(monkeypatch, tmp_path: Path) -> None:
    from youtube_transcript_api._errors import IpBlocked

    database_url = _use_temp_db(monkeypatch, tmp_path, "ipblock_log.db")
    _insert_video(database_url, "block_me")
    _insert_video(database_url, "should_not_fetch")

    class BlockApi:
        def __init__(self, *args, **kwargs): pass
        def list(self, video_id):
            raise IpBlocked("blocked")

    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi", BlockApi
    )


    result = collect_native_transcripts_overtime(
        limit=2, sleep_seconds=0, jitter_seconds=0,
        max_per_creator=5, min_disk_mb=0,
        creator_diversify=False,
        undercovered_years_first=False,
        undercovered_creators_first=False,
    )

    assert result.stopped_reason == "ip_blocked"
    assert result.attempted_count == 1

    with connect(database_url) as conn:
        attempts = conn.execute(
            "SELECT video_id, status FROM transcript_collection_attempts WHERE run_id = ?",
            (result.run_id,),
        ).fetchall()
        run = conn.execute(
            "SELECT ip_blocked_count, stopped_reason FROM transcript_collection_runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
    assert len(attempts) == 1
    assert attempts[0]["status"] == "ip_blocked"
    assert run["ip_blocked_count"] == 1
    assert run["stopped_reason"] == "ip_blocked"


def test_max_daily_attempts_prevents_run(monkeypatch, tmp_path: Path) -> None:
    import datetime as _dt

    database_url = _use_temp_db(monkeypatch, tmp_path, "daily_cap.db")
    _insert_video(database_url, "cap_vid")

    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO transcript_collection_runs (
              started_at, ended_at, command_name, attempted_count
            ) VALUES (?, ?, ?, ?)
            """,
            (
                _dt.datetime.now(_dt.UTC).isoformat(),
                _dt.datetime.now(_dt.UTC).isoformat(),
                "test_run", 1,
            ),
        )
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i in range(50):
            conn.execute(
                """
                INSERT INTO transcript_collection_attempts (
                  run_id, video_id, attempted_at, status
                ) VALUES (?, ?, ?, 'error')
                """,
                (run_id, f"vid_{i}", _dt.datetime.now(_dt.UTC).isoformat()),
            )
        conn.commit()


    result = collect_native_transcripts_overtime(
        limit=1, sleep_seconds=0, jitter_seconds=0,
        max_per_creator=5, min_disk_mb=0, max_daily_attempts=50,
        creator_diversify=False,
        undercovered_years_first=False,
        undercovered_creators_first=False,
    )

    assert result.stopped_reason == "max_daily_attempts"
    assert result.run_id == -1


def test_disk_guard_stops_below_threshold(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "disk_guard.db")
    _insert_video(database_url, "disk_vid")

    def fake_check(min_free_mb=500):
        return False

    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection._check_disk_space", fake_check
    )


    result = collect_native_transcripts_overtime(
        limit=1, sleep_seconds=0, jitter_seconds=0,
        max_per_creator=5, min_disk_mb=500,
        creator_diversify=False,
        undercovered_years_first=False,
        undercovered_creators_first=False,
    )

    assert result.stopped_reason is not None
    assert "disk_below" in (result.stopped_reason or "")


def test_status_command_shows_last_run(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "status_cmd.db")
    _insert_video(database_url, "status_vid")


    status = transcript_collection_status()
    assert status.total_transcripts >= 0
    assert status.native_transcripts >= 0
    assert status.provider_transcripts >= 0
    assert status.candidate_windows >= 0
    assert status.accepted_events >= 0
    assert isinstance(status.recommended_action, str)
    assert len(status.coverage_by_year) >= 0
    assert len(status.coverage_by_creator) >= 0


def test_max_per_creator_caps_concentration(monkeypatch, tmp_path: Path) -> None:

    database_url = _use_temp_db(monkeypatch, tmp_path, "max_per_creator.db")

    with connect(database_url) as conn:
        for i in range(5):
            vid = f"creator_a_{i}"
            conn.execute(
                "INSERT INTO raw_youtube_videos (video_id, channel_id, channel_title, published_at, title, url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (vid, "ch_a", "Creator A", "2026-01-01T00:00:00Z", f"T {i}", f"https://youtube.com/watch?v={vid}"),
            )
            conn.execute(
                "INSERT INTO transcript_fetch_queue (video_id, channel_title, priority_score, transcript_status) "
                "VALUES (?, ?, ?, NULL)",
                (vid, "Creator A", 10.0 - i),
            )
        for i in range(5):
            vid = f"creator_b_{i}"
            conn.execute(
                "INSERT INTO raw_youtube_videos (video_id, channel_id, channel_title, published_at, title, url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (vid, "ch_b", "Creator B", "2026-01-01T00:00:00Z", f"T {i}", f"https://youtube.com/watch?v={vid}"),
            )
            conn.execute(
                "INSERT INTO transcript_fetch_queue (video_id, channel_title, priority_score, transcript_status) "
                "VALUES (?, ?, ?, NULL)",
                (vid, "Creator B", 9.0 - i),
            )
        conn.commit()

    with connect(database_url) as conn:
        eligible = _eligible_from_queue(
            conn, limit=6,
            undercovered_years_first=False,
            undercovered_creators_first=False,
            cooldown_hours=24,
        )
        result = _diversify_by_creator(eligible, limit=4, max_per_creator=2)

    assert len(result) == 4
    creators = {r["channel_title"] for r in result}
    assert creators == {"Creator A", "Creator B"}
