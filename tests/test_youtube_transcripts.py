from pathlib import Path

from youtube_transcript_api._errors import IpBlocked, RequestBlocked, TranscriptsDisabled

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.youtube_transcripts import (
    TooManyRequests,
    TranscriptFetchResult,
    collect_transcripts_for_videos,
    fetch_transcript_for_video,
    store_transcript_result,
)


class FakeTranscript:
    language = "English"
    language_code = "en"
    is_generated = False
    is_translatable = True

    def fetch(self, preserve_formatting: bool = False) -> list[dict[str, object]]:
        assert preserve_formatting is False
        return [
            {"text": "I am buying Nvidia stock", "start": 10.0, "duration": 4.0},
            {"text": "because it has upside", "start": 14.0, "duration": 3.0},
        ]


class FakeTranscriptList:
    def find_manually_created_transcript(self, languages: list[str]) -> FakeTranscript:
        assert languages == ["en"]
        return FakeTranscript()


class FakeTranscriptApi:
    init_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.init_calls.append((args, kwargs))

    def list(self, video_id: str) -> FakeTranscriptList:
        assert video_id == "video123"
        return FakeTranscriptList()


class ErrorTranscriptApi:
    error: Exception = RuntimeError("test error")

    def __init__(self, *args: object, **kwargs: object) -> None:
        assert args == ()
        assert kwargs == {}

    def list(self, video_id: str) -> object:
        raise self.error


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "transcripts.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _insert_video(database_url: str, video_id: str = "video123") -> None:
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
                "channel123",
                "Test Channel",
                "2026-01-01T00:00:00Z",
                "Test video",
                f"https://www.youtube.com/watch?v={video_id}",
            ),
        )
        conn.commit()


def test_schema_creates_transcript_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'schema.db'}"
    init_db(database_url)
    with connect(database_url) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
    assert {
        "youtube_transcripts",
        "youtube_transcript_segments",
        "transcript_candidate_windows",
        "transcript_recommendation_events",
    } <= tables
    assert {
        "idx_youtube_transcript_segments_video",
        "idx_transcript_candidate_windows_ticker",
        "idx_transcript_recommendation_events_video",
    } <= indexes


def test_transcript_dry_run_does_not_mutate_db(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    _insert_video(database_url)

    result = collect_transcripts_for_videos(limit=1, only_candidates=False, dry_run=True)

    with connect(database_url) as conn:
        transcript_count = conn.execute("SELECT COUNT(*) AS n FROM youtube_transcripts").fetchone()
    assert result.dry_run
    assert result.selected_count == 1
    assert transcript_count["n"] == 0


def test_mock_transcript_stores_transcript_and_segments(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi",
        FakeTranscriptApi,
    )
    FakeTranscriptApi.init_calls = []

    result = fetch_transcript_for_video("video123", ["en"])
    with connect(database_url) as conn:
        store_transcript_result(conn, result)
        conn.commit()
        transcript = conn.execute("SELECT * FROM youtube_transcripts").fetchone()
        segment_count = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcript_segments"
        ).fetchone()

    assert FakeTranscriptApi.init_calls == [((), {})]
    assert result.status == "available"
    assert transcript["status"] == "available"
    assert transcript["full_text_sha256"]
    assert segment_count["n"] == 2


def test_transcript_unavailable_status_is_stored(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'disabled.db'}"
    init_db(database_url)
    result = TranscriptFetchResult(
        video_id="video123",
        provider_name="youtube_transcript_api",
        provider_version="1.2.4",
        status="disabled",
        error_type="TranscriptsDisabled",
        error_message="disabled",
    )
    with connect(database_url) as conn:
        store_transcript_result(conn, result)
        conn.commit()
        row = conn.execute("SELECT status, error_type FROM youtube_transcripts").fetchone()
    assert row["status"] == "disabled"
    assert row["error_type"] == "TranscriptsDisabled"


def test_request_blocked_and_ip_blocked_are_stored_and_stop(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "blocked.db")
    _insert_video(database_url, "blocked")
    _insert_video(database_url, "second")

    ErrorTranscriptApi.error = RequestBlocked("blocked")
    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi",
        ErrorTranscriptApi,
    )
    result = collect_transcripts_for_videos(limit=2, only_candidates=False, dry_run=False)

    with connect(database_url) as conn:
        row = conn.execute("SELECT status, error_type FROM youtube_transcripts").fetchone()
    assert result.stopped_reason == "request_blocked"
    assert row["status"] == "request_blocked"
    assert row["error_type"] == "RequestBlocked"

    database_url = _use_temp_db(monkeypatch, tmp_path, "ip_blocked.db")
    _insert_video(database_url, "ipblocked")
    ErrorTranscriptApi.error = IpBlocked("ipblocked")
    result = collect_transcripts_for_videos(limit=1, only_candidates=False, dry_run=False)
    with connect(database_url) as conn:
        row = conn.execute("SELECT status, error_type FROM youtube_transcripts").fetchone()
    assert result.stopped_reason == "ip_blocked"
    assert row["status"] == "ip_blocked"
    assert row["error_type"] == "IpBlocked"


def test_rate_limited_retries_at_most_once(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "rate_limited.db")
    _insert_video(database_url, "limited")
    monkeypatch.setattr("finfluencer_alpha.youtube_transcripts.time.sleep", lambda _: None)

    class RateLimitApi(ErrorTranscriptApi):
        calls = 0

        def list(self, video_id: str) -> object:
            self.__class__.calls += 1
            raise TooManyRequests("limited")

    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi",
        RateLimitApi,
    )

    result = collect_transcripts_for_videos(limit=1, only_candidates=False, dry_run=False)

    assert RateLimitApi.calls == 2
    assert result.status_counts["rate_limited"] == 2
    with connect(database_url) as conn:
        row = conn.execute("SELECT status, error_type FROM youtube_transcripts").fetchone()
    assert row["status"] == "rate_limited"
    assert row["error_type"] == "TooManyRequests"


def test_transcript_disabled_exception_maps_to_disabled(monkeypatch) -> None:
    ErrorTranscriptApi.error = TranscriptsDisabled("video123")
    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi",
        ErrorTranscriptApi,
    )
    result = fetch_transcript_for_video("video123", ["en"])
    assert result.status == "disabled"
    assert result.error_type == "TranscriptsDisabled"


def test_no_proxy_or_cookie_settings_are_exposed() -> None:
    fields = set(type(get_settings()).model_fields)
    joined = " ".join(fields).lower()
    assert "proxy" not in joined
    assert "cookie" not in joined


def test_generated_data_patterns_are_ignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    for pattern in [".env", "data/raw/", "data/exports/", "*.db", "__pycache__/", "*.py[cod]"]:
        assert pattern in gitignore


def test_queue_schema_creates_fetch_queue_table(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'queue_schema.db'}"
    init_db(database_url)
    with connect(database_url) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "transcript_fetch_queue" in tables


def test_build_queue_populates_from_raw_videos(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "queue_populate.db")
    _insert_video(database_url, "video_a")
    _insert_video(database_url, "video_b")

    from finfluencer_alpha.youtube_transcripts import build_transcript_fetch_queue

    with connect(database_url) as conn:
        count = build_transcript_fetch_queue(conn, cooldown_hours=24)

    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT video_id, priority_score, transcript_status FROM transcript_fetch_queue ORDER BY video_id"
        ).fetchall()

    assert count == 2
    assert len(rows) == 2
    assert rows[0]["video_id"] == "video_a"
    assert rows[0]["transcript_status"] is None


def test_queue_skips_already_attempted_on_rebuild(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "queue_rebuild.db")
    _insert_video(database_url, "video_x")

    from finfluencer_alpha.youtube_transcripts import build_transcript_fetch_queue

    with connect(database_url) as conn:
        conn.execute(
            "INSERT INTO transcript_fetch_queue (video_id, priority_score, transcript_status) "
            "VALUES ('video_y', 5.0, 'available')"
        )
        conn.commit()
        count = build_transcript_fetch_queue(conn, cooldown_hours=24)

    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT video_id FROM transcript_fetch_queue ORDER BY video_id"
        ).fetchall()
    assert count >= 1
    assert {"video_id": "video_x"} in [dict(r) for r in rows]


def test_queue_skips_failed_videos_within_cooldown(monkeypatch, tmp_path: Path) -> None:
    import datetime as _dt

    database_url = _use_temp_db(monkeypatch, tmp_path, "queue_cooldown.db")
    _insert_video(database_url, "failed_video")

    future_time = (_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=2)).isoformat()
    with connect(database_url) as conn:
        conn.execute(
            "INSERT INTO transcript_fetch_queue (video_id, priority_score, transcript_status, "
            "attempt_count, next_eligible_attempt_at) VALUES ('failed_video', 10.0, 'ip_blocked', "
            "1, ?)",
            (future_time,),
        )
        conn.commit()

    from finfluencer_alpha.youtube_transcripts import collect_transcripts_from_queue

    result = collect_transcripts_from_queue(limit=1, dry_run=True)
    assert result.selected_count == 0


def test_queue_dry_run_does_not_fetch(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "queue_dry.db")
    _insert_video(database_url, "dry_video")

    from finfluencer_alpha.youtube_transcripts import (
        build_transcript_fetch_queue,
        collect_transcripts_from_queue,
    )

    with connect(database_url) as conn:
        build_transcript_fetch_queue(conn)

    result = collect_transcripts_from_queue(limit=5, dry_run=True)
    assert result.dry_run
    assert result.selected_count >= 1
    with connect(database_url) as conn:
        transcript_count = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcripts"
        ).fetchone()
    assert transcript_count["n"] == 0


def test_queue_prioritizes_recommendation_titles(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "queue_priority.db")

    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, channel_id, channel_title, published_at, title, url)
            VALUES ('low_priority', 'ch1', 'Control Channel', '2026-01-01T00:00:00Z',
                    'Weekly Market Update', 'https://youtube.com/watch?v=low_priority')
            """
        )
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, channel_id, channel_title, published_at, title, url)
            VALUES ('high_priority', 'ch2', 'Stock Moe', '2026-01-02T00:00:00Z',
                    '3 Stocks to BUY NOW', 'https://youtube.com/watch?v=high_priority')
            """
        )
        conn.commit()

    from finfluencer_alpha.youtube_transcripts import build_transcript_fetch_queue

    with connect(database_url) as conn:
        build_transcript_fetch_queue(conn)
        rows = conn.execute(
            "SELECT video_id, priority_score, priority_reason FROM transcript_fetch_queue ORDER BY priority_score DESC"
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["video_id"] == "high_priority"
    assert rows[0]["priority_score"] > rows[1]["priority_score"]


def test_queue_includes_control_videos(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "queue_control.db")

    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, channel_id, channel_title, published_at, title, url)
            VALUES ('control_vid', 'ch1', 'Control Channel', '2026-01-01T00:00:00Z',
                    'Market News Update LIVE', 'https://youtube.com/watch?v=control_vid')
            """
        )
        conn.commit()

    from finfluencer_alpha.youtube_transcripts import build_transcript_fetch_queue

    with connect(database_url) as conn:
        build_transcript_fetch_queue(conn)
        rows = conn.execute(
            "SELECT video_id FROM transcript_fetch_queue"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["video_id"] == "control_vid"


def test_queue_ip_blocked_stores_status_and_stops(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "queue_ip_block.db")
    _insert_video(database_url, "will_block")

    from finfluencer_alpha.youtube_transcripts import (
        build_transcript_fetch_queue,
        collect_transcripts_from_queue,
    )

    with connect(database_url) as conn:
        build_transcript_fetch_queue(conn)

    ErrorTranscriptApi.error = IpBlocked("ipblocked")
    monkeypatch.setattr(
        "finfluencer_alpha.youtube_transcripts.YouTubeTranscriptApi",
        ErrorTranscriptApi,
    )

    result = collect_transcripts_from_queue(
        limit=1, sleep_seconds=0, jitter_seconds=0, stop_on_block=True
    )

    assert result.stopped_reason == "ip_blocked"
    with connect(database_url) as conn:
        queue_row = conn.execute(
            "SELECT transcript_status FROM transcript_fetch_queue WHERE video_id = 'will_block'"
        ).fetchone()
        transcript_row = conn.execute(
            "SELECT status FROM youtube_transcripts WHERE video_id = 'will_block'"
        ).fetchone()
    assert queue_row["transcript_status"] == "ip_blocked"
    assert transcript_row["status"] == "ip_blocked"


def test_classifier_version_is_rules_v2() -> None:
    assert "transcript_rules_v2" in get_settings().transcript_classifier_version
