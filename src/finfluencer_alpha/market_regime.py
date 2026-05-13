from __future__ import annotations

from dataclasses import dataclass

from .db import connect, init_db


@dataclass(frozen=True)
class MarketRegimeWindow:
    label: str
    start_date: str
    end_date: str


MARKET_REGIME_WINDOWS = (
    MarketRegimeWindow("covid_crash", "2020-02-20", "2020-03-23"),
    MarketRegimeWindow("covid_rebound", "2020-03-24", "2020-12-31"),
    MarketRegimeWindow("meme_spac_bubble", "2021-01-01", "2021-12-31"),
    MarketRegimeWindow("rate_hike_selloff", "2022-01-01", "2022-12-31"),
    MarketRegimeWindow("ai_rally", "2023-01-01", "2024-12-31"),
    MarketRegimeWindow("recent_market", "2025-01-01", "2026-05-12"),
)


def market_regime_for_timestamp(value: object) -> str | None:
    text = str(value or "").strip()
    date_value = text[:10]
    if len(date_value) != 10:
        return None
    for window in MARKET_REGIME_WINDOWS:
        if window.start_date <= date_value <= window.end_date:
            return window.label
    return None


def backfill_market_regimes() -> int:
    init_db()
    updated = 0
    with connect() as conn:
        rows = conn.execute(
            "SELECT video_id, published_at, market_regime FROM raw_youtube_videos"
        ).fetchall()
        for row in rows:
            regime = market_regime_for_timestamp(row["published_at"])
            if regime == row["market_regime"]:
                continue
            conn.execute(
                "UPDATE raw_youtube_videos SET market_regime = ? WHERE video_id = ?",
                (regime, row["video_id"]),
            )
            updated += 1
        conn.commit()
    return updated
