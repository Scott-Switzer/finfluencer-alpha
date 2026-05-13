from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import get_settings
from .db import connect, init_db


class ProviderTier(Enum):
    PAID_API = "paid_api"
    APIFY = "apify"
    NATIVE_PACKAGE = "native_package"
    YT_DLP = "yt_dlp"


PROVIDER_ORDER = [
    ProviderTier.PAID_API,
    ProviderTier.APIFY,
    ProviderTier.NATIVE_PACKAGE,
    ProviderTier.YT_DLP,
]


@dataclass(frozen=True)
class FallbackStatus:
    video_id: str
    tier: ProviderTier
    status: str
    error_type: str | None = None
    error_message: str | None = None


def resolve_provider_chain(
    *,
    video_id: str,
    attempted_tiers: frozenset[ProviderTier] | None = None,
) -> list[ProviderTier]:
    if attempted_tiers is None:
        attempted_tiers = frozenset()
    settings = get_settings()
    chain: list[ProviderTier] = []
    for tier in PROVIDER_ORDER:
        if tier in attempted_tiers:
            continue
        if tier == ProviderTier.PAID_API:
            if settings.transcriptapi_key or settings.youtubetranscript_dev_api_key:
                chain.append(tier)
        elif tier == ProviderTier.APIFY:
            if settings.apify_token:
                chain.append(tier)
        elif tier == ProviderTier.NATIVE_PACKAGE:
            chain.append(tier)
        elif tier == ProviderTier.YT_DLP:
            chain.append(tier)
    return chain


def record_fallback_attempt(
    *,
    video_id: str,
    tier: ProviderTier,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO transcript_collection_attempts (
              run_id, video_id, attempted_at, status, error_type,
              error_message, provider_name
            )
            VALUES (NULL, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
            """,
            (
                video_id,
                status,
                error_type,
                error_message,
                f"fallback:{tier.value}",
            ),
        )
        conn.commit()
