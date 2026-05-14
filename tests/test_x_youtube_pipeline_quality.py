import pytest

from finfluencer_alpha import x_youtube_pipeline as pipeline
from finfluencer_alpha.config import clear_settings_cache
from finfluencer_alpha.db import connect


def _normalized_post(raw_created_at: object) -> dict[str, object] | None:
    return pipeline.normalize_apify_x_post(
        {"id": "123", "text": "Buying $TSLA here", "created_at": raw_created_at, "lang": "en"},
        actor_id="actor/test",
        key_label="test_key",
        source_type="profile",
        source_value="tester",
    )


def test_x_timestamp_parsing_requires_explicit_year() -> None:
    legacy = _normalized_post("Thu May 14 12:34:56 +0000 2020")
    epoch_ms = _normalized_post("1589459696000")

    assert legacy is not None
    assert legacy["created_at"] == "2020-05-14T12:34:56Z"
    assert epoch_ms is not None
    assert epoch_ms["created_at"] == "2020-05-14T12:34:56Z"
    assert _normalized_post("May 14") is None
    assert _normalized_post("2h") is None


def test_x_date_window_converts_to_unix_utc_bounds() -> None:
    assert pipeline._date_window_unix_bounds("2020-08-01", "2020-08-07") == (
        1596240000,
        1596844799,
    )


def test_kaito_input_uses_unix_time_schema_fields() -> None:
    actor_input = pipeline.build_x_actor_input(
        "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest",
        "cashtag",
        "TSLA",
        20,
        date_start="2020-08-01",
        date_end="2020-08-07",
    )

    assert actor_input["searchTerms"] == [
        "$TSLA lang:en -filter:retweets since_time:1596240000 until_time:1596844799"
    ]
    assert actor_input["since_time"] == "1596240000"
    assert actor_input["until_time"] == "1596844799"
    assert actor_input["queryType"] == "Latest"
    assert "queries" not in actor_input
    assert "startDate" not in actor_input
    assert "endDate" not in actor_input
    assert " since:" not in actor_input["searchTerms"][0]
    assert " until:" not in actor_input["searchTerms"][0]


def test_x_historical_date_filter_flag_defaults_unproven(monkeypatch) -> None:
    monkeypatch.delenv(pipeline.X_APIFY_HISTORICAL_DATE_FILTER_PROVEN_ENV, raising=False)

    assert not pipeline._env_flag(pipeline.X_APIFY_HISTORICAL_DATE_FILTER_PROVEN_ENV)


def test_same_day_only_date_coverage_guard() -> None:
    coverage = pipeline.analyze_x_date_coverage(
        ["2026-05-14T01:00:00Z", "2026-05-14T22:00:00Z", "May 14"]
    )

    assert coverage.same_day_only
    assert coverage.malformed_rows == 1
    with pytest.raises(RuntimeError, match="same-day-only X data"):
        pipeline.assert_x_event_study_date_quality(coverage)
    pipeline.assert_x_event_study_date_quality(coverage, allow_diagnostic=True)


def test_import_events_use_strict_cashtags_and_seed_universe(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'x_quality.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    clear_settings_cache()

    posts = [
        {
            "post_id": "1",
            "author_handle": "tester",
            "text": "Buying $TSLA and $NVDA here",
            "created_at": "2024-01-02T12:00:00Z",
            "normalized_text_hash": "hash1",
        },
        {
            "post_id": "2",
            "author_handle": "tester",
            "text": "Buying TSLA stock here",
            "created_at": "2024-01-03T12:00:00Z",
            "normalized_text_hash": "hash2",
        },
    ]

    imported, duplicates, _, events = pipeline.import_normalized_x_posts(
        posts,
        event_seed_tickers={"TSLA"},
        strict_cashtag_events=True,
    )

    assert (imported, duplicates, events) == (2, 0, 1)
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT ticker, source_method FROM x_recommendation_events ORDER BY event_id"
        ).fetchall()
    assert [(row["ticker"], row["source_method"]) for row in rows] == [
        ("TSLA", "x_rules_v1_strict_cashtag_seed")
    ]
    clear_settings_cache()
