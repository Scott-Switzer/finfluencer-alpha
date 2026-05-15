from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE raw_youtube_videos (
          video_id TEXT PRIMARY KEY,
          channel_title TEXT,
          published_at TEXT,
          title TEXT,
          description TEXT,
          url TEXT,
          duration_seconds INTEGER,
          excluded_flag INTEGER DEFAULT 0,
          seed_source TEXT
        );
        CREATE TABLE youtube_transcripts (
          video_id TEXT,
          status TEXT,
          full_text TEXT,
          language TEXT,
          is_generated INTEGER,
          segment_count INTEGER,
          error_type TEXT,
          error_message TEXT,
          retrieved_at TEXT,
          provider_actor_id TEXT
        );
        CREATE TABLE transcript_candidate_windows (
          candidate_window_id INTEGER PRIMARY KEY,
          video_id TEXT,
          accepted_event_flag INTEGER
        );
        CREATE TABLE transcript_recommendation_events (
          transcript_event_id INTEGER PRIMARY KEY,
          video_id TEXT,
          ticker TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO raw_youtube_videos
        (video_id, channel_title, published_at, title, description, url, duration_seconds, excluded_flag, seed_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'seed')
        """,
        [
            ("video000001A", "Creator A", "2021-01-05T00:00:00Z", "TSLA stock buy", "price target", "https://youtube.com/watch?v=video000001A", 600),
            ("video000001B", "Creator B", "2021-01-06T00:00:00Z", "market update", "macro", "https://youtube.com/watch?v=video000001B", 45),
            ("video000001C", "Creator A", "2021-01-07T00:00:00Z", "AAPL analysis", "earnings", "https://youtube.com/watch?v=video000001C", 900),
        ],
    )
    conn.execute(
        "INSERT INTO youtube_transcripts(video_id,status,full_text,retrieved_at) VALUES ('video000001B','available','already','2021-01-07T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO transcript_candidate_windows(video_id,accepted_event_flag) VALUES ('video000001A',1)"
    )
    conn.execute(
        "INSERT INTO transcript_recommendation_events(video_id,ticker) VALUES ('video000001A','TSLA')"
    )
    conn.commit()
    conn.close()


def test_queue_excludes_success_and_scores_candidate_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.build_youtube_transcript_expansion_queue")
    db = tmp_path / "db.sqlite"
    _seed_db(db)
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "50.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "50.md")
    monkeypatch.setattr(mod, "SEED_CSV", tmp_path / "seeds.csv")
    (tmp_path / "seeds.csv").write_text("channel_name,category\nCreator A,stock_picker\nCreator B,macro_commentary\n", encoding="utf-8")
    rows, _ = mod.build_queue()
    assert all(r.video_id != "video000001B" for r in rows)
    assert rows[0].video_id == "video000001A"


def test_planner_does_not_print_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    mod = importlib.import_module("scripts.plan_youtube_apify_transcript_drain")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "51.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "51.md")
    monkeypatch.setattr(mod, "_actor_meta", lambda actor_id, token: {"inputSchema": {"properties": {"videoUrls": {"type": "array"}}}})
    monkeypatch.setenv("APIFY_TOKEN_1", "SECRET_TOKEN_VALUE")
    mod.main()
    out = capsys.readouterr().out
    assert "SECRET_TOKEN_VALUE" not in out


def test_canary_dry_run_no_paid_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.canary_youtube_apify_transcript_provider")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "52.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "52.md")
    monkeypatch.setattr(mod, "QUEUE_CSV", tmp_path / "50.csv")
    monkeypatch.setattr(mod, "PLAN_CSV", tmp_path / "51.csv")
    (tmp_path / "50.csv").write_text("video_id\nvideo000001A\n", encoding="utf-8")
    (tmp_path / "51.csv").write_text("actor_id,selected\nsupreme_coder/youtube-transcript-scraper,1\n", encoding="utf-8")
    monkeypatch.setenv("RUN_YOUTUBE_APIFY_TRANSCRIPT_CANARY", "0")
    called = {"n": 0}
    monkeypatch.setattr(mod, "collect_apify_transcripts", lambda **kwargs: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(mod, "_transcript_snapshot", lambda _ids: {})
    mod.main()
    assert called["n"] == 0


def test_overnight_dry_run_no_paid_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_overnight")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "QUEUE_CSV", tmp_path / "50.csv")
    monkeypatch.setattr(mod, "LIVE_MD", tmp_path / "53.md")
    monkeypatch.setattr(mod, "CHECKPOINT_JSON", tmp_path / "53.json")
    (tmp_path / "50.csv").write_text("video_id\nvideo000001A\n", encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_APIFY_SELECTED_PROVIDER", "supreme_coder/youtube-transcript-scraper")
    monkeypatch.setenv("RUN_YOUTUBE_APIFY_OVERNIGHT", "0")
    called = {"n": 0}
    monkeypatch.setattr(mod, "collect_apify_transcripts", lambda **kwargs: called.__setitem__("n", called["n"] + 1))
    mod.main()
    assert called["n"] == 0


def test_overnight_requires_selected_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_overnight")
    monkeypatch.delenv("YOUTUBE_APIFY_SELECTED_PROVIDER", raising=False)
    with pytest.raises(SystemExit):
        mod.main()


def test_queue_dedup_ids_in_loader(tmp_path: Path) -> None:
    mod = importlib.import_module("scripts.run_youtube_apify_transcript_overnight")
    p = tmp_path / "q.csv"
    p.write_text("video_id\nabc\nabc\ndef\n", encoding="utf-8")
    # call actual by patching module constant
    mod.QUEUE_CSV = p
    assert mod._load_queue(10) == ["abc", "def"]
    assert mod._load_queue(0) == ["abc", "def"]


def test_error_classification_permanent_vs_transient() -> None:
    mod = importlib.import_module("scripts.canary_youtube_apify_transcript_provider")
    assert mod._map_error("unavailable", "", "") == "VideoUnavailable"
    assert mod._map_error("ip_blocked", "", "") == "IpBlocked"
    assert mod._map_error("", "", "HTTP 400 invalid-input: Field input.urls is required") == "SchemaMismatch"


def test_raw_transcript_paths_ignored_in_git() -> None:
    ignore = Path(".gitignore").read_text(encoding="utf-8")
    assert "data/raw/" in ignore


def test_live_canary_failure_still_writes_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.canary_youtube_apify_transcript_provider")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "52.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "52.md")
    monkeypatch.setattr(mod, "DECISION_MD", tmp_path / "56.md")
    monkeypatch.setattr(mod, "QUEUE_CSV", tmp_path / "50.csv")
    monkeypatch.setattr(mod, "PLAN_CSV", tmp_path / "51.csv")
    (tmp_path / "50.csv").write_text("video_id\nvideo000001A\n", encoding="utf-8")
    (tmp_path / "51.csv").write_text("actor_id,selected\nsupreme_coder/youtube-transcript-scraper,1\n", encoding="utf-8")
    monkeypatch.setenv("RUN_YOUTUBE_APIFY_TRANSCRIPT_CANARY", "1")
    monkeypatch.setattr(
        mod,
        "collect_apify_transcripts",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 400 invalid-input: Field input.urls is required")),
    )
    monkeypatch.setattr(mod, "_transcript_snapshot", lambda _ids: {})
    mod.main()
    assert (tmp_path / "52.csv").exists()
    assert (tmp_path / "52.md").exists()
    assert (tmp_path / "56.md").exists()
    assert "SchemaMismatch" in (tmp_path / "52.md").read_text(encoding="utf-8")
    assert "FAIL" in (tmp_path / "56.md").read_text(encoding="utf-8")


def test_queue_exhaustive_mode_includes_non_priority_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = importlib.import_module("scripts.build_youtube_transcript_expansion_queue")
    db = tmp_path / "db.sqlite"
    _seed_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO raw_youtube_videos(video_id,channel_title,published_at,title,description,url,duration_seconds,excluded_flag,seed_source)
        VALUES ('video000001D','Creator Z','2021-01-08T00:00:00Z','general market chat','','https://youtube.com/watch?v=video000001D',200,0,'')
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "50.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "50.md")
    monkeypatch.setattr(mod, "SEED_CSV", tmp_path / "seeds.csv")
    (tmp_path / "seeds.csv").write_text("channel_name,category\nCreator A,stock_picker\n", encoding="utf-8")
    monkeypatch.setattr(mod, "EXPANSION_MODE", "priority_only")
    rows_priority, _ = mod.build_queue()
    monkeypatch.setattr(mod, "EXPANSION_MODE", "exhaustive")
    rows_exhaustive, _ = mod.build_queue()
    ids_priority = {r.video_id for r in rows_priority}
    ids_exhaustive = {r.video_id for r in rows_exhaustive}
    assert "video000001D" not in ids_priority
    assert "video000001D" in ids_exhaustive
