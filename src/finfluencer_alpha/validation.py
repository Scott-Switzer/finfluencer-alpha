from __future__ import annotations

from .config import get_settings


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
