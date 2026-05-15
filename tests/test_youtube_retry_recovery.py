from __future__ import annotations

import importlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from finfluencer_alpha.apify_key_manager import ApifyKeyManager


def _seed_retry_queue_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE raw_youtube_videos (
          video_id TEXT PRIMARY KEY,
          url TEXT,
          channel_title TEXT,
          title TEXT,
          description TEXT,
          published_at TEXT,
          raw_json TEXT,
          excluded_flag INTEGER DEFAULT 0
        );
        CREATE TABLE youtube_transcripts (
          video_id TEXT,
          status TEXT,
          error_type TEXT,
          error_message TEXT,
          retrieved_at TEXT,
          collected_at TEXT
        );
        CREATE TABLE transcript_candidate_windows (
          candidate_window_id INTEGER PRIMARY KEY,
          video_id TEXT,
          accepted_event_flag INTEGER
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO raw_youtube_videos(video_id,url,channel_title,title,description,published_at,raw_json,excluded_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        [
            (
                "video000001A",
                "https://www.youtube.com/watch?v=video000001A",
                "Creator A",
                "Top stocks to buy now",
                "NVDA and TSLA deep dive",
                "2025-01-01T00:00:00Z",
                '{"contentDetails":{"duration":"PT12M00S"}}',
            ),
            (
                "video000001B",
                "https://www.youtube.com/watch?v=video000001B",
                "Creator B",
                "General market update",
                "macro",
                "2025-01-02T00:00:00Z",
                '{"contentDetails":{"duration":"PT6M00S"}}',
            ),
            (
                "video000001C",
                "https://www.youtube.com/watch?v=video000001C",
                "Creator C",
                "Old no caption",
                "no transcript likely",
                "2020-01-01T00:00:00Z",
                '{"contentDetails":{"duration":"PT4H00M00S"}}',
            ),
        ],
    )
    conn.execute(
        """
        INSERT INTO youtube_transcripts(video_id,status,error_type,error_message,retrieved_at,collected_at)
        VALUES ('video000001B','available','','','2025-01-03T00:00:00Z','2025-01-03T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO youtube_transcripts(video_id,status,error_type,error_message,retrieved_at,collected_at)
        VALUES ('video000001C','disabled','TranscriptNotFound','subtitles disabled','2025-01-04T00:00:00Z','2025-01-04T00:00:00Z')
        """
    )
    conn.execute(
        "INSERT INTO transcript_candidate_windows(video_id,accepted_event_flag) VALUES ('video000001A',1)"
    )
    conn.commit()
    conn.close()


@dataclass
class _FakeResult:
    available_count: int
    skipped_existing_count: int = 0
    cost_usd: float = 0.01


def test_retry_queue_excludes_permanent_and_success_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = importlib.import_module("scripts.build_youtube_transcript_retry_queue")
    db = tmp_path / "db.sqlite"
    _seed_retry_queue_db(db)
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "71.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "71.md")
    rows, _ = mod.build_retry_queue()
    ids = {row["video_id"] for row in rows}
    assert "video000001A" in ids
    assert "video000001B" not in ids
    assert "video000001C" not in ids


def test_retry_queue_prioritizes_stock_pick_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = importlib.import_module("scripts.build_youtube_transcript_retry_queue")
    db = tmp_path / "db.sqlite"
    _seed_retry_queue_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO raw_youtube_videos(video_id,url,channel_title,title,description,published_at,raw_json,excluded_flag)
        VALUES ('video000001D','https://www.youtube.com/watch?v=video000001D','Creator D','weekly vlog','nothing about stocks','2025-01-01T00:00:00Z','{"contentDetails":{"duration":"PT10M00S"}}',0)
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "71.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "71.md")
    rows, _ = mod.build_retry_queue()
    assert rows[0]["video_id"] == "video000001A"


def test_retry_runner_dry_run_makes_no_paid_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_retry_recovery")
    queue = tmp_path / "71.csv"
    queue.write_text("video_id\nvideo000001A\n", encoding="utf-8")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "LIVE_MD", tmp_path / "72.md")
    monkeypatch.setattr(mod, "LIVE_CSV", tmp_path / "72.csv")
    monkeypatch.setattr(mod, "FINAL_MD", tmp_path / "73.md")
    monkeypatch.setattr(mod, "FINAL_CSV", tmp_path / "73.csv")
    monkeypatch.setenv("YOUTUBE_RETRY_QUEUE_PATH", str(queue))
    monkeypatch.setenv("RUN_YOUTUBE_APIFY_RETRY_RECOVERY", "0")
    monkeypatch.setenv("APIFY_TOKEN", "SECRET_TOKEN")
    called = {"n": 0}
    monkeypatch.setattr(mod, "collect_apify_transcripts", lambda **kwargs: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(mod, "_status_map", lambda _ids: {})
    monkeypatch.setattr(mod, "_get_transcript_count", lambda: 0)
    monkeypatch.setattr(mod, "_get_queue_remaining", lambda _p: 1)
    mod.main()
    assert called["n"] == 0
    assert "SECRET_TOKEN" not in (tmp_path / "72.md").read_text(encoding="utf-8")
    assert "SECRET_TOKEN" not in (tmp_path / "73.md").read_text(encoding="utf-8")


def test_retry_runner_english_fallback_languages_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_retry_recovery")
    queue = tmp_path / "71.csv"
    queue.write_text("video_id\nvideo000001A\n", encoding="utf-8")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "LIVE_MD", tmp_path / "72.md")
    monkeypatch.setattr(mod, "LIVE_CSV", tmp_path / "72.csv")
    monkeypatch.setattr(mod, "FINAL_MD", tmp_path / "73.md")
    monkeypatch.setattr(mod, "FINAL_CSV", tmp_path / "73.csv")
    monkeypatch.setenv("YOUTUBE_RETRY_QUEUE_PATH", str(queue))
    monkeypatch.setenv("RUN_YOUTUBE_APIFY_RETRY_RECOVERY", "1")
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setenv("YOUTUBE_APIFY_RETRY_MAX_VIDEOS", "1")
    captured: dict[str, object] = {}

    def fake_collect(**kwargs):
        captured["languages"] = kwargs["languages"]
        return _FakeResult(available_count=1, skipped_existing_count=0, cost_usd=0.01)

    monkeypatch.setattr(mod, "collect_apify_transcripts", fake_collect)
    monkeypatch.setattr(mod, "_status_map", lambda _ids: {})
    monkeypatch.setattr(mod, "_get_transcript_count", lambda: 0)
    monkeypatch.setattr(mod, "_get_queue_remaining", lambda _p: 0)
    manager = ApifyKeyManager.from_env({"APIFY_TOKEN": "tok"}, ledger_path=tmp_path / "ledger.csv")
    monkeypatch.setattr(mod.ApifyKeyManager, "from_env", lambda: manager)
    mod.main()
    assert captured["languages"] == ["en", "en-US", "en-GB"]


def test_retry_runner_ipblocked_is_transient_backoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_retry_recovery")
    queue = tmp_path / "71.csv"
    queue.write_text("video_id\nvideo000001A\nvideo000001B\n", encoding="utf-8")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "LIVE_MD", tmp_path / "72.md")
    monkeypatch.setattr(mod, "LIVE_CSV", tmp_path / "72.csv")
    monkeypatch.setattr(mod, "FINAL_MD", tmp_path / "73.md")
    monkeypatch.setattr(mod, "FINAL_CSV", tmp_path / "73.csv")
    monkeypatch.setenv("YOUTUBE_RETRY_QUEUE_PATH", str(queue))
    monkeypatch.setenv("RUN_YOUTUBE_APIFY_RETRY_RECOVERY", "1")
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setenv("YOUTUBE_APIFY_RETRY_BATCH_SIZE_INITIAL", "1")
    monkeypatch.setenv("YOUTUBE_APIFY_RETRY_BATCH_SIZE_MAX", "2")
    monkeypatch.setenv("YOUTUBE_APIFY_RETRY_CAP_USD", "0.03")
    attempts = {"n": 0}

    def fake_collect(**kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("IpBlocked: proxy blocked")
        return _FakeResult(available_count=1, cost_usd=0.02)

    monkeypatch.setattr(mod, "collect_apify_transcripts", fake_collect)
    monkeypatch.setattr(mod, "_status_map", lambda _ids: {})
    monkeypatch.setattr(mod, "_get_transcript_count", lambda: 0)
    monkeypatch.setattr(mod, "_get_queue_remaining", lambda _p: 0)
    manager = ApifyKeyManager.from_env({"APIFY_TOKEN": "tok"}, ledger_path=tmp_path / "ledger.csv")
    monkeypatch.setattr(mod.ApifyKeyManager, "from_env", lambda: manager)
    mod.main()
    text = (tmp_path / "72.md").read_text(encoding="utf-8")
    assert "IpBlocked" in text
    assert "STOP_REPEATED_PROVIDER_FAILURE" not in text


def test_retry_runner_batch_ladder_increase_and_decrease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_retry_recovery")
    queue = tmp_path / "71.csv"
    queue.write_text("video_id\n" + "\n".join(f"video{i:09d}" for i in range(1, 131)) + "\n", encoding="utf-8")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "LIVE_MD", tmp_path / "72.md")
    monkeypatch.setattr(mod, "LIVE_CSV", tmp_path / "72.csv")
    monkeypatch.setattr(mod, "FINAL_MD", tmp_path / "73.md")
    monkeypatch.setattr(mod, "FINAL_CSV", tmp_path / "73.csv")
    monkeypatch.setenv("YOUTUBE_RETRY_QUEUE_PATH", str(queue))
    monkeypatch.setenv("RUN_YOUTUBE_APIFY_RETRY_RECOVERY", "1")
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setenv("YOUTUBE_APIFY_RETRY_BATCH_SIZE_INITIAL", "20")
    monkeypatch.setenv("YOUTUBE_APIFY_RETRY_BATCH_SIZE_MAX", "50")
    monkeypatch.setenv("YOUTUBE_APIFY_RETRY_CAP_USD", "1.0")
    calls: list[int] = []

    def fake_collect(**kwargs):
        calls.append(int(kwargs["batch_size"]))
        if len(calls) <= 3:
            return _FakeResult(available_count=len(kwargs["video_ids"]), cost_usd=0.01)
        return _FakeResult(available_count=0, cost_usd=0.01)

    monkeypatch.setattr(mod, "collect_apify_transcripts", fake_collect)
    monkeypatch.setattr(mod, "_status_map", lambda _ids: {})
    monkeypatch.setattr(mod, "_get_transcript_count", lambda: 0)
    monkeypatch.setattr(mod, "_get_queue_remaining", lambda _p: 0)
    manager = ApifyKeyManager.from_env({"APIFY_TOKEN": "tok"}, ledger_path=tmp_path / "ledger.csv")
    monkeypatch.setattr(mod.ApifyKeyManager, "from_env", lambda: manager)
    mod.main()
    assert 50 in calls
    # after a low success batch, the runner should downshift
    assert 10 in calls


def test_retry_runner_classifies_schema_auth_credit() -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_retry_recovery")
    assert mod._classify_stop("HTTP 400 invalid-input: Field input.urls is required") == "STOP_SCHEMA_ERROR"
    assert mod._classify_stop("HTTP 401 unauthorized") == "STOP_AUTH_ERROR"
    assert mod._classify_stop("platform-feature-disabled monthly usage hard limit exceeded") == "STOP_CREDIT_EXHAUSTED"
    assert not mod._is_provider_level_failure("TranscriptNotFound: subtitles are disabled")
    assert not mod._is_provider_level_failure("AgeRestricted")
    assert not mod._is_provider_level_failure("VideoUnavailable")
