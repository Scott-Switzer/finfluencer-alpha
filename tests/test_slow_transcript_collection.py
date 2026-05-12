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
    refresh_slow_youtube_transcript_queue,
)
from finfluencer_alpha.transcript_proxy import (
    ProxyConfig,
    proxymode_summary,
    redact_credentials,
    resolve_proxy_config,
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


def test_plan_queue_excludes_permanent_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)
    from finfluencer_alpha.db import connect

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
            VALUES (?, ?, ?, ?)
            """,
            ("perm_vid1", "Title 1", "Creator A", "2021-06-01T12:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
            VALUES (?, ?, ?, ?)
            """,
            ("perm_vid2", "Title 2", "Creator B", "2021-06-02T12:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
            VALUES (?, ?, ?, ?)
            """,
            ("perm_vid3", "Title 3", "Creator C", "2021-06-03T12:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("perm_vid1", "disabled", "youtube_transcript_api"),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("perm_vid2", "unavailable", "youtube_transcript_api"),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("perm_vid3", "no_language", "youtube_transcript_api"),
        )
        conn.commit()

    result = plan_slow_youtube_transcript_queue(
        start_year=2021,
        end_year=2021,
        max_videos=10,
        exclude_permanent_failures=True,
        output_path=tmp_path / "queue.csv",
        summary_md_path=tmp_path / "queue.md",
    )
    assert result.queue_size == 0


def test_plan_queue_includes_permanent_failures_when_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)
    from finfluencer_alpha.db import connect

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
            VALUES (?, ?, ?, ?)
            """,
            ("perm_vid1", "Title 1", "Creator A", "2021-06-01T12:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("perm_vid1", "disabled", "youtube_transcript_api"),
        )
        conn.commit()

    result = plan_slow_youtube_transcript_queue(
        start_year=2021,
        end_year=2021,
        max_videos=10,
        exclude_permanent_failures=False,
        output_path=tmp_path / "queue.csv",
        summary_md_path=tmp_path / "queue.md",
    )
    assert result.queue_size == 1
    queue = list(csv.DictReader((tmp_path / "queue.csv").open()))
    assert queue[0]["video_id"] == "perm_vid1"


def test_refresh_queue_excludes_available_and_permanent_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_test_db(monkeypatch, tmp_path)
    from finfluencer_alpha.db import connect

    with connect() as conn:
        for vid, status in [
            ("avail_vid", "available"),
            ("disabled_vid", "disabled"),
            ("missing_vid", "missing"),
        ]:
            conn.execute(
                """
                INSERT INTO raw_youtube_videos (video_id, title, channel_title, published_at)
                VALUES (?, ?, ?, ?)
                """,
                (vid, f"Title {vid}", "Creator", "2021-06-01T12:00:00Z"),
            )
            if status != "missing":
                conn.execute(
                    """
                    INSERT INTO youtube_transcripts (video_id, status, provider_name)
                    VALUES (?, ?, ?)
                    """,
                    (vid, status, "youtube_transcript_api"),
                )
        conn.commit()

    result = refresh_slow_youtube_transcript_queue(
        output_path=tmp_path / "queue.csv",
        summary_md_path=tmp_path / "queue.md",
    )
    assert result.queue_size == 1
    queue = list(csv.DictReader((tmp_path / "queue.csv").open()))
    assert queue[0]["video_id"] == "missing_vid"


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


class TestProxyResolution:
    def test_auto_mode_selects_no_proxy_when_no_env_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
        monkeypatch.delenv("WEBSHARE_PROXY_PASSWORD", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTP_PROXY", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTPS_PROXY", raising=False)
        config = resolve_proxy_config(mode="auto")
        assert config.mode == "no-proxy"

    def test_auto_mode_selects_webshare_when_env_vars_exist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "testuser")
        monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "testpass")
        monkeypatch.delenv("YT_TRANSCRIPT_HTTP_PROXY", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTPS_PROXY", raising=False)
        config = resolve_proxy_config(mode="auto")
        assert config.mode == "webshare"
        assert config.webshare_username == "testuser"
        assert config.webshare_password == "testpass"

    def test_auto_mode_selects_generic_when_webshare_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
        monkeypatch.delenv("WEBSHARE_PROXY_PASSWORD", raising=False)
        monkeypatch.setenv("YT_TRANSCRIPT_HTTP_PROXY", "http://proxy:8080")
        monkeypatch.delenv("YT_TRANSCRIPT_HTTPS_PROXY", raising=False)
        config = resolve_proxy_config(mode="auto")
        assert config.mode == "generic"
        assert config.http_proxy == "http://proxy:8080"

    def test_explicit_webshare_mode_errors_without_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
        monkeypatch.delenv("WEBSHARE_PROXY_PASSWORD", raising=False)
        with pytest.raises(ValueError, match="requires WEBSHARE"):
            resolve_proxy_config(mode="webshare")

    def test_explicit_generic_mode_errors_without_proxy_urls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("YT_TRANSCRIPT_HTTP_PROXY", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTPS_PROXY", raising=False)
        with pytest.raises(ValueError, match="requires YT_TRANSCRIPT"):
            resolve_proxy_config(mode="generic")

    def test_explicit_no_proxy_mode_selected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "testuser")
        monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "testpass")
        config = resolve_proxy_config(mode="no-proxy")
        assert config.mode == "no-proxy"


class TestProxyRedaction:
    def test_redact_credentials_hides_url_credentials(self) -> None:
        text = "http://user:password@proxy.example.com:8080"
        redacted = redact_credentials(text)
        assert "user:password" not in redacted
        assert "***:***" in redacted

    def test_redact_credentials_hides_env_var_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "secret-user")
        monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "secret-pass")
        text = "Using credentials secret-user and secret-pass"
        redacted = redact_credentials(text)
        assert "secret-user" not in redacted
        assert "secret-pass" not in redacted

    def test_redact_credentials_returns_empty_for_empty_input(self) -> None:
        assert redact_credentials("") == ""
        assert redact_credentials(None) is None  # type: ignore[arg-type]

    def test_proxymode_summary_does_not_contain_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "secret-user")
        monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "secret-pass")
        config = ProxyConfig(
            mode="webshare", webshare_username="secret-user", webshare_password="secret-pass"
        )
        summary = proxymode_summary(config)
        assert "secret-user" not in summary
        assert "secret-pass" not in summary

    def test_proxymode_summary_generic_redacts_urls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = ProxyConfig(
            mode="generic",
            http_proxy="http://u:p@proxy:8080",
            https_proxy="https://u2:p2@proxy:8443",
        )
        summary = proxymode_summary(config)
        assert "u:p" not in summary
        assert "u2:p2" not in summary
        assert "***:***" in summary


class TestProxyCollectionIntegration:
    def test_dry_run_resolves_proxy_without_fetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
        monkeypatch.delenv("WEBSHARE_PROXY_PASSWORD", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTP_PROXY", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTPS_PROXY", raising=False)

        _write_csv(
            tmp_path / "queue.csv",
            [
                {
                    "video_id": "proxydry_vid1",
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
            proxy_mode="auto",
            output_summary_csv=tmp_path / "summary.csv",
            output_summary_md=tmp_path / "summary.md",
        )
        assert result.attempted == 0
        assert result.stop_reason == "dry_run"

    def test_webshare_mode_propagates_to_summary(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "testuser")
        monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "testpass")
        monkeypatch.delenv("YT_TRANSCRIPT_HTTP_PROXY", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTPS_PROXY", raising=False)

        _write_csv(
            tmp_path / "queue.csv",
            [
                {
                    "video_id": "wssum_vid1",
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
                status="available",
            )

        import finfluencer_alpha.slow_transcript_collection as sc

        monkeypatch.setattr(sc, "fetch_transcript_for_video", fake_fetch)
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
        _clear_settings_cache()
        from finfluencer_alpha.db import init_db

        init_db(database_url=f"sqlite:///{tmp_path / 'test.db'}")

        result = collect_youtube_transcripts_slow(
            input_path=tmp_path / "queue.csv",
            max_videos=10,
            delay_seconds=0,
            confirm_run=True,
            proxy_mode="webshare",
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            output_summary_csv=tmp_path / "summary.csv",
            output_summary_md=tmp_path / "summary.md",
        )
        assert result.attempted >= 0
        summary_md = (tmp_path / "summary.md").read_text()
        assert "Proxy mode requested: webshare" in summary_md
        assert "webshare" in summary_md

    def test_unknown_proxy_mode_falls_back_to_no_proxy(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
        monkeypatch.delenv("WEBSHARE_PROXY_PASSWORD", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTP_PROXY", raising=False)
        monkeypatch.delenv("YT_TRANSCRIPT_HTTPS_PROXY", raising=False)

        _write_csv(
            tmp_path / "queue.csv",
            [
                {
                    "video_id": "badmode_vid1",
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
            proxy_mode="invalid_mode",
            output_summary_csv=tmp_path / "summary.csv",
            output_summary_md=tmp_path / "summary.md",
        )
        assert result.attempted == 0
        assert result.stop_reason == "dry_run"
