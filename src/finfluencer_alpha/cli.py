from __future__ import annotations

import json
import sqlite3
from datetime import datetime, time, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .classify import classify_text, should_create_candidate
from .config import (
    SEED_X_HANDLES,
    X_DISCOVERY_QUERIES,
    YOUTUBE_SEARCH_QUERIES,
    YOUTUBE_SEED_CHANNELS,
    ensure_data_dirs,
    get_settings,
)
from .creator_score import score_creators
from .db import connect, count_rows
from .db import init_db as initialize_database
from .exports import export_csvs
from .ticker_extract import extract_tickers
from .utils import configure_logging, get_logger
from .validation import api_key_status, missing_api_keys

app = typer.Typer(help="FIN 496 finfluencer alpha MVP research pipeline.")
console = Console()
logger = get_logger(__name__)


def _date_start_iso(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.combine(parsed, time.min).isoformat(timespec="seconds") + "Z"


def _date_end_exclusive_iso(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d").date() + timedelta(days=1)
    return datetime.combine(parsed, time.min).isoformat(timespec="seconds") + "Z"


def _require_paid_confirmation(confirm_paid_run: bool) -> bool:
    if confirm_paid_run:
        return True
    console.print(
        "Refusing paid X post retrieval. Re-run with --confirm-paid-run after reviewing the budget estimate."
    )
    return False


@app.callback()
def callback(verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging.")) -> None:
    configure_logging(verbose=verbose)
    ensure_data_dirs()


@app.command("init-db")
def init_db_command() -> None:
    db_path = initialize_database()
    console.print(f"Initialized SQLite database at {db_path}")


@app.command("discover-x")
def discover_x(max_pages: int = typer.Option(2, min=1, help="Pages per X discovery query.")) -> None:
    if not get_settings().x_bearer_token:
        console.print("Skipping X discovery: X_BEARER_TOKEN is not set.")
        return
    from .x_collect import discover_x_creators_from_queries

    count = discover_x_creators_from_queries(X_DISCOVERY_QUERIES, max_pages=max_pages)
    console.print(f"Discovered or updated {count} X creator candidates.")


@app.command("collect-x-seeds")
def collect_x_seeds(
    days_back: int = typer.Option(7, min=1, help="Recent collection window."),
    max_pages: int = typer.Option(2, min=1, help="Pages per seed handle."),
    strict_stock_pick: bool = typer.Option(False, help="Use stricter stock-pick query terms."),
) -> None:
    if not get_settings().x_bearer_token:
        console.print("Skipping X seed collection: X_BEARER_TOKEN is not set.")
        return
    from .x_collect import collect_x_for_seed_handles

    pages = collect_x_for_seed_handles(
        SEED_X_HANDLES,
        days_back=days_back,
        max_pages=max_pages,
        strict_stock_pick=strict_stock_pick,
    )
    console.print(f"Collected {pages} X result pages for seed handles.")


@app.command("discover-youtube")
def discover_youtube(max_results: int = typer.Option(25, min=1, max=50)) -> None:
    if not get_settings().youtube_api_key:
        console.print("Skipping YouTube discovery: YOUTUBE_API_KEY is not set.")
        return
    from .youtube_collect import discover_youtube_from_queries

    count = discover_youtube_from_queries(YOUTUBE_SEARCH_QUERIES, max_results=max_results)
    console.print(f"Discovered or collected {count} YouTube channel/video records.")


@app.command("collect-youtube-seeds")
def collect_youtube_seeds(max_pages: int = typer.Option(2, min=1)) -> None:
    if not get_settings().youtube_api_key:
        console.print("Skipping YouTube seed collection: YOUTUBE_API_KEY is not set.")
        return
    from .youtube_collect import collect_youtube_for_seed_channels

    count = collect_youtube_for_seed_channels(YOUTUBE_SEED_CHANNELS, max_pages=max_pages)
    console.print(f"Collected {count} YouTube videos from seed channels.")


@app.command("collect-youtube-history-seeds")
def collect_youtube_history_seeds(
    start_date: str = typer.Option(..., help="Start date as YYYY-MM-DD."),
    end_date: str = typer.Option(..., help="End date as YYYY-MM-DD."),
    max_channels: int = typer.Option(1, min=1, help="Maximum seed channels to collect."),
    max_pages: int = typer.Option(1, min=1, help="Upload playlist pages per channel."),
    dry_run: bool = typer.Option(False, help="Print quota estimate without calling the API."),
) -> None:
    from .youtube_quota import estimate_youtube_history_seed_quota

    estimate = estimate_youtube_history_seed_quota(
        YOUTUBE_SEED_CHANNELS,
        max_channels=max_channels,
        max_pages=max_pages,
    )
    console.print(
        "Estimated YouTube quota for collect-youtube-history-seeds: "
        f"channels={estimate.selected_seed_count}, "
        f"max_pages={estimate.max_pages_per_channel}, "
        f"channels.list={estimate.channels_list_calls}, "
        f"playlistItems.list={estimate.playlist_items_list_calls}, "
        f"videos.list={estimate.videos_list_calls}, "
        f"search.list={estimate.search_list_calls}, "
        f"total={estimate.total_quota_units} units."
    )
    console.print("Seed source: data/seeds/youtube_seed_channels.csv")
    if estimate.search_required_seeds:
        console.print(
            "Seeds requiring search.list: "
            f"{len(estimate.search_required_seeds)} "
            f"({', '.join(estimate.search_required_seeds)})"
        )
    else:
        console.print("Seeds requiring search.list: 0")
    if dry_run:
        console.print("Dry run only; no YouTube API calls were made.")
        return
    if not get_settings().youtube_api_key:
        console.print("Skipping YouTube history collection: YOUTUBE_API_KEY is not set.")
        return
    from .youtube_collect import collect_youtube_history_for_seed_channels

    count = collect_youtube_history_for_seed_channels(
        YOUTUBE_SEED_CHANNELS,
        start_date=start_date,
        end_date=end_date,
        max_channels=max_channels,
        max_pages=max_pages,
    )
    console.print(
        "Collected "
        f"{count} YouTube videos with current cumulative metrics "
        "(current_view_count/current_like_count/current_comment_count)."
    )


def _insert_ticker_mentions() -> int:
    initialize_database()
    rows_written = 0
    with connect() as conn:
        sources = conn.execute(
            "SELECT 'x' AS platform, post_id AS source_id, text AS text FROM raw_x_posts"
        ).fetchall()
        sources += conn.execute(
            """
            SELECT 'youtube' AS platform, video_id AS source_id,
                   COALESCE(title, '') || char(10) || COALESCE(description, '') AS text
            FROM raw_youtube_videos
            """
        ).fetchall()

        for source in sources:
            for mention in extract_tickers(source["text"]):
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ticker_mentions (
                      platform, source_id, ticker, mention_text,
                      cashtag_flag, extraction_method, confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source["platform"],
                        source["source_id"],
                        mention.ticker,
                        mention.mention_text,
                        int(mention.cashtag_flag),
                        mention.extraction_method,
                        mention.confidence,
                    ),
                )
                rows_written += conn.total_changes - before
        conn.commit()
    return rows_written


@app.command("extract-tickers")
def extract_tickers_command() -> None:
    count = _insert_ticker_mentions()
    console.print(f"Ticker extraction complete. Inserted/updated approximately {count} mention rows.")


def _source_rows_for_classification(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          tm.platform,
          tm.source_id,
          tm.ticker,
          CASE
            WHEN tm.platform = 'x' THEN x.creator_handle
            ELSE y.channel_id
          END AS creator_handle,
          CASE
            WHEN tm.platform = 'x' THEN x.created_at
            ELSE y.published_at
          END AS event_time,
          CASE
            WHEN tm.platform = 'x' THEN x.text
            ELSE COALESCE(y.title, '')
          END AS text
        FROM ticker_mentions tm
        LEFT JOIN raw_x_posts x
          ON tm.platform = 'x' AND tm.source_id = x.post_id
        LEFT JOIN raw_youtube_videos y
          ON tm.platform = 'youtube' AND tm.source_id = y.video_id
        """
    ).fetchall()


def _classify_mentions(refresh_existing: bool = False) -> int:
    initialize_database()
    inserted = 0
    with connect() as conn:
        if refresh_existing:
            conn.execute("DELETE FROM recommendation_candidates")
        for row in _source_rows_for_classification(conn):
            result = classify_text(row["text"])
            if not should_create_candidate(result, has_ticker=bool(row["ticker"])):
                continue
            before = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO recommendation_candidates (
                  platform, source_id, creator_handle, ticker, event_time, stance,
                  actionability_score, recommendation_type, horizon, disclosure_flag,
                  risk_discussion_flag, valuation_discussion_flag, classifier_confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["platform"],
                    row["source_id"],
                    row["creator_handle"],
                    row["ticker"],
                    row["event_time"],
                    result.stance,
                    result.actionability_score,
                    result.recommendation_type,
                    result.horizon,
                    int(result.disclosure_flag),
                    int(result.risk_discussion_flag),
                    int(result.valuation_discussion_flag),
                    result.classifier_confidence,
                ),
            )
            inserted += conn.total_changes - before
        conn.commit()
    return inserted


@app.command("classify")
def classify_command() -> None:
    count = _classify_mentions()
    console.print(f"Classification complete. Inserted {count} recommendation candidates.")


@app.command("build-events")
def build_events_command() -> None:
    ticker_count = _insert_ticker_mentions()
    candidate_count = _classify_mentions(refresh_existing=True)
    console.print(
        "Event build complete. "
        f"Inserted/updated approximately {ticker_count} ticker mentions and "
        f"{candidate_count} recommendation candidates."
    )


@app.command("score-creators")
def score_creators_command() -> None:
    count = score_creators()
    console.print(f"Scored {count} creators.")


@app.command("export")
def export_command() -> None:
    paths = export_csvs()
    for name, path in paths.items():
        console.print(f"{name}: {path}")


@app.command("export-research-sample")
def export_research_sample_command() -> None:
    from .research_sample import export_research_sample

    paths = export_research_sample()
    for name, path in paths.items():
        console.print(f"{name}: {path}")


@app.command("count-x-creators")
def count_x_creators(
    start_date: str = typer.Option(..., help="Start date as YYYY-MM-DD."),
    end_date: str = typer.Option(..., help="End date as YYYY-MM-DD."),
) -> None:
    from .creator_taxonomy import load_creator_taxonomy_seed, seed_creator_taxonomy
    from .selection_report import export_creator_selection_report
    from .x_counts import XCountsAccessError, count_x_creator_stockpick_posts

    initialize_database()
    seed_creator_taxonomy()
    if not get_settings().x_bearer_token:
        console.print("Skipping X full-archive counts: X_BEARER_TOKEN is not set.")
        paths = export_creator_selection_report()
        for name, path in paths.items():
            console.print(f"{name}: {path}")
        return

    total = 0
    x_records = [record for record in load_creator_taxonomy_seed() if record.platform == "x"]
    for record in x_records:
        try:
            result = count_x_creator_stockpick_posts(record.handle_or_channel, start_date, end_date)
        except XCountsAccessError as exc:
            console.print(str(exc))
            paths = export_creator_selection_report()
            for name, path in paths.items():
                console.print(f"{name}: {path}")
            raise typer.Exit(code=1) from exc
        total += result.total_tweet_count
        console.print(
            f"{record.handle_or_channel}: {result.total_tweet_count:,} stock-pick-filtered posts"
        )
    console.print(f"Counted {len(x_records)} X creators with {total:,} estimated post reads.")


@app.command("select-creators")
def select_creators(
    budget: float = typer.Option(50.0, min=0.0, help="Budget ceiling for planning in USD."),
) -> None:
    from .creator_selection import build_creator_selection
    from .selection_report import export_creator_selection_report

    settings = get_settings()
    read_budget = min(
        int(budget / settings.x_cost_per_post_read),
        settings.x_main_collection_read_budget,
        settings.x_max_total_post_reads,
    )
    rows = build_creator_selection(read_budget=read_budget)
    paths = export_creator_selection_report()
    selected = sum(1 for row in rows if row["selected_for_collection"])
    console.print(f"Scored {len(rows)} creators; selected {selected} X primary creators in plan.")
    for name, path in paths.items():
        console.print(f"{name}: {path}")


@app.command("collect-x-budgeted")
def collect_x_budgeted(
    start_date: str = typer.Option(..., help="Start date as YYYY-MM-DD."),
    end_date: str = typer.Option(..., help="End date as YYYY-MM-DD."),
    budget: float = typer.Option(50.0, min=0.0, help="Command budget in USD."),
    confirm_paid_run: bool = typer.Option(False, help="Required for paid X post retrieval."),
    override_budget: bool = typer.Option(False, help="Override the hard budget guard."),
) -> None:
    from .budget_guard import BudgetExceededError, BudgetGuard
    from .creator_selection import build_creator_selection
    from .creator_taxonomy import load_creator_taxonomy_seed, seed_creator_taxonomy
    from .selection_report import export_creator_selection_report
    from .x_collect import search_x_full_archive_posts
    from .x_counts import XCountsAccessError, count_x_creator_stockpick_posts, x_stockpick_query

    settings = get_settings()
    initialize_database()
    seed_creator_taxonomy()
    if not settings.x_bearer_token:
        console.print("Skipping budgeted X collection: X_BEARER_TOKEN is not set.")
        return
    if budget > settings.x_max_budget_usd and not override_budget:
        console.print(
            "X budget guard blocked paid run: "
            f"requested budget ${budget:.2f} exceeds "
            f"X_MAX_BUDGET_USD=${settings.x_max_budget_usd:.2f}."
        )
        raise typer.Exit(code=1)
    if not _require_paid_confirmation(confirm_paid_run):
        raise typer.Exit(code=1)

    for record in [record for record in load_creator_taxonomy_seed() if record.platform == "x"]:
        try:
            count_x_creator_stockpick_posts(record.handle_or_channel, start_date, end_date)
        except XCountsAccessError as exc:
            console.print(str(exc))
            console.print("Stopping before any paid X post retrieval.")
            raise typer.Exit(code=1) from exc

    read_budget = min(
        int(budget / settings.x_cost_per_post_read),
        settings.x_main_collection_read_budget,
        settings.x_max_total_post_reads,
    )
    build_creator_selection(read_budget=read_budget)
    with connect() as conn:
        selected = conn.execute(
            """
            SELECT handle_or_channel, estimated_x_reads, creator_selection_score
            FROM creator_selection
            WHERE platform = 'x' AND selected_for_collection = 1
            ORDER BY creator_selection_score DESC
            """
        ).fetchall()

    estimated_reads = min(sum(int(row["estimated_x_reads"] or 0) for row in selected), read_budget)
    if estimated_reads <= 0:
        console.print("No X creators selected for paid collection. Run count-x-creators/select-creators first.")
        export_creator_selection_report()
        return

    guard = BudgetGuard()
    console.print(guard.format_snapshot(estimated_reads, "collect-x-budgeted full-archive post reads"))
    try:
        guard.assert_budget_available(estimated_reads, override_budget=override_budget)
    except BudgetExceededError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc
    guard.reserve_budget(
        "x_main_collection",
        estimated_reads,
        details=f"{start_date} to {end_date}",
        override_budget=override_budget,
    )

    remaining_reads = estimated_reads
    actual_reads = 0
    for row in selected:
        if remaining_reads <= 0:
            break
        handle = row["handle_or_channel"]
        creator_cap = min(int(row["estimated_x_reads"] or 0), remaining_reads)
        reads = search_x_full_archive_posts(
            x_stockpick_query(handle),
            _date_start_iso(start_date),
            _date_end_exclusive_iso(end_date),
            max_reads=creator_cap,
            raw_prefix=f"budgeted_{handle}",
        )
        actual_reads += reads
        remaining_reads -= reads
        console.print(f"{handle}: collected {reads:,} posts")

    guard.record_actual_usage("x_main_collection", actual_reads)
    _insert_ticker_mentions()
    _classify_mentions()
    score_creators()
    build_creator_selection(read_budget=read_budget)
    paths = export_creator_selection_report()
    console.print(f"Recorded actual X post reads: {actual_reads:,}")
    for name, path in paths.items():
        console.print(f"{name}: {path}")


@app.command("enrich-x-budgeted")
def enrich_x_budgeted(
    budget: float = typer.Option(10.0, min=0.0, help="Command budget in USD."),
    confirm_paid_run: bool = typer.Option(False, help="Required for paid X post retrieval."),
    override_budget: bool = typer.Option(False, help="Override the hard budget guard."),
) -> None:
    from .budget_guard import BudgetExceededError, BudgetGuard
    from .creator_selection import plan_enrichment_events
    from .x_collect import collect_x_quote_tweets, search_x_full_archive_posts

    settings = get_settings()
    initialize_database()
    if not settings.x_bearer_token:
        console.print("Skipping X enrichment: X_BEARER_TOKEN is not set.")
        return
    if not _require_paid_confirmation(confirm_paid_run):
        raise typer.Exit(code=1)

    with connect() as conn:
        candidates = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                  rc.candidate_id,
                  rc.source_id,
                  rc.creator_handle,
                  rc.actionability_score,
                  COALESCE(cs.creator_selection_score, 0) AS creator_selection_score,
                  (
                    COALESCE(x.like_count, 0) + COALESCE(x.repost_count, 0) +
                    COALESCE(x.reply_count, 0) + COALESCE(x.quote_count, 0)
                  ) AS engagement,
                  COALESCE(MAX(tm.confidence), 0) AS ticker_confidence
                FROM recommendation_candidates rc
                JOIN raw_x_posts x
                  ON rc.platform = 'x' AND rc.source_id = x.post_id
                LEFT JOIN creator_selection cs
                  ON cs.platform = 'x' AND cs.handle_or_channel = rc.creator_handle
                LEFT JOIN ticker_mentions tm
                  ON tm.platform = 'x' AND tm.source_id = rc.source_id
                  AND tm.ticker = rc.ticker
                WHERE rc.platform = 'x'
                GROUP BY rc.candidate_id
                ORDER BY
                  rc.actionability_score DESC,
                  creator_selection_score DESC,
                  engagement DESC,
                  ticker_confidence DESC
                """
            ).fetchall()
        ]

    read_budget = min(
        int(budget / settings.x_cost_per_post_read),
        settings.x_enrichment_read_budget,
        settings.max_x_enriched_events
        * (settings.max_x_reply_reads_per_event + settings.max_x_quote_reads_per_event),
    )
    guard = BudgetGuard()
    read_budget = min(read_budget, guard.remaining_reads())
    plans = plan_enrichment_events(
        candidates,
        max_events=settings.max_x_enriched_events,
        max_replies=settings.max_x_reply_reads_per_event,
        max_quotes=settings.max_x_quote_reads_per_event,
        remaining_reads=read_budget,
    )
    estimated_reads = sum(plan.reply_read_cap + plan.quote_read_cap for plan in plans)
    if estimated_reads <= 0:
        console.print("No X recommendation candidates are available for enrichment within budget.")
        return

    console.print(guard.format_snapshot(estimated_reads, "enrich-x-budgeted replies and quotes"))
    try:
        guard.assert_budget_available(estimated_reads, override_budget=override_budget)
    except BudgetExceededError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc
    guard.reserve_budget(
        "x_enrichment",
        estimated_reads,
        details=f"{len(plans)} recommendation events",
        override_budget=override_budget,
    )

    actual_reads = 0
    with connect() as conn:
        for plan in plans:
            reply_reads = search_x_full_archive_posts(
                f"conversation_id:{plan.source_id} is:reply -is:retweet",
                None,
                None,
                max_reads=plan.reply_read_cap,
                raw_prefix=f"replies_{plan.source_id}",
            )
            quote_reads = collect_x_quote_tweets(plan.source_id, max_reads=plan.quote_read_cap)
            actual_reads += reply_reads + quote_reads
            conn.execute(
                """
                INSERT INTO x_enriched_events (
                  candidate_id, source_id, reply_reads, quote_reads, status
                )
                VALUES (?, ?, ?, ?, 'collected')
                """,
                (plan.candidate_id, plan.source_id, reply_reads, quote_reads),
            )
        conn.commit()
    guard.record_actual_usage("x_enrichment", actual_reads)
    console.print(f"Enriched {len(plans)} events with {actual_reads:,} X post reads.")


@app.command("export-creator-selection-report")
def export_creator_selection_report_command() -> None:
    from .creator_selection import build_creator_selection
    from .selection_report import export_creator_selection_report

    build_creator_selection()
    paths = export_creator_selection_report()
    for name, path in paths.items():
        console.print(f"{name}: {path}")


def _summary_stats() -> dict[str, int]:
    initialize_database()
    with connect() as conn:
        return {
            "creators": count_rows(conn, "creators"),
            "raw_x_posts": count_rows(conn, "raw_x_posts"),
            "raw_youtube_videos": count_rows(conn, "raw_youtube_videos"),
            "ticker_mentions": count_rows(conn, "ticker_mentions"),
            "recommendation_candidates": count_rows(conn, "recommendation_candidates"),
            "creator_scores": count_rows(conn, "creator_scores"),
        }


def _print_summary(stats: dict[str, int], exports: dict[str, Path]) -> None:
    table = Table(title="FIN 496 MVP Summary")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for key, value in stats.items():
        table.add_row(key, str(value))
    console.print(table)
    console.print("Exports:")
    for name, path in exports.items():
        console.print(f"  {name}: {path}")


@app.command("run-mvp")
def run_mvp(
    x_max_pages: int = typer.Option(2, min=1, help="Pages per X collection/discovery query."),
    youtube_max_results: int = typer.Option(25, min=1, max=50),
    youtube_max_pages: int = typer.Option(2, min=1),
    x_days_back: int = typer.Option(7, min=1),
) -> None:
    settings = get_settings()
    db_path = initialize_database()
    console.print(f"Initialized database: {db_path}")

    missing = missing_api_keys()
    if missing:
        console.print(f"Missing API keys: {', '.join(missing)}. API collection steps will be skipped.")

    status = api_key_status()
    if status["x"]:
        from .x_collect import collect_x_for_seed_handles, discover_x_creators_from_queries

        collect_x_for_seed_handles(SEED_X_HANDLES, days_back=x_days_back, max_pages=x_max_pages)
        discover_x_creators_from_queries(X_DISCOVERY_QUERIES, max_pages=x_max_pages)
    else:
        console.print("Skipping X collection/discovery because X_BEARER_TOKEN is not set.")

    if settings.x_search_mode == "all":
        console.print(
            "X_SEARCH_MODE=all is enabled. Full archive requires elevated X API access; "
            "the pipeline will warn and continue if unavailable."
        )

    if status["youtube"]:
        from .youtube_collect import (
            collect_youtube_for_seed_channels,
            discover_youtube_from_queries,
        )

        discover_youtube_from_queries(YOUTUBE_SEARCH_QUERIES, max_results=youtube_max_results)
        collect_youtube_for_seed_channels(YOUTUBE_SEED_CHANNELS, max_pages=youtube_max_pages)
    else:
        console.print("Skipping YouTube collection/discovery because YOUTUBE_API_KEY is not set.")

    _insert_ticker_mentions()
    _classify_mentions()
    score_creators()
    exports = export_csvs()
    _print_summary(_summary_stats(), exports)


@app.command("show-config")
def show_config() -> None:
    settings = get_settings()
    safe = settings.model_dump()
    safe["x_bearer_token"] = bool(settings.x_bearer_token)
    safe["youtube_api_key"] = bool(settings.youtube_api_key)
    console.print(json.dumps(safe, indent=2))


def main() -> None:
    app()
