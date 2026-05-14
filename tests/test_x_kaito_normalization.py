"""Kaito / Apify X payload normalization (synthetic fixtures only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from finfluencer_alpha.x_recommendation_classifier import extract_x_ticker_mentions
from finfluencer_alpha.x_youtube_pipeline import (
    _date_window_unix_bounds,
    diagnose_apify_x_item_quality,
    normalize_apify_x_post,
)


def _actor_kwargs() -> dict[str, str]:
    return {
        "actor_id": "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest",
        "key_label": "test",
        "source_type": "search",
        "source_value": "unit",
    }


def kaito_nested_tweet_item() -> dict[str, object]:
    return {
        "tweet": {
            "id": "1700000000000000001",
            "text": "Still long $TSLA into battery day.",
            "created_at": "Wed Oct 11 15:20:45 +0000 2023",
            "lang": "en",
            "author": {"userName": "EvcGuy", "name": "Redacted", "id": "99"},
        }
    }


def test_normalize_apify_x_post_kaito_nested_shape() -> None:
    post = normalize_apify_x_post(kaito_nested_tweet_item(), **_actor_kwargs())
    assert post is not None
    assert post["post_id"] == "1700000000000000001"
    assert post["author_handle"] == "EvcGuy"
    assert "$TSLA" in post["text"]
    assert post["created_at"].startswith("2023-10-11")


def test_cashtag_detection_uses_nested_text_field() -> None:
    post = normalize_apify_x_post(kaito_nested_tweet_item(), **_actor_kwargs())
    assert post is not None
    mentions = extract_x_ticker_mentions(post["text"], strict_cashtag_only=True)
    assert any(m.ticker == "TSLA" and m.cashtag for m in mentions)


def test_created_at_epoch_milliseconds_nested() -> None:
    item = {
        "tweet": {
            "id": "1700000000000000002",
            "text": "Adding $TSLA on weakness.",
            "created_at": "1697040045000",
            "lang": "en",
            "author": {"userName": "DeskA", "id": "1"},
        }
    }
    post = normalize_apify_x_post(item, **_actor_kwargs())
    assert post is not None
    assert post["created_at"].startswith("2023-10-11")


def test_mock_tweet_type_rejected() -> None:
    item = {"type": "mock_tweet", "id": -1, "text": "Pricing placeholder not a tweet.", "lang": "en"}
    assert normalize_apify_x_post(item, **_actor_kwargs()) is None
    diag = diagnose_apify_x_item_quality(item, expected_ticker="TSLA")
    assert diag["reject_reason"] == "mock_or_placeholder"


def test_missing_created_at_rejected() -> None:
    item = {
        "tweet": {
            "id": "1700000000000000003",
            "text": "Only $TSLA chatter.",
            "lang": "en",
            "author": {"userName": "DeskB", "id": "2"},
        }
    }
    assert normalize_apify_x_post(item, **_actor_kwargs()) is None


def test_negative_numeric_post_id_rejected_without_mock_type() -> None:
    item = {"id": -1, "text": "x $TSLA", "created_at": "2024-01-02T12:00:00Z", "lang": "en"}
    assert normalize_apify_x_post(item, **_actor_kwargs()) is None


def test_strict_expected_ticker_and_window_kwargs() -> None:
    since, until = _date_window_unix_bounds("2024-01-01", "2024-01-10")
    item = {"id": "1", "text": "Long $AMD only", "created_at": "2024-01-02T12:00:00Z", "lang": "en"}
    assert (
        normalize_apify_x_post(
            item,
            **_actor_kwargs(),
            expected_ticker="TSLA",
            window_start_unix=since,
            window_end_unix=until,
        )
        is None
    )


def test_flat_full_text_schema_normalizes() -> None:
    item = {
        "id": "8888888888888888888",
        "full_text": "Quick $TSLA note",
        "created_at": "2024-01-02T15:00:00Z",
        "userName": "DeskFlat",
        "lang": "en",
    }
    post = normalize_apify_x_post(
        item,
        actor_id="apidojo/tweet-scraper",
        key_label="t",
        source_type="search",
        source_value="s",
    )
    assert post is not None
    assert post["post_id"] == "8888888888888888888"
    assert "$TSLA" in post["text"]


def test_expected_ticker_strict_cashtag_missing_on_text() -> None:
    """Research gate: expected-ticker cashtag absent even if another cashtag exists."""
    text = "Trimming $AMD into close."
    mentions = extract_x_ticker_mentions(text, strict_cashtag_only=True)
    assert not any(m.ticker == "TSLA" and m.cashtag for m in mentions)


def test_diagnose_outside_event_window() -> None:
    since, until = _date_window_unix_bounds("2024-01-01", "2024-01-10")
    item = {
        "text": "Long $TSLA here.",
        "id": "1",
        "created_at": "2023-06-01T12:00:00Z",
        "lang": "en",
    }
    row = diagnose_apify_x_item_quality(
        item,
        expected_ticker="TSLA",
        window_start_unix=since,
        window_end_unix=until,
    )
    assert row["reject_reason"] == "outside_window"


def test_assert_markdown_has_no_secrets_rejects_bearer_like_strings() -> None:
    from scripts import debug_kaito_dataset_schema as mod

    with pytest.raises(RuntimeError):
        mod.assert_markdown_has_no_secrets("Authorization: Bearer apify_api_abcdefghijklmnopqrstuvwxyz0123456789")


def test_debug_kaito_build_report_no_full_payloads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts import debug_kaito_dataset_schema as mod

    monkeypatch.setattr(mod, "OUT", tmp_path / "36.md")
    rows = [
        {"type": "mock_tweet", "id": -1, "text": "Short placeholder.", "lang": "en"},
        kaito_nested_tweet_item(),
    ]
    md = mod.build_report([("fixture:unit", rows)], sample=5, expected_ticker="TSLA")
    assert "Bearer " not in md
    assert "battery day" not in md.lower()
    assert "mock_tweet" in md
    assert len(md) < 200_000


def test_debug_kaito_main_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts import debug_kaito_dataset_schema as mod

    out = tmp_path / "out.md"
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod, "_first_apify_token", lambda: "dummy-token")
    monkeypatch.setattr(
        mod,
        "_fetch_sample",
        lambda run_id, token, limit: [{"type": "mock_tweet", "id": -1, "text": "placeholder"}],
    )
    monkeypatch.setattr(
        mod,
        "_fetch_actor_run",
        lambda run_id, token: {"defaultDatasetId": "ds_test_1", "status": "SUCCEEDED", "actId": "actor~x"},
    )
    monkeypatch.setattr(sys, "argv", ["debug_kaito_dataset_schema.py", "--run-id", "run_test", "--sample", "2"])
    mod.main()
    text = out.read_text(encoding="utf-8")
    assert "mock_tweet" in text
    assert "ds_test_1" in text
    assert "dummy-token" not in text


def test_debug_fixture_json_load(tmp_path: Path) -> None:
    from scripts import debug_kaito_dataset_schema as mod

    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{"type": "mock_tweet", "id": -1, "text": "x"}]), encoding="utf-8")
    rows = mod._load_fixture_items(path)
    assert len(rows) == 1
