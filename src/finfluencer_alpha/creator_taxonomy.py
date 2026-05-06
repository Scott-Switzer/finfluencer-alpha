from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import CREATOR_TAXONOMY_SEED_PATH
from .db import connect, init_db, upsert_creator

CreatorCategory = Literal[
    "stock_picker",
    "news_attention",
    "analytical_control",
    "meme_retail",
    "macro_commentary",
    "unknown",
]

TAXONOMY_LABELS: set[str] = {
    "stock_picker",
    "news_attention",
    "analytical_control",
    "meme_retail",
    "macro_commentary",
    "unknown",
}


@dataclass(frozen=True)
class CreatorTaxonomyRecord:
    platform: str
    handle_or_channel: str
    initial_category: str
    notes: str


def normalize_category(category: str | None) -> str:
    value = (category or "unknown").strip().lower()
    return value if value in TAXONOMY_LABELS else "unknown"


def load_creator_taxonomy_seed(path: Path | None = None) -> list[CreatorTaxonomyRecord]:
    seed_path = path or CREATOR_TAXONOMY_SEED_PATH
    if not seed_path.exists():
        return []
    records: list[CreatorTaxonomyRecord] = []
    with seed_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            platform = (row.get("platform") or "").strip().lower()
            handle_or_channel = (
                row.get("handle_or_channel")
                or row.get("handle")
                or row.get("channel_name")
                or ""
            ).strip()
            if not platform or not handle_or_channel:
                continue
            records.append(
                CreatorTaxonomyRecord(
                    platform=platform,
                    handle_or_channel=handle_or_channel,
                    initial_category=normalize_category(row.get("initial_category")),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return records


def assign_creator_taxonomy(platform: str, handle_or_channel: str) -> str:
    needle_platform = platform.strip().lower()
    needle = handle_or_channel.strip().lower()
    for record in load_creator_taxonomy_seed():
        if record.platform == needle_platform and record.handle_or_channel.lower() == needle:
            return record.initial_category
    return "unknown"


def seed_creator_taxonomy() -> int:
    init_db()
    records = load_creator_taxonomy_seed()
    with connect() as conn:
        for record in records:
            conn.execute(
                """
                INSERT INTO creator_taxonomy (
                  platform, handle_or_channel, initial_category, notes, source
                )
                VALUES (?, ?, ?, ?, 'seed_csv')
                ON CONFLICT(platform, handle_or_channel) DO UPDATE SET
                  initial_category = excluded.initial_category,
                  notes = excluded.notes,
                  source = excluded.source
                """,
                (
                    record.platform,
                    record.handle_or_channel,
                    record.initial_category,
                    record.notes,
                ),
            )
            upsert_creator(
                conn,
                {
                    "platform": record.platform,
                    "handle": record.handle_or_channel,
                    "display_name": record.handle_or_channel if record.platform == "youtube" else None,
                    "account_url": f"https://x.com/{record.handle_or_channel}"
                    if record.platform == "x"
                    else None,
                    "category": record.initial_category,
                    "source_method": "taxonomy_seed",
                    "include_reason": record.notes,
                },
            )
        conn.commit()
    return len(records)
