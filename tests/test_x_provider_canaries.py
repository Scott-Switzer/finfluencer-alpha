from __future__ import annotations

import sys
from pathlib import Path

import pytest

from finfluencer_alpha.x_apify_provider_registry import default_canary_queries
from finfluencer_alpha.x_youtube_pipeline import build_x_actor_input


def test_advanced_search_does_not_wrap_query_with_global_dates() -> None:
    q = default_canary_queries()[0]
    payload = build_x_actor_input(
        "apidojo/tweet-scraper",
        "advanced_search",
        q["query"],
        5,
        date_start=q["since"],
        date_end=q["until"],
    )
    assert payload["searchTerms"][0] == q["query"]
    assert " since:2020-01-01 " not in payload["searchTerms"][0]


def test_dry_run_canary_script_no_apify_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import scripts.run_x_provider_canaries as mod

    out_md = tmp_path / "39.md"
    out_csv = tmp_path / "39.csv"
    monkeypatch.setattr(mod, "CANARY_RESULTS_MD", out_md)
    monkeypatch.setattr(mod, "CANARY_RESULTS_CSV", out_csv)
    monkeypatch.setenv("X_PROVIDER_CANARY_DRY_RUN", "1")
    monkeypatch.setenv("X_PROVIDER_CANARY_PROVIDERS", "apidojo_lite")
    monkeypatch.setenv("X_PROVIDER_CANARY_INCLUDE_SANITY_QUERY", "1")
    monkeypatch.setattr(sys, "argv", ["run_x_provider_canaries.py"])
    mod.main()
    text = out_md.read_text(encoding="utf-8")
    assert "DRY_RUN" in text or "dry-run" in text.lower()
    csv_body = out_csv.read_text(encoding="utf-8")
    assert "SKIPPED_DRY_RUN" in csv_body
    assert "schema_sanity_control" in csv_body
    assert "research_strict" in csv_body


def test_debug_provider_schema_fixture_no_secrets(tmp_path: Path) -> None:
    from scripts import debug_x_provider_dataset_schema as mod

    from finfluencer_alpha.x_apify_provider_registry import (
        default_canary_queries,
        window_bounds_for_canary_entry,
    )

    q = default_canary_queries()[0]
    w0, w1 = window_bounds_for_canary_entry(q)
    rows = [
        {
            "id": "1298374651092837465",
            "text": f"Thoughts on ${q['ticker']} into the week.",
            "created_at": "2021-01-04T16:00:00Z",
            "lang": "en",
        }
    ]
    text = mod.build_report(
        [("fixture:unit", rows, "apidojo/tweet-scraper", q["ticker"], w0, w1)],
        sample=5,
    )
    out = tmp_path / "38.md"
    out.write_text(text, encoding="utf-8")
    assert "Bearer " not in text
    body = out.read_text(encoding="utf-8")
    assert len(body) < 200_000
