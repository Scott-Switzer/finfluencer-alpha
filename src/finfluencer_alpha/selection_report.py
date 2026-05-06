from __future__ import annotations

from pathlib import Path

import pandas as pd

from .budget_guard import estimate_cost
from .config import EXPORTS_DIR, ensure_data_dirs, get_settings
from .db import connect, init_db

CREATOR_SELECTION_COLUMNS = [
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

X_BUDGET_COLUMNS = [
    "budget_bucket",
    "max_reads",
    "max_cost",
    "planned_use",
    "actual_reads",
    "actual_cost",
    "remaining_budget",
]

X_COUNTS_COLUMNS = [
    "handle",
    "start_date",
    "end_date",
    "granularity",
    "total_tweet_count",
    "collected_at",
]

FINAL_SELECTED_CREATOR_COLUMNS = [
    "platform",
    "handle_or_channel",
    "initial_category",
    "creator_selection_score",
    "recommended_action",
    "estimated_x_reads",
    "estimated_x_cost",
    "reason",
]


def _write(df: pd.DataFrame, path: Path, columns: list[str]) -> Path:
    if df.empty:
        df = pd.DataFrame(columns=columns)
    df.to_csv(path, index=False)
    return path


def _budget_plan_df() -> pd.DataFrame:
    settings = get_settings()
    buckets = [
        ("discovery", settings.x_discovery_read_budget, "Initial paid discovery sample if needed"),
        ("main_collection", settings.x_main_collection_read_budget, "Budgeted full-archive stock-pick posts"),
        ("enrichment", settings.x_enrichment_read_budget, "Replies/quotes for high-confidence events"),
        ("buffer", settings.x_buffer_read_budget, "Reserved safety buffer"),
    ]
    with connect() as conn:
        usage_rows = conn.execute(
            """
            SELECT job_name, COALESCE(SUM(actual_reads), 0) AS actual_reads
            FROM x_budget_usage
            GROUP BY job_name
            """
        ).fetchall()
    usage_by_bucket = {"discovery": 0, "main_collection": 0, "enrichment": 0, "buffer": 0}
    for row in usage_rows:
        job = row["job_name"]
        if "enrichment" in job:
            bucket = "enrichment"
        elif "discovery" in job:
            bucket = "discovery"
        elif "main" in job or "collection" in job:
            bucket = "main_collection"
        else:
            bucket = "buffer"
        usage_by_bucket[bucket] += int(row["actual_reads"] or 0)

    records = []
    total_actual = 0
    for bucket, max_reads, planned_use in buckets:
        actual_reads = usage_by_bucket[bucket]
        total_actual += actual_reads
        records.append(
            {
                "budget_bucket": bucket,
                "max_reads": max_reads,
                "max_cost": estimate_cost(max_reads),
                "planned_use": planned_use,
                "actual_reads": actual_reads,
                "actual_cost": estimate_cost(actual_reads),
                "remaining_budget": estimate_cost(max(max_reads - actual_reads, 0)),
            }
        )
    max_total_reads = min(
        settings.x_max_total_post_reads,
        int(settings.x_max_budget_usd / settings.x_cost_per_post_read),
    )
    records.append(
        {
            "budget_bucket": "total",
            "max_reads": max_total_reads,
            "max_cost": settings.x_max_budget_usd,
            "planned_use": "Hard cap across all paid X post reads",
            "actual_reads": total_actual,
            "actual_cost": estimate_cost(total_actual),
            "remaining_budget": estimate_cost(max(max_total_reads - total_actual, 0)),
        }
    )
    return pd.DataFrame(records)


def export_creator_selection_report() -> dict[str, Path]:
    init_db()
    ensure_data_dirs()
    paths = {
        "creator_selection_report": EXPORTS_DIR / "creator_selection_report.csv",
        "x_budget_plan": EXPORTS_DIR / "x_budget_plan.csv",
        "x_counts_by_creator": EXPORTS_DIR / "x_counts_by_creator.csv",
        "final_selected_creators": EXPORTS_DIR / "final_selected_creators.csv",
    }
    with connect() as conn:
        selection_df = pd.read_sql_query(
            """
            SELECT
              platform, handle_or_channel, initial_category,
              count_stockpick_filtered, estimated_x_reads, estimated_x_cost,
              ticker_density, actionable_density, creator_selection_score,
              recommended_action, reason
            FROM creator_selection
            ORDER BY platform, recommended_action, creator_selection_score DESC
            """,
            conn,
        )
        counts_df = pd.read_sql_query(
            """
            SELECT
              handle, start_date, end_date, granularity, total_tweet_count,
              collected_at
            FROM x_query_counts
            WHERE handle IS NOT NULL
            ORDER BY handle, collected_at DESC
            """,
            conn,
        )
        selected_df = pd.read_sql_query(
            """
            SELECT
              platform, handle_or_channel, initial_category,
              creator_selection_score, recommended_action, estimated_x_reads,
              estimated_x_cost, reason
            FROM creator_selection
            WHERE selected_for_collection = 1
               OR recommended_action IN ('include_primary', 'include_control')
            ORDER BY selected_for_collection DESC, creator_selection_score DESC
            """,
            conn,
        )
    _write(selection_df, paths["creator_selection_report"], CREATOR_SELECTION_COLUMNS)
    _write(_budget_plan_df(), paths["x_budget_plan"], X_BUDGET_COLUMNS)
    _write(counts_df, paths["x_counts_by_creator"], X_COUNTS_COLUMNS)
    _write(selected_df, paths["final_selected_creators"], FINAL_SELECTED_CREATOR_COLUMNS)
    return paths
