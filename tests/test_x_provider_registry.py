from __future__ import annotations

from datetime import UTC, datetime

import pytest

from finfluencer_alpha.x_apify_provider_registry import (
    CANARY_SEARCH_QUERIES,
    all_provider_keys,
    build_canary_actor_input,
    default_canary_queries,
    get_provider,
    latest_canary_pass_from_csv,
    overnight_x_collection_canary_gate_ok,
    provider_canary_passes,
    summarize_provider_canary_rows,
    window_bounds_for_canary_entry,
)


def test_registry_lists_all_configured_providers() -> None:
    keys = all_provider_keys()
    for needle in (
        "kaito_cheapest",
        "xquik",
        "scrapebadger",
        "scweet",
        "apidojo_v2",
        "apidojo_lite",
    ):
        assert needle in keys
    assert get_provider("apidojo_v2").actor_id == "apidojo/tweet-scraper"


def test_canary_queries_use_audited_handles_only() -> None:
    for row in CANARY_SEARCH_QUERIES:
        assert row["query"].startswith("from:")
        assert "since:" in row["query"]
        assert "$" in row["query"]
        assert row["handle_audit"].startswith("CHANNEL_X")


def test_build_canary_actor_input_advanced_search() -> None:
    q = default_canary_queries()[0]
    payload = build_canary_actor_input("apidojo_v2", q, 5)
    assert "searchTerms" in payload
    assert payload["searchTerms"][0] == q["query"]
    assert payload["start"] == q["since"]
    assert payload["end"] == q["until"]


def test_summarize_passes_on_synthetic_real_rows() -> None:
    q = default_canary_queries()[0]
    w0, w1 = window_bounds_for_canary_entry(q)
    items = [
        {
            "id": "1298374651092837465",
            "text": f"Thoughts on ${q['ticker']} into the week.",
            "created_at": "2021-01-04T16:00:00Z",
            "lang": "en",
        }
    ]
    m = summarize_provider_canary_rows(
        items,
        actor_id="apidojo/tweet-scraper",
        expected_ticker=q["ticker"],
        window_start_unix=w0,
        window_end_unix=w1,
    )
    assert m["non_mock_rows"] == 1
    assert m["importable_rows"] == 1
    ok, reason = provider_canary_passes(m)
    assert ok, reason


def test_provider_canary_fails_mock_only() -> None:
    items = [{"type": "mock_tweet", "id": -1, "text": "placeholder", "lang": "en"}]
    q = default_canary_queries()[0]
    w0, w1 = window_bounds_for_canary_entry(q)
    m = summarize_provider_canary_rows(
        items,
        actor_id="kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest",
        expected_ticker=q["ticker"],
        window_start_unix=w0,
        window_end_unix=w1,
    )
    ok, reason = provider_canary_passes(m)
    assert not ok
    assert "mock" in reason.lower()


def test_latest_canary_pass_reads_csv(tmp_path) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    p = tmp_path / "c.csv"
    p.write_text(
        "provider_status,finished_at_utc\n"
        f"PASS,{now}\n",
        encoding="utf-8",
    )
    ok, msg = latest_canary_pass_from_csv(p, max_age_hours=24)
    assert ok
    assert "pass_within_window" in msg


def test_overnight_gate_bypass_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_REQUIRE_PROVIDER_CANARY_PASS", "0")
    ok, msg = overnight_x_collection_canary_gate_ok()
    assert ok
    assert "bypass" in msg
