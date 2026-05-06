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
