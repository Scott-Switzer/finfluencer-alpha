from finfluencer_alpha.exports import MANUAL_VALIDATION_COLUMNS
from finfluencer_alpha.selection_report import (
    CREATOR_SELECTION_COLUMNS,
    FINAL_SELECTED_CREATOR_COLUMNS,
    X_BUDGET_COLUMNS,
    X_COUNTS_COLUMNS,
)


def test_creator_selection_report_headers_are_stable() -> None:
    assert CREATOR_SELECTION_COLUMNS == [
        "platform",
        "handle_or_channel",
        "initial_category",
        "count_stockpick_filtered",
        "estimated_x_reads",
        "estimated_x_cost",
        "ticker_density",
        "actionable_density",
        "creator_selection_score",
        "recommended_action",
        "reason",
    ]


def test_budget_and_selection_export_headers_are_stable() -> None:
    assert X_BUDGET_COLUMNS == [
        "budget_bucket",
        "max_reads",
        "max_cost",
        "planned_use",
        "actual_reads",
        "actual_cost",
        "remaining_budget",
    ]
    assert X_COUNTS_COLUMNS == [
        "handle",
        "start_date",
        "end_date",
        "granularity",
        "total_tweet_count",
        "collected_at",
    ]
    assert FINAL_SELECTED_CREATOR_COLUMNS == [
        "platform",
        "handle_or_channel",
        "initial_category",
        "creator_selection_score",
        "recommended_action",
        "estimated_x_reads",
        "estimated_x_cost",
        "reason",
    ]


def test_manual_validation_export_headers_are_stable() -> None:
    assert MANUAL_VALIDATION_COLUMNS == [
        "event_id",
        "platform",
        "video_id",
        "post_id",
        "video_url",
        "post_url",
        "channel_title",
        "x_handle",
        "creator_category",
        "published_at",
        "title",
        "post_text",
        "ticker",
        "company_name",
        "detected_action",
        "detected_direction",
        "confidence_score",
        "confidence_label",
        "source_layer",
        "evidence_snippet",
        "transcript_timestamp_start",
        "transcript_timestamp_end",
        "current_view_count",
        "current_like_count",
        "current_comment_count",
        "manual_label",
        "manual_direction",
        "manual_action",
        "manual_confidence",
        "manual_notes",
        "reviewer",
        "reviewed_at",
    ]
