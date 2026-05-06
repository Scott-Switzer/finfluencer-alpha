from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_X_DIR = DATA_DIR / "raw" / "x"
RAW_YOUTUBE_DIR = DATA_DIR / "raw" / "youtube"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"

X_DISCOVERY_QUERIES = [
    '("$" "buy" OR "buying" OR "long" OR "short" OR "watchlist" OR "undervalued" OR "overvalued") lang:en -is:retweet',
    '("stocks to buy" OR "top stocks" OR "multibagger" OR "10x stock" OR "penny stock") lang:en -is:retweet',
    '("$NVDA" OR "$TSLA" OR "$PLTR" OR "$SOFI" OR "$AMD" OR "$SMCI") lang:en -is:retweet',
]

SEED_X_HANDLES = [
    "unusual_whales",
    "StockMKTNewz",
    "QuiverQuant",
    "WatcherGuru",
    "KobeissiLetter",
    "DeItaone",
    "zerohedge",
    "jimcramer",
    "MarketRebels",
    "TrendSpider",
    "RampCapitalLLC",
    "litcapital",
    "Gurgavin",
]

YOUTUBE_SEARCH_QUERIES = [
    "finance stocks to buy",
    "best stocks to buy now",
    "penny stocks to buy now",
    "undervalued stocks",
    "AI stocks to buy",
    "stock market portfolio update",
    "growth stocks to buy",
    "top stocks 2025",
    "millionaire stock portfolio",
    "stock watchlist",
]

YOUTUBE_SEED_CHANNELS = [
    "Financial Education",
    "Meet Kevin",
    "ZipTrader",
    "Stock Moe",
    "Tom Nash",
    "Let's Talk Money! with Joseph Hogue",
    "Everything Money",
    "Chicken Genius Singapore",
    "Andrei Jikh",
    "Graham Stephan",
    "The Plain Bagel",
    "Ben Felix",
    "The Stock Dork",
    "Rob Almasi",
    "Brendan Guastaferro",
    "Alpha Status Stocks",
]

FINANCE_KEYWORDS = {
    "stock",
    "stocks",
    "market",
    "markets",
    "equity",
    "equities",
    "shares",
    "buy",
    "sell",
    "short",
    "long",
    "bullish",
    "bearish",
    "calls",
    "puts",
    "watchlist",
    "undervalued",
    "overvalued",
    "portfolio",
    "earnings",
    "revenue",
    "valuation",
    "price target",
    "pt",
}


class Settings(BaseModel):
    x_bearer_token: str | None = Field(default=None)
    x_search_mode: Literal["recent", "all"] = "recent"
    youtube_api_key: str | None = Field(default=None)
    database_url: str = "sqlite:///data/finfluencer_alpha.db"

    @field_validator("x_bearer_token", "youtube_api_key", mode="before")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("x_search_mode", mode="before")
    @classmethod
    def normalize_search_mode(cls, value: str | None) -> str:
        value = (value or "recent").strip().lower()
        if value not in {"recent", "all"}:
            raise ValueError("X_SEARCH_MODE must be either 'recent' or 'all'")
        return value


def ensure_data_dirs() -> None:
    for path in [RAW_X_DIR, RAW_YOUTUBE_DIR, INTERIM_DIR, PROCESSED_DIR, EXPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        x_bearer_token=os.getenv("X_BEARER_TOKEN"),
        x_search_mode=os.getenv("X_SEARCH_MODE", "recent"),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/finfluencer_alpha.db"),
    )
