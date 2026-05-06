from finfluencer_alpha.event_schema import (
    CROSS_PLATFORM_CLUSTER_FIELDS,
    DUPLICATE_EVENT_KEY_FIELDS,
    EVENT_DATE_ALIGNMENT_RULES,
    MARKET_DATA_READINESS_FIELDS,
)


def test_duplicate_event_key_fields_are_stable() -> None:
    assert DUPLICATE_EVENT_KEY_FIELDS == [
        "ticker",
        "creator_id",
        "platform",
        "event_trading_day",
        "recommendation_direction",
    ]


def test_cross_platform_cluster_preserves_separate_events() -> None:
    assert CROSS_PLATFORM_CLUSTER_FIELDS == [
        "ticker",
        "youtube_video_id",
        "x_post_id",
        "cluster_window_trading_days",
        "attention_cluster_id",
    ]


def test_event_date_alignment_rules_are_declared() -> None:
    assert EVENT_DATE_ALIGNMENT_RULES == [
        "preserve_raw_published_at_timestamp_with_timezone",
        "convert_to_us_eastern_time_for_market_alignment",
        "after_4pm_et_moves_to_next_trading_day",
        "weekend_or_market_holiday_moves_to_next_trading_day",
    ]


def test_market_data_readiness_fields_are_declared() -> None:
    assert MARKET_DATA_READINESS_FIELDS == [
        "event_trading_day",
        "price_available_flag",
        "volume_available_flag",
        "benchmark_available_flag",
        "sector_available_flag",
        "market_cap_available_flag",
        "liquidity_screen_pass",
        "missing_market_data_reason",
    ]
