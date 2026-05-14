"""Unit tests for `scripts/x_native_creator_checkpoint_1.py` query planning."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def checkpoint_mod():
    path = ROOT / "scripts" / "x_native_creator_checkpoint_1.py"
    spec = importlib.util.spec_from_file_location("x_native_creator_checkpoint_1", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["x_native_creator_checkpoint_1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_resolve_x_handle_matches_needles(checkpoint_mod) -> None:
    assert checkpoint_mod.resolve_x_handle("The Plain Bagel") == "ThePlainBagel"
    assert checkpoint_mod.resolve_x_handle("Graham Stephan") == "GrahamStephan"
    assert checkpoint_mod.resolve_x_handle("Everything Money") == "EverythingMoney"
    assert checkpoint_mod.resolve_x_handle("Meet Kevin") == "realMeetKevin"
    assert checkpoint_mod.resolve_x_handle("Parkev Tatevosian, CFA") is None


def test_choose_checkpoint_query_priority(checkpoint_mod) -> None:
    q, typ, handle = checkpoint_mod.choose_checkpoint_query(
        "The Plain Bagel",
        "DIS",
        event_id="e1",
        mention_enabled=True,
        panel_enabled=True,
    )
    assert typ == "x-creator-authored"
    assert q == "from:ThePlainBagel $DIS"
    assert handle == "ThePlainBagel"

    q2, typ2, handle2 = checkpoint_mod.choose_checkpoint_query(
        "Parkev Tatevosian, CFA",
        "NFLX",
        event_id="e2",
        mention_enabled=True,
        panel_enabled=True,
    )
    assert typ2 == "x-creator-mentioned"
    assert q2.startswith('"Parkev Tatevosian" $NFLX')
    assert handle2 == ""

    q3, typ3, handle3 = checkpoint_mod.choose_checkpoint_query(
        "Parkev Tatevosian, CFA",
        "NFLX",
        event_id="e2",
        mention_enabled=False,
        panel_enabled=True,
    )
    assert typ3 == "x-creator-panel"
    assert handle3 in checkpoint_mod.CREATOR_PANEL_HANDLES
    assert q3 == f"from:{handle3} $NFLX"

    q4, typ4, handle4 = checkpoint_mod.choose_checkpoint_query(
        "Parkev Tatevosian, CFA",
        "NFLX",
        event_id="e2",
        mention_enabled=False,
        panel_enabled=False,
    )
    assert typ4 == "ticker-only-control"
    assert q4 == "$NFLX"
    assert handle4 == ""


def test_mention_phrase_rejects_single_token(checkpoint_mod) -> None:
    assert checkpoint_mod.mention_phrase_for_search("HyperChange") is None
    assert checkpoint_mod.creator_mention_search("HyperChange", "TSLA") is None


def test_prioritize_checkpoint_events_prefers_mapped(checkpoint_mod) -> None:
    events = [
        {"creator": "Kenan Grace", "event_date_utc": "2026-04-09", "event_id": "1", "ticker": "META"},
        {"creator": "The Plain Bagel", "event_date_utc": "2022-11-18", "event_id": "2", "ticker": "DIS"},
        {"creator": "Graham Stephan", "event_date_utc": "2024-01-01", "event_id": "3", "ticker": "NVDA"},
    ]
    ordered = checkpoint_mod.prioritize_checkpoint_events(events)
    assert [e["creator"] for e in ordered][:2] == ["The Plain Bagel", "Graham Stephan"]
    assert ordered[-1]["creator"] == "Kenan Grace"


def test_panel_handle_stable(checkpoint_mod) -> None:
    a = checkpoint_mod.panel_handle_for_event("e", "Kenan Grace", "META")
    b = checkpoint_mod.panel_handle_for_event("e", "Kenan Grace", "META")
    assert a == b
    assert a in checkpoint_mod.CREATOR_PANEL_HANDLES


def test_mapped_creator_outside_legacy_head_slice_is_selectable(checkpoint_mod) -> None:
    """Regression: pool must not be capped to max_runs×3 before mapped-first sort."""
    rows: list[dict[str, str]] = []
    for i in range(100):
        rows.append(
            {
                "creator": "Kenan Grace",
                "event_id": str(i),
                "ticker": "META",
                "event_date_utc": "2024-01-01",
                "video_id": "",
            }
        )
    rows.append(
        {
            "creator": "Graham Stephan",
            "event_id": "mapped1",
            "ticker": "NVDA",
            "event_date_utc": "2024-01-02",
            "video_id": "v1",
        }
    )
    candidates = checkpoint_mod.select_checkpoint_candidates(
        rows,
        max_runs=5,
        require_mapped_for_pool=False,
        mention_enabled=True,
        panel_enabled=True,
    )
    assert candidates[0]["youtube_creator"] == "Graham Stephan"
    assert candidates[0]["query_type"] == "x-creator-authored"


def test_select_dedupes_identical_search_window(checkpoint_mod) -> None:
    rows = [
        {
            "creator": "The Plain Bagel",
            "event_id": "a",
            "ticker": "TSLA",
            "event_date_utc": "2020-02-21",
            "video_id": "x",
        },
        {
            "creator": "The Plain Bagel",
            "event_id": "b",
            "ticker": "TSLA",
            "event_date_utc": "2020-02-21",
            "video_id": "y",
        },
    ]
    c = checkpoint_mod.select_checkpoint_candidates(
        rows,
        max_runs=5,
        require_mapped_for_pool=False,
        mention_enabled=True,
        panel_enabled=True,
    )
    assert len(c) == 1


def test_no_ticker_only_when_mapped_and_mention_panel_disabled(checkpoint_mod) -> None:
    rows = [
        {
            "creator": "Graham Stephan",
            "event_id": "1",
            "ticker": "NVDA",
            "event_date_utc": "2024-01-01",
            "video_id": "",
        }
    ]
    c = checkpoint_mod.select_checkpoint_candidates(
        rows,
        max_runs=3,
        require_mapped_for_pool=False,
        mention_enabled=False,
        panel_enabled=False,
    )
    assert len(c) == 1
    assert c[0]["query_type"] == "x-creator-authored"


def test_dry_run_does_not_call_apify(monkeypatch: pytest.MonkeyPatch, checkpoint_mod) -> None:
    calls: list[str] = []

    def boom(**_kwargs: object) -> None:
        calls.append("apify")
        raise AssertionError("Apify must not run in dry-run mode")

    monkeypatch.setenv("X_CHECKPOINT_DRY_RUN", "1")
    monkeypatch.setenv("X_CHECKPOINT_WRITE_DEBUG_MD", "0")
    monkeypatch.setattr(checkpoint_mod, "run_single_x_apify_source", boom)
    rows = [
        {
            "creator": "Graham Stephan",
            "event_id": "1",
            "ticker": "NVDA",
            "event_date_utc": "2024-01-01",
            "video_id": "",
        }
    ]
    monkeypatch.setattr(checkpoint_mod, "discover_events", lambda _n: ("unit", rows))
    checkpoint_mod.main()
    assert calls == []


def test_zero_import_fixture_summary_counts(checkpoint_mod) -> None:
    from finfluencer_alpha.x_youtube_pipeline import (
        _date_window_unix_bounds,
        summarize_apify_checkpoint_items,
    )

    since, until = _date_window_unix_bounds("2024-01-01", "2024-01-10")
    summary = summarize_apify_checkpoint_items(
        checkpoint_mod._DIAGNOSTIC_FIXTURE_ITEMS,
        expected_ticker="NVDA",
        window_start_unix=since,
        window_end_unix=until,
    )
    counts = summary["reject_reason_counts"]
    assert counts["missing_text"] >= 1
    assert counts["normalized_ok"] >= 1
    assert "items" in summary


def test_debug_markdown_has_no_raw_high_entropy_payloads(
    monkeypatch: pytest.MonkeyPatch, checkpoint_mod, tmp_path: Path
) -> None:
    monkeypatch.setattr(checkpoint_mod, "DEBUG_MD_PATH", tmp_path / "35.md")
    report = {"dry_run": True, "event_source": "unit"}
    checkpoint_mod.write_zero_import_audit_file(
        dry_run_report=report,
        fixture_summary=checkpoint_mod.fixture_diagnostic_summary(),
    )
    text = (tmp_path / "35.md").read_text(encoding="utf-8")
    assert "Bearer " not in text
    assert "api_key" not in text.lower()
    assert len(text) < 500_000


def test_schema_summary_excludes_full_text_payloads() -> None:
    from finfluencer_alpha.x_youtube_pipeline import diagnose_apify_x_item_quality

    row = diagnose_apify_x_item_quality(
        {"text": "X" * 5000, "id": "1", "created_at": "2024-01-02T12:00:00Z", "lang": "en"},
        expected_ticker="TSLA",
    )
    assert row["text_char_len"] == 5000
    assert "XXXX" not in json.dumps(row)
