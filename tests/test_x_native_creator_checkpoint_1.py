"""Unit tests for `scripts/x_native_creator_checkpoint_1.py` query planning."""
from __future__ import annotations

import importlib.util
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
