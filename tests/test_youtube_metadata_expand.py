from pathlib import Path

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.youtube_metadata_expand import (
    ChannelResolution,
    CreatorSeed,
    _collect_seed_channel_videos,
    _validate_channel_item,
    backfill_youtube_seed_attribution,
    build_transcript_collection_plan,
    exclude_youtube_channel,
    expand_metadata_from_seeds,
    load_creator_seeds,
    load_search_queries,
)


def test_load_creator_seeds(tmp_path: Path) -> None:
    csv_path = tmp_path / "test_seeds.csv"
    csv_path.write_text(
        "creator_name,channel_id,channel_url,handle,creator_category,priority,notes\n"
        "Test Creator,,,@TestCreator,stock_picker,10,test notes\n"
        "News Channel,,,@NewsChannel,news_commentary,2,control channel\n"
    )

    seeds = load_creator_seeds(csv_path)
    assert len(seeds) == 2
    assert seeds[0].creator_name == "Test Creator"
    assert seeds[0].creator_category == "stock_picker"
    assert seeds[0].priority == 10
    assert seeds[0].collection_identifier == "@TestCreator"
    assert seeds[1].creator_category == "news_commentary"
    assert seeds[1].priority == 2


def test_load_search_queries(tmp_path: Path) -> None:
    csv_path = tmp_path / "test_queries.csv"
    csv_path.write_text(
        "query,category,recommended\n"
        "stocks to buy now,stock_pick,yes\n"
        "market analysis stocks,market_commentary,no\n"
    )

    queries = load_search_queries(csv_path)
    assert len(queries) == 2
    assert queries[0].query == "stocks to buy now"
    assert queries[0].recommended is True
    assert queries[1].query == "market analysis stocks"
    assert queries[1].recommended is False


def test_collection_plan_returns_stats(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'plan.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    from finfluencer_alpha.config import get_settings
    get_settings.cache_clear()
    init_db(database_url)

    plan = build_transcript_collection_plan(target_limit=100)
    assert plan.total_videos >= 0
    assert plan.available_transcripts >= 0
    assert plan.pending_transcripts >= 0
    assert isinstance(plan.safe_to_collect, bool)


def test_creator_seed_category_groups() -> None:
    seed_dir = Path(__file__).resolve().parents[2] / "data" / "seeds"
    seed_path = seed_dir / "youtube_creator_seeds.csv"
    if not seed_path.exists():
        return

    seeds = load_creator_seeds(seed_path)
    categories = {s.creator_category for s in seeds}
    assert "stock_picker" in categories
    assert len(seeds) >= 20


def test_suspicious_channel_title_mismatch_is_rejected() -> None:
    seed = CreatorSeed(
        creator_name="Larry Jones",
        channel_id=None,
        channel_url=None,
        handle="@LarryJones",
        creator_category="stock_picker",
        priority=4,
        notes="",
    )
    item = {
        "id": "UCH-skJI_w6vRwHhB_gHNhWQ",
        "snippet": {"title": "Gwyne Gwyne", "customUrl": "@LarryJones"},
    }

    resolution = _validate_channel_item(seed, item)

    assert not resolution.valid
    assert "suspicious channel resolution" in (resolution.warning or "")


def test_explicit_channel_id_is_trusted_over_title_mismatch() -> None:
    seed = CreatorSeed(
        creator_name="Larry Jones",
        channel_id="UCtrusted",
        channel_url=None,
        handle="@WrongHandle",
        creator_category="stock_picker",
        priority=4,
        notes="",
    )
    item = {"id": "UCtrusted", "snippet": {"title": "Different Public Title"}}

    resolution = _validate_channel_item(seed, item, explicit_channel_id="UCtrusted")

    assert resolution.valid
    assert resolution.channel_id == "UCtrusted"


def test_unresolved_creator_is_skipped_safely(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'skip.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    seed_path = tmp_path / "seeds.csv"
    seed_path.write_text(
        "creator_name,channel_id,channel_url,handle,creator_category,priority,notes\n"
        "Larry Jones,,,@LarryJones,stock_picker,4,bad handle\n"
    )

    def fake_resolve(seed: CreatorSeed) -> ChannelResolution:
        return ChannelResolution(seed, None, valid=False, warning="bad resolution")

    def fail_collect(*args: object, **kwargs: object) -> int:
        raise AssertionError("unresolved seed should not collect videos")

    monkeypatch.setattr(
        "finfluencer_alpha.youtube_metadata_expand.resolve_creator_seed_channel",
        fake_resolve,
    )
    monkeypatch.setattr(
        "finfluencer_alpha.youtube_metadata_expand._collect_seed_channel_videos",
        fail_collect,
    )

    result = expand_metadata_from_seeds(seed_path=seed_path, max_videos_per_channel=50)

    assert result.channels_resolved == 0
    assert result.videos_collected == 0
    assert result.unresolved_creators == ("Larry Jones",)


def test_max_videos_per_channel_hard_cap(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'cap.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    seed = CreatorSeed("Test Creator", "UCtest", None, None, "stock_picker", 1, "")
    playlist_calls = 0

    def fake_youtube_get(endpoint: str, params: dict[str, object]) -> dict[str, object]:
        nonlocal playlist_calls
        assert endpoint == "playlistItems"
        playlist_calls += 1
        base = (playlist_calls - 1) * 50
        return {
            "items": [
                {"contentDetails": {"videoId": f"video_{base + index}"}}
                for index in range(50)
            ],
            "nextPageToken": "next",
        }

    def fake_get_videos(video_ids: list[str]) -> list[dict[str, object]]:
        assert len(video_ids) == 200
        return [{"id": video_id, "snippet": {}, "statistics": {}} for video_id in video_ids]

    monkeypatch.setattr(
        "finfluencer_alpha.youtube_metadata_expand.get_channel_uploads_playlist",
        lambda channel_id: "uploads",
    )
    monkeypatch.setattr("finfluencer_alpha.youtube_metadata_expand._youtube_get", fake_youtube_get)
    monkeypatch.setattr("finfluencer_alpha.youtube_metadata_expand.get_videos", fake_get_videos)

    collected = _collect_seed_channel_videos(
        seed,
        "UCtest",
        max_videos_per_channel=200,
        seed_source="youtube_creator_seeds.csv",
    )

    assert collected == 200
    assert playlist_calls == 4


def test_dry_run_estimate_respects_hard_cap(tmp_path: Path) -> None:
    seed_path = tmp_path / "seeds.csv"
    seed_path.write_text(
        "creator_name,channel_id,channel_url,handle,creator_category,priority,notes\n"
        "One,,,@One,stock_picker,1,\n"
        "Two,,,@Two,stock_picker,1,\n"
    )

    result = expand_metadata_from_seeds(
        seed_path=seed_path,
        max_videos_per_channel=200,
        dry_run=True,
    )

    assert result.expected_max_videos == 400
    assert result.estimated_quota_units == 20


def test_backfill_seed_attribution_does_not_overwrite_existing(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'backfill.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    seed_path = tmp_path / "seeds.csv"
    seed_path.write_text(
        "creator_name,channel_id,channel_url,handle,creator_category,priority,notes\n"
        "Seeded Creator,UCseed,,@Seeded,stock_picker,7,\n"
    )
    with connect(database_url) as conn:
        conn.executemany(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url,
              creator_category, seed_source
            )
            VALUES (?, 'UCseed', 'Seeded Creator', '2026-01-01T00:00:00Z',
                    'Video', 'https://youtube.com/watch?v=x', ?, ?)
            """,
            [
                ("blank_attr", None, None),
                ("existing_attr", "existing", "manual"),
            ],
        )
        conn.commit()

    def fake_resolve(seed: CreatorSeed) -> ChannelResolution:
        return ChannelResolution(seed, "UCseed", "Seeded Creator", "@Seeded", True)

    monkeypatch.setattr(
        "finfluencer_alpha.youtube_metadata_expand.resolve_creator_seed_channel",
        fake_resolve,
    )

    result = backfill_youtube_seed_attribution(seed_path=seed_path)

    assert result.rows_updated == 2
    with connect(database_url) as conn:
        rows = {
            row["video_id"]: dict(row)
            for row in conn.execute(
                """
                SELECT video_id, creator_category, seed_source, seed_creator_name,
                       seed_priority
                FROM raw_youtube_videos
                """
            ).fetchall()
        }
    assert rows["blank_attr"]["creator_category"] == "stock_picker"
    assert rows["blank_attr"]["seed_source"] == "seeds.csv"
    assert rows["blank_attr"]["seed_creator_name"] == "Seeded Creator"
    assert rows["blank_attr"]["seed_priority"] == 7
    assert rows["existing_attr"]["creator_category"] == "existing"
    assert rows["existing_attr"]["seed_source"] == "manual"


def test_exclude_youtube_channel_marks_raw_and_queue(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'exclude.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url
            )
            VALUES ('bad_video', 'UCbad', 'Bad Channel', '2026-01-01T00:00:00Z',
                    'Bad resolution', 'https://youtube.com/watch?v=bad_video')
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_fetch_queue (
              video_id, channel_title, published_at, title, transcript_status
            )
            VALUES ('bad_video', 'Bad Channel', '2026-01-01T00:00:00Z',
                    'Bad resolution', NULL)
            """
        )
        conn.commit()

    result = exclude_youtube_channel("UCbad", reason="bad_resolution")

    assert result.rows_excluded == 1
    assert result.queue_rows_marked == 1
    with connect(database_url) as conn:
        raw = conn.execute(
            """
            SELECT excluded_flag, exclusion_reason
            FROM raw_youtube_videos
            WHERE video_id = 'bad_video'
            """
        ).fetchone()
        queue = conn.execute(
            """
            SELECT transcript_status, priority_reason
            FROM transcript_fetch_queue
            WHERE video_id = 'bad_video'
            """
        ).fetchone()
    assert raw["excluded_flag"] == 1
    assert raw["exclusion_reason"] == "bad_resolution"
    assert queue["transcript_status"] == "excluded"
    assert queue["priority_reason"] == "excluded:bad_resolution"
