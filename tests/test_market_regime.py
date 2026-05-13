from pathlib import Path

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.market_regime import (
    backfill_market_regimes,
    market_regime_for_timestamp,
)


def test_market_regime_windows_are_deterministic() -> None:
    assert market_regime_for_timestamp("2020-02-20T00:00:00Z") == "covid_crash"
    assert market_regime_for_timestamp("2020-03-24T00:00:00Z") == "covid_rebound"
    assert market_regime_for_timestamp("2021-06-01T00:00:00Z") == "meme_spac_bubble"
    assert market_regime_for_timestamp("2022-09-13T00:00:00Z") == "rate_hike_selloff"
    assert market_regime_for_timestamp("2024-05-01T00:00:00Z") == "ai_rally"
    assert market_regime_for_timestamp("2026-05-12T00:00:00Z") == "recent_market"
    assert market_regime_for_timestamp("2019-12-31T00:00:00Z") is None


def test_backfill_market_regimes_updates_metadata(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'market_regime.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title
            )
            VALUES ('video000001', 'chan1', 'Creator', '2025-04-01T00:00:00Z', 'Title')
            """
        )
        conn.commit()

    updated = backfill_market_regimes()
    assert updated == 1
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT market_regime FROM raw_youtube_videos WHERE video_id = 'video000001'"
        ).fetchone()
    assert row["market_regime"] == "recent_market"
