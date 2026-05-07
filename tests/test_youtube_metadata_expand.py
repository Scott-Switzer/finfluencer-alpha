from pathlib import Path

from finfluencer_alpha.db import init_db
from finfluencer_alpha.youtube_metadata_expand import (
    build_transcript_collection_plan,
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
