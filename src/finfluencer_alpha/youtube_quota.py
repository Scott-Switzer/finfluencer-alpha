from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

YOUTUBE_QUOTA_COSTS = {
    "channels.list": 1,
    "playlistItems.list": 1,
    "search.list": 100,
    "videos.list": 1,
}


@dataclass(frozen=True)
class YouTubeQuotaEstimate:
    selected_seed_count: int
    max_pages_per_channel: int
    channels_list_calls: int
    playlist_items_list_calls: int
    videos_list_calls: int
    search_list_calls: int
    search_required_seeds: tuple[str, ...] = ()

    @property
    def total_quota_units(self) -> int:
        return (
            self.channels_list_calls * YOUTUBE_QUOTA_COSTS["channels.list"]
            + self.playlist_items_list_calls * YOUTUBE_QUOTA_COSTS["playlistItems.list"]
            + self.videos_list_calls * YOUTUBE_QUOTA_COSTS["videos.list"]
            + self.search_list_calls * YOUTUBE_QUOTA_COSTS["search.list"]
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "selected_seed_count": self.selected_seed_count,
            "max_pages_per_channel": self.max_pages_per_channel,
            "channels.list": self.channels_list_calls,
            "playlistItems.list": self.playlist_items_list_calls,
            "videos.list": self.videos_list_calls,
            "search.list": self.search_list_calls,
            "total_quota_units": self.total_quota_units,
        }


def seed_resolution_method(seed: str) -> str:
    normalized = seed.strip()
    if not normalized:
        return "skip"
    if normalized.startswith("UC"):
        return "channel_id"
    if normalized.startswith("@"):
        return "handle"
    parsed = urlparse(normalized)
    if parsed.netloc.endswith("youtube.com"):
        path = parsed.path.strip("/")
        if path.startswith("channel/UC"):
            return "channel_id"
        if path.startswith("@"):
            return "handle"
    return "search"


def _seed_resolution_method(seed: str) -> str:
    return seed_resolution_method(seed)


def seed_requires_search_list(seed: str) -> bool:
    return seed_resolution_method(seed) == "search"


def estimate_youtube_seed_quota_units(seed: str, max_pages: int) -> int:
    normalized = seed.strip()
    if not normalized:
        return 0
    resolution_method = seed_resolution_method(normalized)
    if resolution_method == "channel_id":
        channels_list_calls = 1
        search_list_calls = 0
    elif resolution_method == "handle":
        channels_list_calls = 2
        search_list_calls = 0
    else:
        channels_list_calls = 1
        search_list_calls = 1
    return (
        channels_list_calls * YOUTUBE_QUOTA_COSTS["channels.list"]
        + max(max_pages, 1) * YOUTUBE_QUOTA_COSTS["playlistItems.list"]
        + YOUTUBE_QUOTA_COSTS["videos.list"]
        + search_list_calls * YOUTUBE_QUOTA_COSTS["search.list"]
    )


def seeds_requiring_search_list(seed_channels: list[str], max_channels: int) -> list[str]:
    selected = seed_channels[: max(max_channels, 0)]
    return [seed for seed in selected if _seed_resolution_method(seed) == "search"]


def estimate_youtube_history_seed_quota(
    seed_channels: list[str],
    max_channels: int,
    max_pages: int,
) -> YouTubeQuotaEstimate:
    selected = seed_channels[: max(max_channels, 0)]
    channels_list_calls = 0
    search_list_calls = 0
    playlist_items_list_calls = 0
    videos_list_calls = 0
    search_required: list[str] = []

    for seed in selected:
        normalized = seed.strip()
        if not normalized:
            continue
        resolution_method = _seed_resolution_method(normalized)
        if resolution_method == "channel_id":
            channels_list_calls += 1
        elif resolution_method == "handle":
            channels_list_calls += 2
        else:
            search_list_calls += 1
            channels_list_calls += 1
            search_required.append(normalized)
        playlist_items_list_calls += max(max_pages, 1)
        videos_list_calls += 1

    return YouTubeQuotaEstimate(
        selected_seed_count=len([seed for seed in selected if seed.strip()]),
        max_pages_per_channel=max(max_pages, 1),
        channels_list_calls=channels_list_calls,
        playlist_items_list_calls=playlist_items_list_calls,
        videos_list_calls=videos_list_calls,
        search_list_calls=search_list_calls,
        search_required_seeds=tuple(search_required),
    )
