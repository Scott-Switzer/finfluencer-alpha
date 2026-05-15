from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_autonomous_dry_run_makes_no_paid_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.autonomous_youtube_transcript_expansion")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "QUEUE_CSV", tmp_path / "queue.csv")
    monkeypatch.setattr(mod, "STATUS_MD", tmp_path / "62.md")
    monkeypatch.setattr(mod, "STATUS_CSV", tmp_path / "62.csv")
    monkeypatch.setattr(mod, "FINAL_MD", tmp_path / "63.md")
    monkeypatch.setattr(mod, "FINAL_CSV", tmp_path / "63.csv")
    monkeypatch.setattr(mod, "_queue_size", lambda: 0)
    monkeypatch.setattr(mod, "_accepted_events", lambda: 0)
    monkeypatch.setattr(mod, "_ledger_spend_snapshot", lambda: (0.0, {}))
    monkeypatch.setattr(mod, "_head_commit", lambda: "abc123")
    calls: list[list[str]] = []

    def fake_run(cmd, env=None):  # noqa: ANN001
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(mod, "_run", fake_run)
    monkeypatch.setenv("RUN_YOUTUBE_AUTONOMOUS_EXPANSION", "0")
    monkeypatch.delenv("YOUTUBE_AUTONOMOUS_DRYRUN_ENABLE_APIS", raising=False)
    mod.main()
    assert not any("run_youtube_apify_transcript_overnight.py" in " ".join(c) for c in calls)


def test_autonomous_live_calls_runner_with_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.autonomous_youtube_transcript_expansion")
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "QUEUE_CSV", tmp_path / "queue.csv")
    monkeypatch.setattr(mod, "STATUS_MD", tmp_path / "62.md")
    monkeypatch.setattr(mod, "STATUS_CSV", tmp_path / "62.csv")
    monkeypatch.setattr(mod, "FINAL_MD", tmp_path / "63.md")
    monkeypatch.setattr(mod, "FINAL_CSV", tmp_path / "63.csv")
    monkeypatch.setattr(mod, "_queue_size", lambda: 0)
    monkeypatch.setattr(mod, "_accepted_events", lambda: 0)
    monkeypatch.setattr(mod, "_ledger_spend_snapshot", lambda: (0.0, {}))
    monkeypatch.setattr(mod, "_head_commit", lambda: "abc123")
    monkeypatch.setattr(mod, "_status_from_runner", lambda: {"videos_attempted": "0", "transcripts_imported": "0"})
    calls: list[list[str]] = []

    def fake_run(cmd, env=None):  # noqa: ANN001
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(mod, "_run", fake_run)
    monkeypatch.setenv("RUN_YOUTUBE_AUTONOMOUS_EXPANSION", "1")
    monkeypatch.setenv("YOUTUBE_AUTONOMOUS_MAX_CYCLES", "1")
    mod.main()
    assert any("run_youtube_apify_transcript_overnight.py" in " ".join(c) for c in calls)


def test_dynamic_expansion_respects_search_quota_and_dedup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.expand_youtube_stock_picker_universe")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "61.csv")
    monkeypatch.setattr(mod, "OUT_MD", tmp_path / "61.md")
    monkeypatch.setattr(mod, "SEED_CHANNELS", tmp_path / "seed.csv")
    (tmp_path / "seed.csv").write_text("channel_name,channel_id,channel_url,category\nCreator A,UC123,,stock_picker\n", encoding="utf-8")
    monkeypatch.setattr(mod, "init_db", lambda: None)
    monkeypatch.setattr(mod, "_creator_prior_stats", lambda: {"UC123": {"prior_conversion_rate": 0.2}})
    monkeypatch.setattr(mod, "get_channel_uploads_playlist", lambda cid: "PL123")
    monkeypatch.setattr(mod, "_fetch_playlist_video_ids", lambda channel_id, max_pages: (["v1", "v1", "v2"], 2))
    monkeypatch.setattr(
        mod,
        "get_videos",
        lambda ids: [
            {"id": vid, "snippet": {"channelId": "UC123", "channelTitle": "Creator A", "title": "Best stocks to buy", "description": "NVDA", "publishedAt": "2024-01-01T00:00:00Z"}, "contentDetails": {"duration": "PT10M"}}
            for vid in ids
        ],
    )
    monkeypatch.setattr(mod, "_insert_youtube_videos", lambda *args, **kwargs: 0)

    class _DummyConn:
        def __enter__(self):  # noqa: ANN001
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def commit(self) -> None:
            return None

    monkeypatch.setattr(mod, "connect", lambda: _DummyConn())
    endpoint_calls: list[str] = []
    monkeypatch.setattr(
        mod,
        "_youtube_get",
        lambda endpoint, params: endpoint_calls.append(endpoint) or {"items": []},
    )
    monkeypatch.setenv("RUN_YOUTUBE_AUTONOMOUS_EXPANSION", "1")
    monkeypatch.setenv("YOUTUBE_AUTONOMOUS_SEARCH_QUOTA_CAP", "0")
    monkeypatch.setenv("YOUTUBE_AUTONOMOUS_MAX_NEW_CHANNELS_PER_CYCLE", "1")
    monkeypatch.setenv("YOUTUBE_AUTONOMOUS_ENABLE_SEARCH_DISCOVERY", "1")
    result = mod.run_expansion()
    assert result["new_included_videos"] <= 2
    assert "search" not in endpoint_calls


def test_backup_collection_excludes_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.prepare_runpod_shutdown_backup")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "BACKUPS_DIR", tmp_path / "backups")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "data/exports/overnight_collection").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/exports/overnight_collection/safe.md").write_text("ok", encoding="utf-8")
    files = mod._collect_candidates()
    assert all(p.name != ".env" for p in files)
