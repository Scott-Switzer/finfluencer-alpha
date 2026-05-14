from __future__ import annotations

from datetime import UTC, datetime

import pytest

from finfluencer_alpha.x_apify_provider_registry import (
    CANARY_SEARCH_QUERIES,
    SAMPLE_KIND_BROAD_PROBE,
    SAMPLE_KIND_SANITY,
    all_provider_keys,
    build_canary_actor_input,
    canary_full_search_query,
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


def test_build_canary_actor_input_advanced_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_PROVIDER_CANARY_INCLUDE_APIDOJO_V2", "1")
    q = default_canary_queries()[0]
    payload = build_canary_actor_input("apidojo_v2", q, 5)
    assert "searchTerms" in payload
    assert payload["searchTerms"][0] == q["query"]
    assert payload["start"] == q["since"]
    assert payload["end"] == q["until"]


def test_build_canary_apidojo_lite_shape() -> None:
    q = default_canary_queries()[0]
    p = build_canary_actor_input("apidojo_lite", q, 5, query_variant="strict")
    assert p["searchTerms"] == [q["query"]]
    assert p["sort"] == "Latest"
    assert p["maxItems"] == 5
    assert p["includeSearchTerms"] is True


def test_build_canary_scweet_shape() -> None:
    q = default_canary_queries()[0]
    p = build_canary_actor_input("scweet", q, 5, query_variant="strict")
    assert p["source_mode"] == "search"
    assert p["since"] == q["since"]
    assert p["until"] == q["until"]
    assert p["max_items"] == 5
    assert "from:" in p["search_query"] and "$" + q["ticker"] in p["search_query"]
    assert "since:" not in p["search_query"] and "until:" not in p["search_query"]


def test_strict_query_contains_operators() -> None:
    q = default_canary_queries()[0]
    s = canary_full_search_query(q, variant="strict")
    assert s.startswith("from:")
    assert f"${q['ticker']}" in s
    assert "since:" in s and "until:" in s and "lang:en" in s


def test_broad_query_strips_cashtag_dollar() -> None:
    q = default_canary_queries()[0]
    b = canary_full_search_query(q, variant="broad")
    assert f"${q['ticker']}" not in b
    assert q["ticker"] in b


def test_provider_canary_broad_never_passes_gate() -> None:
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
    ok, reason = provider_canary_passes(m, sample_kind=SAMPLE_KIND_BROAD_PROBE)
    assert not ok
    assert "schema_probe" in reason


def test_provider_canary_sanity_never_passes_gate() -> None:
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
    ok, reason = provider_canary_passes(m, sample_kind=SAMPLE_KIND_SANITY)
    assert not ok
    assert "sanity" in reason.lower()


def test_provider_canary_fails_without_importable_rows() -> None:
    q = default_canary_queries()[0]
    w0, w1 = window_bounds_for_canary_entry(q)
    items = [
        {
            "id": "1298374651092837465",
            "text": "Macro thoughts only — no cashtags here.",
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
    ok, reason = provider_canary_passes(m)
    assert not ok
    assert "importable" in reason


def test_provider_canary_fails_same_day_collapse() -> None:
    q = default_canary_queries()[0]
    w0, w1 = window_bounds_for_canary_entry(q)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    items = [
        {
            "id": "1298374651092837465",
            "text": f"Thoughts on ${q['ticker']} into the week.",
            "created_at": f"{today}T16:00:00Z",
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
    ok, reason = provider_canary_passes(m)
    assert not ok
    assert "collapse" in reason


def test_latest_canary_pass_ignores_non_research_sample_kinds(tmp_path) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    p = tmp_path / "c.csv"
    p.write_text(
        "provider_status,sample_kind,finished_at_utc\n"
        f"PASS,{SAMPLE_KIND_SANITY},{now}\n",
        encoding="utf-8",
    )
    ok, msg = latest_canary_pass_from_csv(p, max_age_hours=24)
    assert not ok
    assert "no_pass" in msg


def test_apidojo_v2_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_PROVIDER_CANARY_INCLUDE_APIDOJO_V2", raising=False)
    assert get_provider("apidojo_v2").canary_enabled is False
    assert get_provider("apidojo_v2").include_in_tiny_default_canary is False


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
        "provider_status,sample_kind,finished_at_utc\n"
        f"PASS,research_strict,{now}\n",
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
