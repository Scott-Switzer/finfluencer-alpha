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
RAW_X_COUNTS_DIR = RAW_X_DIR / "counts"
RAW_YOUTUBE_DIR = DATA_DIR / "raw" / "youtube"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"
SEEDS_DIR = DATA_DIR / "seeds"
CREATOR_TAXONOMY_SEED_PATH = SEEDS_DIR / "creator_taxonomy_seed.csv"

X_DISCOVERY_QUERIES = [
    '("$" "buy" OR "buying" OR "long" OR "short" OR "watchlist" OR "undervalued" OR "overvalued") lang:en -is:retweet',
    '("stocks to buy" OR "top stocks" OR "multibagger" OR "10x stock" OR "penny stock") lang:en -is:retweet',
    '("$NVDA" OR "$TSLA" OR "$PLTR" OR "$SOFI" OR "$AMD" OR "$SMCI") lang:en -is:retweet',
]

SEED_X_HANDLES = [
    "realMeetKevin",
    "iamtomnash",
    "jimcramer",
    "unusual_whales",
    "StockMKTNewz",
    "QuiverQuant",
    "WatcherGuru",
    "KobeissiLetter",
    "DeItaone",
    "zerohedge",
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
    x_cost_per_post_read: float = 0.005
    x_max_budget_usd: float = 50.0
    x_max_total_post_reads: int = 10_000
    x_discovery_read_budget: int = 1_000
    x_main_collection_read_budget: int = 6_000
    x_enrichment_read_budget: int = 2_000
    x_buffer_read_budget: int = 1_000
    max_x_reply_reads_per_event: int = 20
    max_x_quote_reads_per_event: int = 20
    max_x_enriched_events: int = 100
    min_creator_stock_pick_count: int = 50
    min_creator_actionable_count: int = 20

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
    for path in [
        RAW_X_DIR,
        RAW_X_COUNTS_DIR,
        RAW_YOUTUBE_DIR,
        INTERIM_DIR,
        PROCESSED_DIR,
        EXPORTS_DIR,
        SEEDS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        x_bearer_token=os.getenv("X_BEARER_TOKEN"),
        x_search_mode=os.getenv("X_SEARCH_MODE", "recent"),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/finfluencer_alpha.db"),
        x_cost_per_post_read=float(os.getenv("X_COST_PER_POST_READ", "0.005")),
        x_max_budget_usd=float(os.getenv("X_MAX_BUDGET_USD", "50")),
        x_max_total_post_reads=int(os.getenv("X_MAX_TOTAL_POST_READS", "10000")),
        x_discovery_read_budget=int(os.getenv("X_DISCOVERY_READ_BUDGET", "1000")),
        x_main_collection_read_budget=int(os.getenv("X_MAIN_COLLECTION_READ_BUDGET", "6000")),
        x_enrichment_read_budget=int(os.getenv("X_ENRICHMENT_READ_BUDGET", "2000")),
        x_buffer_read_budget=int(os.getenv("X_BUFFER_READ_BUDGET", "1000")),
        max_x_reply_reads_per_event=int(os.getenv("MAX_X_REPLY_READS_PER_EVENT", "20")),
        max_x_quote_reads_per_event=int(os.getenv("MAX_X_QUOTE_READS_PER_EVENT", "20")),
        max_x_enriched_events=int(os.getenv("MAX_X_ENRICHED_EVENTS", "100")),
        min_creator_stock_pick_count=int(os.getenv("MIN_CREATOR_STOCK_PICK_COUNT", "50")),
        min_creator_actionable_count=int(os.getenv("MIN_CREATOR_ACTIONABLE_COUNT", "20")),
    )
