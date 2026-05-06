from __future__ import annotations

import json
import sqlite3
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
from .x_collect import collect_x_for_seed_handles, discover_x_creators_from_queries
from .youtube_collect import collect_youtube_for_seed_channels, discover_youtube_from_queries

app = typer.Typer(help="FIN 496 finfluencer alpha MVP research pipeline.")
console = Console()
logger = get_logger(__name__)


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
    count = discover_youtube_from_queries(YOUTUBE_SEARCH_QUERIES, max_results=max_results)
    console.print(f"Discovered or collected {count} YouTube channel/video records.")


@app.command("collect-youtube-seeds")
def collect_youtube_seeds(max_pages: int = typer.Option(2, min=1)) -> None:
    if not get_settings().youtube_api_key:
        console.print("Skipping YouTube seed collection: YOUTUBE_API_KEY is not set.")
        return
    count = collect_youtube_for_seed_channels(YOUTUBE_SEED_CHANNELS, max_pages=max_pages)
    console.print(f"Collected {count} YouTube videos from seed channels.")


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
            ELSE COALESCE(y.title, '') || char(10) || COALESCE(y.description, '')
          END AS text
        FROM ticker_mentions tm
        LEFT JOIN raw_x_posts x
          ON tm.platform = 'x' AND tm.source_id = x.post_id
        LEFT JOIN raw_youtube_videos y
          ON tm.platform = 'youtube' AND tm.source_id = y.video_id
        """
    ).fetchall()


def _classify_mentions() -> int:
    initialize_database()
    inserted = 0
    with connect() as conn:
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


@app.command("score-creators")
def score_creators_command() -> None:
    count = score_creators()
    console.print(f"Scored {count} creators.")


@app.command("export")
def export_command() -> None:
    paths = export_csvs()
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
