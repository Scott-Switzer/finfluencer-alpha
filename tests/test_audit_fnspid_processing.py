from __future__ import annotations

from datetime import date

from scripts import audit_fnspid_processing as audit
from scripts.audit_fnspid_processing import EventRec, window_sensitivity_from_spine


def test_symbol_variants_meta_fb() -> None:
    assert "FB" in audit.symbol_variants("META")
    assert "META" in audit.symbol_variants("FB")


def test_window_sensitivity_empty_spine(monkeypatch) -> None:
    monkeypatch.setattr(audit, "SPINE", audit.OUT / "nonexistent_spine.csv")
    events = {1: EventRec(event_id=1, ticker="AAPL", event_date=date(2020, 6, 15))}
    df = window_sensitivity_from_spine(events)
    assert "status" in df.columns or "window" in df.columns
