from pathlib import Path

from typer.testing import CliRunner

from finfluencer_alpha.cli import app
from finfluencer_alpha.config import (
    CREATOR_CATEGORY_LABELS,
    YOUTUBE_SEED_CHANNELS,
    YoutubeSeedChannel,
    load_youtube_seed_rows,
)
from finfluencer_alpha.validation import youtube_seed_consistency_errors
from finfluencer_alpha.youtube_quota import estimate_youtube_history_seed_quota


def _row(name: str, category: str = "stock_picker") -> YoutubeSeedChannel:
    return YoutubeSeedChannel(
        channel_name=name,
        channel_id="",
        handle="",
        category=category,
        expected_role="primary_candidate",
        verification_status="unverified",
        notes="test",
    )


def test_canonical_youtube_seed_file_is_consistent_with_runtime_and_taxonomy() -> None:
    rows = load_youtube_seed_rows()
    assert rows
    assert youtube_seed_consistency_errors() == []
    assert set(YOUTUBE_SEED_CHANNELS) == {row.collection_identifier for row in rows}
    assert {row.category for row in rows} <= CREATOR_CATEGORY_LABELS


def test_youtube_seed_validation_catches_config_seed_missing_from_csv() -> None:
    errors = youtube_seed_consistency_errors(
        config_seed_channels=["Financial Education", "Missing Channel"],
        youtube_seed_rows=[_row("Financial Education")],
        taxonomy_records=[],
    )
    assert any("config YouTube seed 'Missing Channel'" in error for error in errors)


def test_youtube_seed_validation_catches_taxonomy_seed_missing_from_csv() -> None:
    errors = youtube_seed_consistency_errors(
        config_seed_channels=["Financial Education"],
        youtube_seed_rows=[_row("Financial Education")],
        taxonomy_records=[
            {
                "platform": "youtube",
                "channel_name": "Missing Taxonomy Channel",
                "initial_category": "stock_picker",
            }
        ],
    )
    assert any("Missing Taxonomy Channel" in error for error in errors)


def test_youtube_seed_validation_catches_blank_and_invalid_categories() -> None:
    errors = youtube_seed_consistency_errors(
        config_seed_channels=[],
        youtube_seed_rows=[_row("Blank Category", ""), _row("Bad Category", "not_a_category")],
        taxonomy_records=[],
    )
    assert any("Blank Category: missing category" in error for error in errors)
    assert any("Bad Category: invalid category 'not_a_category'" in error for error in errors)


def test_youtube_history_quota_estimate_for_resolved_ids_and_unresolved_names() -> None:
    resolved = estimate_youtube_history_seed_quota(
        ["UCabc", "UCdef", "UCghi"],
        max_channels=3,
        max_pages=1,
    )
    assert resolved.channels_list_calls == 3
    assert resolved.playlist_items_list_calls == 3
    assert resolved.videos_list_calls == 3
    assert resolved.search_list_calls == 0
    assert resolved.total_quota_units == 9

    unresolved = estimate_youtube_history_seed_quota(
        ["Financial Education", "Meet Kevin", "Tom Nash"],
        max_channels=3,
        max_pages=1,
    )
    assert unresolved.channels_list_calls == 3
    assert unresolved.playlist_items_list_calls == 3
    assert unresolved.videos_list_calls == 3
    assert unresolved.search_list_calls == 3
    assert unresolved.total_quota_units == 309


def test_youtube_history_quota_estimate_for_handle_resolution() -> None:
    estimate = estimate_youtube_history_seed_quota(["@example"], max_channels=1, max_pages=2)
    assert estimate.channels_list_calls == 2
    assert estimate.playlist_items_list_calls == 2
    assert estimate.videos_list_calls == 1
    assert estimate.search_list_calls == 0
    assert estimate.total_quota_units == 5


def test_collect_youtube_history_supports_max_pages_and_dry_run(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "collect-youtube-history-seeds",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-06",
            "--max-channels",
            "3",
            "--max-pages",
            "1",
            "--dry-run",
        ],
        env={"DATABASE_URL": f"sqlite:///{tmp_path / 'dry_run.db'}"},
    )
    assert result.exit_code == 0
    assert "search.list=3" in result.output
    assert "total=309 units" in result.output
    assert "Dry run only; no YouTube API calls were made." in result.output
