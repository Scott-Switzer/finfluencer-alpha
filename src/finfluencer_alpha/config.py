from __future__ import annotations

import csv
import os
from dataclasses import dataclass
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
IMPORTS_DIR = DATA_DIR / "imports"
SEEDS_DIR = DATA_DIR / "seeds"
CREATOR_TAXONOMY_SEED_PATH = SEEDS_DIR / "creator_taxonomy_seed.csv"
YOUTUBE_SEED_CHANNELS_PATH = SEEDS_DIR / "youtube_seed_channels.csv"

CREATOR_CATEGORY_LABELS: frozenset[str] = frozenset(
    {
        "stock_picker",
        "news_attention",
        "analytical_control",
        "meme_retail",
        "macro_commentary",
        "unknown",
    }
)

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

@dataclass(frozen=True)
class YoutubeSeedChannel:
    channel_name: str
    channel_id: str
    handle: str
    channel_url: str
    category: str
    expected_role: str
    verified_status: str
    manual_review_notes: str

    @property
    def collection_identifier(self) -> str:
        return self.channel_id or self.handle or self.channel_url or self.channel_name


def _clean_seed_value(value: str | None) -> str:
    return (value or "").strip()


def load_youtube_seed_rows(path: Path | None = None) -> list[YoutubeSeedChannel]:
    seed_path = path or YOUTUBE_SEED_CHANNELS_PATH
    if not seed_path.exists():
        raise FileNotFoundError(
            f"YouTube seed file is required as the canonical source: {seed_path}"
        )
    with seed_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [
            YoutubeSeedChannel(
                channel_name=_clean_seed_value(row.get("channel_name")),
                channel_id=_clean_seed_value(row.get("channel_id")),
                handle=_clean_seed_value(row.get("handle")),
                channel_url=_clean_seed_value(row.get("channel_url")),
                category=_clean_seed_value(row.get("category")),
                expected_role=_clean_seed_value(row.get("expected_role")),
                verified_status=_clean_seed_value(
                    row.get("verified_status") or row.get("verification_status")
                ),
                manual_review_notes=_clean_seed_value(
                    row.get("manual_review_notes") or row.get("notes")
                ),
            )
            for row in reader
        ]
    errors = validate_youtube_seed_rows(rows)
    if errors:
        raise ValueError("Invalid YouTube seed file: " + "; ".join(errors))
    return rows


def validate_youtube_seed_rows(rows: list[YoutubeSeedChannel]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        label = row.channel_name or row.channel_id or row.handle or row.channel_url or f"row {index}"
        if not row.collection_identifier:
            errors.append(f"{label}: missing channel_name, channel_id, handle, or channel_url")
        if not row.category:
            errors.append(f"{label}: missing category")
        elif row.category not in CREATOR_CATEGORY_LABELS:
            errors.append(f"{label}: invalid category '{row.category}'")
        normalized = row.channel_name.lower()
        if normalized:
            if normalized in seen:
                errors.append(f"{label}: duplicate channel_name")
            seen.add(normalized)
    return errors


def load_youtube_seed_channel_identifiers(path: Path | None = None) -> list[str]:
    return [row.collection_identifier for row in load_youtube_seed_rows(path)]


YOUTUBE_SEED_CHANNELS = load_youtube_seed_channel_identifiers()

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
    youtubetranscript_dev_api_key: str | None = Field(default=None)
    transcriptapi_key: str | None = Field(default=None)
    apify_token: str | None = Field(default=None)
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
    youtube_transcript_provider: str = "youtube_transcript_api"
    youtube_transcript_languages: str = "en"
    youtube_transcript_preserve_formatting: bool = False
    youtube_transcript_max_videos_per_run: int = 50
    transcript_classifier_version: str = "transcript_rules_v2"
    max_blocked_errors_per_run: int = 1
    max_rate_limit_errors_per_run: int = 3
    transcript_queue_sleep_seconds: float = 3.0
    transcript_queue_jitter_seconds: float = 1.0
    transcript_queue_max_live_fetches: int = 20
    transcript_queue_cooldown_hours: int = 24

    @field_validator(
        "x_bearer_token",
        "youtube_api_key",
        "youtubetranscript_dev_api_key",
        "transcriptapi_key",
        "apify_token",
        mode="before",
    )
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

    @field_validator("youtube_transcript_provider", "youtube_transcript_languages", mode="before")
    @classmethod
    def normalize_transcript_strings(cls, value: str | None) -> str:
        return (value or "").strip()

    @property
    def youtube_transcript_language_list(self) -> list[str]:
        languages = [
            language.strip()
            for language in self.youtube_transcript_languages.split(",")
            if language.strip()
        ]
        return languages or ["en"]


def ensure_data_dirs() -> None:
    for path in [
        RAW_X_DIR,
        RAW_X_COUNTS_DIR,
        RAW_YOUTUBE_DIR,
        INTERIM_DIR,
        PROCESSED_DIR,
        EXPORTS_DIR,
        IMPORTS_DIR,
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
        youtubetranscript_dev_api_key=os.getenv("YOUTUBETRANSCRIPT_DEV_API_KEY"),
        transcriptapi_key=os.getenv("TRANSCRIPTAPI_KEY"),
        apify_token=os.getenv("APIFY_TOKEN"),
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
        youtube_transcript_provider=os.getenv(
            "YOUTUBE_TRANSCRIPT_PROVIDER", "youtube_transcript_api"
        ),
        youtube_transcript_languages=os.getenv("YOUTUBE_TRANSCRIPT_LANGUAGES", "en"),
        youtube_transcript_preserve_formatting=os.getenv(
            "YOUTUBE_TRANSCRIPT_PRESERVE_FORMATTING", "false"
        )
        .strip()
        .lower()
        in {"1", "true", "yes", "y", "on"},
        youtube_transcript_max_videos_per_run=int(
            os.getenv("YOUTUBE_TRANSCRIPT_MAX_VIDEOS_PER_RUN", "50")
        ),
        transcript_classifier_version=os.getenv(
            "TRANSCRIPT_CLASSIFIER_VERSION", "transcript_rules_v2"
        ),
        max_blocked_errors_per_run=int(os.getenv("MAX_BLOCKED_ERRORS_PER_RUN", "1")),
        max_rate_limit_errors_per_run=int(os.getenv("MAX_RATE_LIMIT_ERRORS_PER_RUN", "3")),
        transcript_queue_sleep_seconds=float(
            os.getenv("TRANSCRIPT_QUEUE_SLEEP_SECONDS", "3.0")
        ),
        transcript_queue_jitter_seconds=float(
            os.getenv("TRANSCRIPT_QUEUE_JITTER_SECONDS", "1.0")
        ),
        transcript_queue_max_live_fetches=int(
            os.getenv("TRANSCRIPT_QUEUE_MAX_LIVE_FETCHES", "20")
        ),
        transcript_queue_cooldown_hours=int(
            os.getenv("TRANSCRIPT_QUEUE_COOLDOWN_HOURS", "24")
        ),
    )


def clear_settings_cache() -> None:
    get_settings.cache_clear()
