from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .config import (
    YoutubeSeedChannel,
    get_settings,
    load_youtube_seed_rows,
    validate_youtube_seed_rows,
)


def missing_api_keys() -> list[str]:
    settings = get_settings()
    missing: list[str] = []
    if not settings.x_bearer_token:
        missing.append("X_BEARER_TOKEN")
    if not settings.youtube_api_key:
        missing.append("YOUTUBE_API_KEY")
    return missing


def api_key_status() -> dict[str, bool]:
    settings = get_settings()
    return {
        "x": bool(settings.x_bearer_token),
        "youtube": bool(settings.youtube_api_key),
    }


def _record_value(record: Any, key: str) -> str:
    if isinstance(record, dict):
        return str(record.get(key) or "").strip()
    return str(getattr(record, key, "") or "").strip()


def _taxonomy_youtube_name(record: Any) -> str:
    if isinstance(record, dict):
        return str(
            record.get("handle_or_channel")
            or record.get("channel_name")
            or record.get("handle")
            or ""
        ).strip()
    return str(getattr(record, "handle_or_channel", "") or "").strip()


def _canonical_identifiers(rows: Iterable[YoutubeSeedChannel]) -> set[str]:
    identifiers: set[str] = set()
    for row in rows:
        for value in [
            row.channel_name,
            row.channel_id,
            row.handle,
            row.channel_url,
            row.collection_identifier,
        ]:
            if value:
                identifiers.add(value.lower())
    return identifiers


def youtube_seed_consistency_errors(
    config_seed_channels: list[str] | None = None,
    youtube_seed_rows: list[YoutubeSeedChannel] | None = None,
    taxonomy_records: list[Any] | None = None,
) -> list[str]:
    from .config import YOUTUBE_SEED_CHANNELS
    from .creator_taxonomy import load_creator_taxonomy_seed

    rows = youtube_seed_rows if youtube_seed_rows is not None else load_youtube_seed_rows()
    errors = validate_youtube_seed_rows(rows)
    canonical = _canonical_identifiers(rows)

    config_seeds = config_seed_channels if config_seed_channels is not None else YOUTUBE_SEED_CHANNELS
    for seed in config_seeds:
        if seed.strip().lower() not in canonical:
            errors.append(f"config YouTube seed '{seed}' is missing from youtube_seed_channels.csv")

    taxonomy = taxonomy_records if taxonomy_records is not None else load_creator_taxonomy_seed()
    for record in taxonomy:
        platform = _record_value(record, "platform").lower()
        if platform != "youtube":
            continue
        name = _taxonomy_youtube_name(record)
        if name and name.lower() not in canonical:
            errors.append(
                f"creator_taxonomy_seed.csv YouTube seed '{name}' is missing from youtube_seed_channels.csv"
            )
    return errors
