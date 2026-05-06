from __future__ import annotations

DUPLICATE_EVENT_KEY_FIELDS = [
    "ticker",
    "creator_id",
    "platform",
    "event_trading_day",
    "recommendation_direction",
]

CROSS_PLATFORM_CLUSTER_FIELDS = [
    "ticker",
    "youtube_video_id",
    "x_post_id",
    "cluster_window_trading_days",
    "attention_cluster_id",
]

EVENT_DATE_ALIGNMENT_RULES = [
    "preserve_raw_published_at_timestamp_with_timezone",
    "convert_to_us_eastern_time_for_market_alignment",
    "after_4pm_et_moves_to_next_trading_day",
    "weekend_or_market_holiday_moves_to_next_trading_day",
]

MARKET_DATA_READINESS_FIELDS = [
    "event_trading_day",
    "price_available_flag",
    "volume_available_flag",
    "benchmark_available_flag",
    "sector_available_flag",
    "market_cap_available_flag",
    "liquidity_screen_pass",
    "missing_market_data_reason",
]

SOURCE_LAYER_VALUES = [
    "title",
    "description",
    "transcript",
    "manual",
    "x_text",
    "comment_context",
]

CONFIDENCE_LABEL_VALUES = ["high", "medium", "low", "exclude"]
