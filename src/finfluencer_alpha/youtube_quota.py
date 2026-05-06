from __future__ import annotations

from dataclasses import dataclass

YOUTUBE_QUOTA_COSTS = {
    "channels.list": 1,
    "playlistItems.list": 1,
    "search.list": 100,
    "videos.list": 1,
}


@dataclass(frozen=True)
class YouTubeQuotaEstimate:
    channels_list_calls: int
    playlist_items_list_calls: int
    videos_list_calls: int
    search_list_calls: int

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
            "channels.list": self.channels_list_calls,
            "playlistItems.list": self.playlist_items_list_calls,
            "videos.list": self.videos_list_calls,
            "search.list": self.search_list_calls,
            "total_quota_units": self.total_quota_units,
        }


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

    for seed in selected:
        normalized = seed.strip()
        if not normalized:
            continue
        if normalized.startswith("UC"):
            channels_list_calls += 1
        elif normalized.startswith("@"):
            channels_list_calls += 2
        else:
            search_list_calls += 1
            channels_list_calls += 1
        playlist_items_list_calls += max(max_pages, 1)
        videos_list_calls += 1

    return YouTubeQuotaEstimate(
        channels_list_calls=channels_list_calls,
        playlist_items_list_calls=playlist_items_list_calls,
        videos_list_calls=videos_list_calls,
        search_list_calls=search_list_calls,
    )
