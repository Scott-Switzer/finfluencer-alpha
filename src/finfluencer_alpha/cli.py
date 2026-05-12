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
    load_youtube_seed_rows,
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
DEFAULT_TRANSCRIPT_VENDOR_BATCH_OUTPUT = Path("data/exports/transcript_vendor_batch.csv")
DEFAULT_PROVIDER_TRANSCRIPT_OUTPUT = Path(
    "data/imports/provider_transcripts_youtubetranscript_dev.csv"
)
DEFAULT_OVERNIGHT_LOG_PATH = Path("data/logs/overnight_transcripts.log")
DEFAULT_OVERNIGHT_SUMMARY_PATH = Path(
    "data/exports/report_ready/overnight_transcript_collection_summary.txt"
)
DEFAULT_AUTO_LABEL_INPUT_PATH = Path("data/exports/validation/event_validation_sample.csv")
DEFAULT_AUTO_LABEL_OUTPUT_PATH = Path(
    "data/exports/validation/event_validation_sample_auto_labeled.csv"
)
DEFAULT_AUTO_LABEL_REVIEW_PATH = Path("data/exports/validation/event_validation_review_needed.csv")
DEFAULT_AUTO_LABEL_SUMMARY_MD_PATH = Path("data/exports/validation/auto_labeling_summary.md")
DEFAULT_AUTO_LABEL_SUMMARY_CSV_PATH = Path("data/exports/validation/auto_labeling_summary.csv")
DEFAULT_CLEAN_AUTO_LABEL_INPUT_PATH = DEFAULT_AUTO_LABEL_OUTPUT_PATH
DEFAULT_CLEAN_AUTO_LABEL_EVENTS_INPUT_PATH = Path("data/exports/transcript_recommendation_events.csv")
DEFAULT_CLEAN_AUTO_LABEL_OUTPUT_PATH = Path("data/exports/validation/clean_auto_labeled_events.csv")
DEFAULT_CLEAN_AUTO_LABEL_EXCLUSIONS_PATH = Path(
    "data/exports/validation/clean_auto_labeled_events_exclusions.csv"
)
DEFAULT_CLEAN_AUTO_LABEL_SUMMARY_MD_PATH = Path(
    "data/exports/validation/clean_auto_labeled_events_summary.md"
)
DEFAULT_MARKET_DATA_REQUEST_INPUT_PATH = DEFAULT_CLEAN_AUTO_LABEL_OUTPUT_PATH
DEFAULT_MARKET_DATA_REQUEST_OUTPUT_PATH = Path("data/exports/market_data/market_data_request.csv")
DEFAULT_MARKET_DATA_UNIQUE_TICKERS_PATH = Path("data/exports/market_data/unique_tickers.csv")
DEFAULT_MARKET_DATA_EVENT_DATES_PATH = Path("data/exports/market_data/event_dates_by_ticker.csv")
DEFAULT_MARKET_DATA_SUMMARY_MD_PATH = Path(
    "data/exports/market_data/market_data_request_summary.md"
)
DEFAULT_THRESHOLD_SENSITIVITY_INPUT_PATH = DEFAULT_AUTO_LABEL_OUTPUT_PATH
DEFAULT_THRESHOLD_SENSITIVITY_CSV_PATH = Path(
    "data/exports/validation/clean_event_threshold_sensitivity.csv"
)
DEFAULT_THRESHOLD_SENSITIVITY_MD_PATH = Path(
    "data/exports/validation/clean_event_threshold_sensitivity.md"
)
DEFAULT_YFINANCE_OUTPUT_PATH = Path("data/imports/market_data/yfinance_market_data.csv")
DEFAULT_YFINANCE_SUMMARY_MD_PATH = Path("data/exports/market_data/yfinance_fetch_summary.md")
DEFAULT_YFINANCE_SUMMARY_CSV_PATH = Path("data/exports/market_data/yfinance_fetch_summary.csv")
DEFAULT_TICKER_ALIASES_PATH = Path("data/seeds/ticker_aliases.csv")
DEFAULT_MARKET_DATA_IMPORT_INPUT_PATH = DEFAULT_YFINANCE_OUTPUT_PATH
DEFAULT_EVENT_STUDY_EVENTS_INPUT_PATH = DEFAULT_CLEAN_AUTO_LABEL_OUTPUT_PATH
DEFAULT_EVENT_STUDY_OUTPUT_PATH = Path("data/exports/event_study/event_study_results.csv")
DEFAULT_EVENT_STUDY_SUMMARY_MD_PATH = Path("data/exports/event_study/event_study_summary.md")
DEFAULT_EVENT_STUDY_MATCH_DIAGNOSTICS_CSV_PATH = Path(
    "data/exports/event_study/event_study_match_diagnostics.csv"
)
DEFAULT_EVENT_STUDY_MATCH_DIAGNOSTICS_MD_PATH = Path(
    "data/exports/event_study/event_study_match_diagnostics.md"
)
DEFAULT_REPORTING_MAIN_TABLE_CSV_PATH = Path("data/exports/reporting/event_study_main_table.csv")
DEFAULT_REPORTING_MAIN_TABLE_MD_PATH = Path("data/exports/reporting/event_study_main_table.md")
DEFAULT_REPORTING_BY_CREATOR_CSV_PATH = Path("data/exports/reporting/event_study_by_creator.csv")
DEFAULT_REPORTING_BY_TICKER_CSV_PATH = Path("data/exports/reporting/event_study_by_ticker.csv")
DEFAULT_REPORTING_BY_YEAR_CSV_PATH = Path("data/exports/reporting/event_study_by_year.csv")
DEFAULT_REPORTING_BY_RECOMMENDATION_TYPE_CSV_PATH = Path(
    "data/exports/reporting/event_study_by_recommendation_type.csv"
)
DEFAULT_REPORTING_BY_DIRECTION_CSV_PATH = Path("data/exports/reporting/event_study_by_direction.csv")
DEFAULT_REPORTING_ROBUSTNESS_CSV_PATH = Path(
    "data/exports/reporting/event_study_robustness_thresholds.csv"
)
DEFAULT_REPORTING_SUMMARY_MD_PATH = Path("data/exports/reporting/event_study_report_summary.md")
DEFAULT_REPORTING_METHODOLOGY_NOTE_PATH = Path(
    "data/exports/reporting/methodology_note_yfinance_prototype.md"
)
DEFAULT_REPORTING_CHARTS_DIR = Path("data/exports/reporting/charts")
DEFAULT_INTRADAY_FEASIBILITY_PATH = Path("data/exports/intraday/intraday_event_feasibility.csv")
DEFAULT_INTRADAY_FEASIBILITY_SUMMARY_MD_PATH = Path(
    "data/exports/intraday/intraday_event_feasibility_summary.md"
)
DEFAULT_INTRADAY_MARKET_DATA_PATH = Path("data/imports/market_data/yfinance_intraday_market_data.csv")
DEFAULT_INTRADAY_FETCH_SUMMARY_MD_PATH = Path("data/exports/intraday/yfinance_intraday_fetch_summary.md")
DEFAULT_INTRADAY_FETCH_SUMMARY_CSV_PATH = Path(
    "data/exports/intraday/yfinance_intraday_fetch_summary.csv"
)
DEFAULT_INTRADAY_EVENT_STUDY_OUTPUT_PATH = Path("data/exports/intraday/intraday_event_study_results.csv")
DEFAULT_INTRADAY_EVENT_STUDY_SUMMARY_MD_PATH = Path(
    "data/exports/intraday/intraday_event_study_summary.md"
)
DEFAULT_INTRADAY_BY_CREATOR_PATH = Path("data/exports/intraday/intraday_event_study_by_creator.csv")
DEFAULT_INTRADAY_BY_TICKER_PATH = Path("data/exports/intraday/intraday_event_study_by_ticker.csv")
DEFAULT_INTRADAY_METHOD_NOTE_PATH = Path("data/exports/intraday/intraday_methodology_note.md")
DEFAULT_INTRADAY_CHARTS_DIR = Path("data/exports/intraday/charts")
DEFAULT_SLOW_TRANSCRIPT_QUEUE_PATH = Path("data/exports/transcripts/slow_youtube_transcript_queue.csv")
DEFAULT_SLOW_TRANSCRIPT_QUEUE_MD_PATH = Path("data/exports/transcripts/slow_youtube_transcript_queue.md")
DEFAULT_SLOW_COLLECTION_SUMMARY_CSV_PATH = Path(
    "data/exports/transcripts/slow_youtube_collection_summary.csv"
)
DEFAULT_SLOW_COLLECTION_SUMMARY_MD_PATH = Path(
    "data/exports/transcripts/slow_youtube_collection_summary.md"
)
DEFAULT_MANUAL_TRANSCRIPT_PACKET_PATH = Path("data/exports/transcripts/manual_collection_packet.csv")
DEFAULT_MANUAL_TRANSCRIPT_PACKET_MD_PATH = Path("data/exports/transcripts/manual_collection_packet.md")
DEFAULT_MANUAL_TRANSCRIPT_TEMPLATE_PATH = Path("data/imports/manual_transcripts_template.csv")
DEFAULT_SLOW_COLLECTION_DAILY_PLAN_PATH = Path("data/exports/transcripts/slow_collection_daily_plan.md")
DEFAULT_X_EXTENSION_COST_PLAN_CSV_PATH = Path("data/exports/x_extension/x_extension_cost_plan.csv")
DEFAULT_X_EXTENSION_COST_PLAN_MD_PATH = Path("data/exports/x_extension/x_extension_cost_plan.md")
DEFAULT_X_EXTENSION_QUERIES_CSV_PATH = Path("data/exports/x_extension/x_candidate_queries.csv")
DEFAULT_X_CREATOR_CANDIDATES_PATH = Path("data/seeds/x_creator_candidates.csv")
OVERNIGHT_LOG_PATH_OPTION = typer.Option(
    DEFAULT_OVERNIGHT_LOG_PATH,
    help="Path to overnight collection log file.",
)
OVERNIGHT_SUMMARY_PATH_OPTION = typer.Option(
    DEFAULT_OVERNIGHT_SUMMARY_PATH,
    help="Path to overnight collection summary file.",
)
TRANSCRIPT_VENDOR_OUTPUT_OPTION = typer.Option(
    DEFAULT_TRANSCRIPT_VENDOR_BATCH_OUTPUT,
    help="CSV output path.",
)
PROVIDER_INPUT_OPTION = typer.Option(
    DEFAULT_TRANSCRIPT_VENDOR_BATCH_OUTPUT,
    "--input",
    "--input-path",
    help="Provider input CSV with video_id and url columns.",
)
PROVIDER_OUTPUT_OPTION = typer.Option(
    DEFAULT_PROVIDER_TRANSCRIPT_OUTPUT,
    help="Import-compatible provider transcript CSV output path.",
)
AUTOPILOT_RETRY_STATUS_OPTION = typer.Option(
    None,
    "--retry-status",
    help="Provider failure status to retry. Repeatable. Defaults to http_408 only.",
)
AUTOPILOT_RESUME_OPTION = typer.Option(
    None,
    "--resume",
    help="Existing provider autopilot run directory to continue.",
)
TRANSCRIPT_IMPORT_PATH_OPTION = typer.Option(..., help="Transcript CSV import path.")
MAX_CATEGORY_SHARE_OPTION = typer.Option(
    None,
    help="Category share cap as category:share, repeatable.",
)
MANUAL_TRANSCRIPT_IMPORT_PATH_OPTION = typer.Option(
    Path("data/imports/manual_transcripts.csv"),
    "--input",
    "--path",
    help="Manual transcript CSV import path.",
)
FREE_TARGET_CREDIT_OUTPUT_OPTION = typer.Option(
    Path("data/exports/remaining_18_credit_targets.csv"),
    help="CSV output for remaining TranscriptAPI credit targets.",
)
FREE_TARGET_MANUAL_OUTPUT_OPTION = typer.Option(
    Path("data/exports/manual_transcript_targets.csv"),
    help="CSV output for manual transcript collection targets.",
)
FREE_TARGET_TEMPLATE_OUTPUT_OPTION = typer.Option(
    Path("data/templates/manual_transcripts_to_import_template.csv"),
    help="Manual transcript import template path.",
)
FREE_TARGET_METHODS_OUTPUT_OPTION = typer.Option(
    Path("data/exports/report_ready/free_transcript_expansion_methods.txt"),
    help="Report-ready methods text output path.",
)
NEXT_PAID_BATCH_OUTPUT_OPTION = typer.Option(
    Path("data/exports/transcripts/next_paid_transcript_batch_61.csv"),
    "--output",
    help="CSV output path.",
)
SLOW_QUEUE_OUTPUT_OPTION = typer.Option(
    DEFAULT_SLOW_TRANSCRIPT_QUEUE_PATH,
    "--output",
    help="Queue CSV output path.",
)
SLOW_QUEUE_MD_OPTION = typer.Option(
    DEFAULT_SLOW_TRANSCRIPT_QUEUE_MD_PATH,
    "--summary-md",
    help="Queue summary markdown path.",
)
SLOW_COLLECT_INPUT_OPTION = typer.Option(
    DEFAULT_SLOW_TRANSCRIPT_QUEUE_PATH,
    "--input",
    help="Queue CSV input path.",
)
SLOW_COLLECT_SUMMARY_CSV_OPTION = typer.Option(
    DEFAULT_SLOW_COLLECTION_SUMMARY_CSV_PATH,
    "--summary-csv",
    help="Summary CSV output path.",
)
SLOW_COLLECT_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_SLOW_COLLECTION_SUMMARY_MD_PATH,
    "--summary-md",
    help="Summary markdown output path.",
)
MANUAL_PACKET_OUTPUT_CSV_OPTION = typer.Option(
    DEFAULT_MANUAL_TRANSCRIPT_PACKET_PATH,
    "--output-csv",
    help="Packet CSV output path.",
)
MANUAL_PACKET_OUTPUT_MD_OPTION = typer.Option(
    DEFAULT_MANUAL_TRANSCRIPT_PACKET_MD_PATH,
    "--output-md",
    help="Packet markdown output path.",
)
MANUAL_PACKET_TEMPLATE_OPTION = typer.Option(
    DEFAULT_MANUAL_TRANSCRIPT_TEMPLATE_PATH,
    "--template",
    help="Template CSV output path.",
)
SLOW_DAILY_PLAN_OUTPUT_OPTION = typer.Option(
    DEFAULT_SLOW_COLLECTION_DAILY_PLAN_PATH,
    "--output",
    help="Daily plan markdown output path.",
)
NEXT_PAID_BATCH_MD_OPTION = typer.Option(
    Path("data/exports/transcripts/next_paid_transcript_batch_61.md"),
    "--summary-md",
    help="Markdown output path.",
)
PAID_BATCH_INPUT_OPTION = typer.Option(
    Path("data/exports/transcripts/next_paid_transcript_batch_61.csv"),
    "--input",
    help="Planned paid transcript batch CSV.",
)
TRANSCRIPT_PROVENANCE_OUTPUT_OPTION = typer.Option(
    Path("data/exports/transcripts/transcript_provenance_summary.csv"),
    "--output",
    help="CSV output path.",
)
TRANSCRIPT_PROVENANCE_MD_OPTION = typer.Option(
    Path("data/exports/transcripts/transcript_provenance_summary.md"),
    "--summary-md",
    help="Markdown output path.",
)
TRANSCRIPT_METHODOLOGY_NOTE_OPTION = typer.Option(
    Path("data/exports/transcripts/transcript_collection_methodology_note.md"),
    "--methodology-note",
    help="Paper-facing methodology note path.",
)
EXPANDED_TRANSCRIPT_COVERAGE_OUTPUT_OPTION = typer.Option(
    Path("data/exports/transcripts/expanded_transcript_coverage_summary.csv"),
    "--output",
    help="Expanded transcript coverage CSV output path.",
)
EXPANDED_TRANSCRIPT_COVERAGE_MD_OPTION = typer.Option(
    Path("data/exports/transcripts/expanded_transcript_coverage_summary.md"),
    "--summary-md",
    help="Expanded transcript coverage Markdown output path.",
)
NEW_TRANSCRIPT_EVENT_EXTRACTION_CSV_OPTION = typer.Option(
    Path("data/exports/transcripts/new_transcript_event_extraction_summary.csv"),
    "--summary-csv",
    help="New transcript extraction summary CSV path.",
)
NEW_TRANSCRIPT_EVENT_EXTRACTION_MD_OPTION = typer.Option(
    Path("data/exports/transcripts/new_transcript_event_extraction_summary.md"),
    "--summary-md",
    help="New transcript extraction summary Markdown path.",
)
EXPANDED_ROBUSTNESS_DIR_OPTION = typer.Option(
    Path("data/exports/expanded_robustness"),
    "--output-dir",
    help="Expanded robustness output directory.",
)
AUTO_LABEL_INPUT_OPTION = typer.Option(
    DEFAULT_AUTO_LABEL_INPUT_PATH,
    "--input",
    help="Raw validation sample CSV path.",
)
AUTO_LABEL_OUTPUT_OPTION = typer.Option(
    DEFAULT_AUTO_LABEL_OUTPUT_PATH,
    "--output",
    help="Auto-labeled validation CSV output path.",
)
AUTO_LABEL_REVIEW_OPTION = typer.Option(
    DEFAULT_AUTO_LABEL_REVIEW_PATH,
    "--review-output",
    help="Review-needed CSV output path.",
)
AUTO_LABEL_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_AUTO_LABEL_SUMMARY_MD_PATH,
    "--summary-md",
    help="Markdown summary output path.",
)
AUTO_LABEL_SUMMARY_CSV_OPTION = typer.Option(
    DEFAULT_AUTO_LABEL_SUMMARY_CSV_PATH,
    "--summary-csv",
    help="CSV summary output path.",
)
CLEAN_AUTO_LABEL_INPUT_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_INPUT_PATH,
    "--input",
    help="Auto-labeled validation CSV input path.",
)
CLEAN_AUTO_LABEL_EVENTS_INPUT_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_EVENTS_INPUT_PATH,
    "--events-input",
    help="Optional transcript recommendation events export used to fill missing event fields.",
)
CLEAN_AUTO_LABEL_OUTPUT_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_OUTPUT_PATH,
    "--output",
    help="Clean auto-labeled events CSV output path.",
)
CLEAN_AUTO_LABEL_EXCLUSIONS_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_EXCLUSIONS_PATH,
    "--exclusions-output",
    help="Excluded rows CSV output path.",
)
CLEAN_AUTO_LABEL_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_SUMMARY_MD_PATH,
    "--summary-md",
    help="Markdown summary output path.",
)
MARKET_DATA_REQUEST_INPUT_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_REQUEST_INPUT_PATH,
    "--input",
    help="Clean auto-labeled events CSV input path.",
)
MARKET_DATA_REQUEST_OUTPUT_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_REQUEST_OUTPUT_PATH,
    "--output",
    help="Market-data request CSV output path.",
)
MARKET_DATA_UNIQUE_TICKERS_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_UNIQUE_TICKERS_PATH,
    "--unique-tickers-output",
    help="Unique tickers CSV output path.",
)
MARKET_DATA_EVENT_DATES_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_EVENT_DATES_PATH,
    "--event-dates-output",
    help="Event dates by ticker CSV output path.",
)
MARKET_DATA_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_SUMMARY_MD_PATH,
    "--summary-md",
    help="Market-data request Markdown summary path.",
)
THRESHOLD_SENSITIVITY_INPUT_OPTION = typer.Option(
    DEFAULT_THRESHOLD_SENSITIVITY_INPUT_PATH,
    "--input",
    help="Auto-labeled validation CSV input path.",
)
THRESHOLD_SENSITIVITY_CSV_OPTION = typer.Option(
    DEFAULT_THRESHOLD_SENSITIVITY_CSV_PATH,
    "--output",
    help="Threshold sensitivity CSV output path.",
)
THRESHOLD_SENSITIVITY_MD_OPTION = typer.Option(
    DEFAULT_THRESHOLD_SENSITIVITY_MD_PATH,
    "--summary-md",
    help="Threshold sensitivity Markdown summary path.",
)
YFINANCE_INPUT_REQUEST_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_REQUEST_OUTPUT_PATH,
    "--input-request",
    help="Market-data request CSV input path.",
)
YFINANCE_INPUT_TICKERS_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_UNIQUE_TICKERS_PATH,
    "--input-tickers",
    help="Unique tickers CSV input path.",
)
YFINANCE_OUTPUT_OPTION = typer.Option(
    DEFAULT_YFINANCE_OUTPUT_PATH,
    "--output",
    help="Interim yfinance market-data CSV output path.",
)
YFINANCE_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_YFINANCE_SUMMARY_MD_PATH,
    "--summary-md",
    help="yfinance fetch Markdown summary path.",
)
YFINANCE_SUMMARY_CSV_OPTION = typer.Option(
    DEFAULT_YFINANCE_SUMMARY_CSV_PATH,
    "--summary-csv",
    help="yfinance fetch CSV summary path.",
)
YFINANCE_TICKER_ALIASES_OPTION = typer.Option(
    DEFAULT_TICKER_ALIASES_PATH,
    "--ticker-aliases",
    help="Optional ticker alias CSV path for mapping event tickers to market-data tickers.",
)
MARKET_DATA_IMPORT_INPUT_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_IMPORT_INPUT_PATH,
    "--input",
    help="Bloomberg-style market-data import CSV path.",
)
EVENT_STUDY_EVENTS_INPUT_OPTION = typer.Option(
    DEFAULT_EVENT_STUDY_EVENTS_INPUT_PATH,
    "--input-events",
    help="Clean events input CSV path.",
)
EVENT_STUDY_MARKET_DATA_INPUT_OPTION = typer.Option(
    None,
    "--input-market-data",
    help="Explicit Bloomberg-style market-data input CSV path.",
)
EVENT_STUDY_OUTPUT_OPTION = typer.Option(
    DEFAULT_EVENT_STUDY_OUTPUT_PATH,
    "--output",
    help="Event-study prototype CSV output path.",
)
EVENT_STUDY_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_EVENT_STUDY_SUMMARY_MD_PATH,
    "--summary-md",
    help="Event-study prototype Markdown summary path.",
)
EVENT_STUDY_TICKER_ALIASES_OPTION = typer.Option(
    DEFAULT_TICKER_ALIASES_PATH,
    "--ticker-aliases",
    help="Optional ticker alias CSV path for matching event tickers to market-data tickers.",
)
EVENT_STUDY_MATCH_DIAGNOSTICS_CSV_OPTION = typer.Option(
    DEFAULT_EVENT_STUDY_MATCH_DIAGNOSTICS_CSV_PATH,
    "--output",
    help="Event-study match diagnostics CSV output path.",
)
EVENT_STUDY_MATCH_DIAGNOSTICS_MD_OPTION = typer.Option(
    DEFAULT_EVENT_STUDY_MATCH_DIAGNOSTICS_MD_PATH,
    "--summary-md",
    help="Event-study match diagnostics Markdown summary path.",
)
REPORTING_MAIN_TABLE_CSV_OPTION = typer.Option(
    DEFAULT_REPORTING_MAIN_TABLE_CSV_PATH,
    "--main-table-csv",
    help="Main event-study reporting table CSV output path.",
)
REPORTING_MAIN_TABLE_MD_OPTION = typer.Option(
    DEFAULT_REPORTING_MAIN_TABLE_MD_PATH,
    "--main-table-md",
    help="Main event-study reporting table Markdown output path.",
)
REPORTING_BY_CREATOR_CSV_OPTION = typer.Option(
    DEFAULT_REPORTING_BY_CREATOR_CSV_PATH,
    "--by-creator-csv",
    help="Grouped event-study report by creator.",
)
REPORTING_BY_TICKER_CSV_OPTION = typer.Option(
    DEFAULT_REPORTING_BY_TICKER_CSV_PATH,
    "--by-ticker-csv",
    help="Grouped event-study report by ticker.",
)
REPORTING_BY_YEAR_CSV_OPTION = typer.Option(
    DEFAULT_REPORTING_BY_YEAR_CSV_PATH,
    "--by-year-csv",
    help="Grouped event-study report by year.",
)
REPORTING_BY_RECOMMENDATION_TYPE_CSV_OPTION = typer.Option(
    DEFAULT_REPORTING_BY_RECOMMENDATION_TYPE_CSV_PATH,
    "--by-recommendation-type-csv",
    help="Grouped event-study report by recommendation type.",
)
REPORTING_BY_DIRECTION_CSV_OPTION = typer.Option(
    DEFAULT_REPORTING_BY_DIRECTION_CSV_PATH,
    "--by-direction-csv",
    help="Grouped event-study report by direction.",
)
REPORTING_ROBUSTNESS_CSV_OPTION = typer.Option(
    DEFAULT_REPORTING_ROBUSTNESS_CSV_PATH,
    "--robustness-csv",
    help="Threshold robustness CSV output path.",
)
REPORTING_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_REPORTING_SUMMARY_MD_PATH,
    "--summary-md",
    help="Event-study reporting Markdown summary path.",
)
REPORTING_METHODOLOGY_NOTE_OPTION = typer.Option(
    DEFAULT_REPORTING_METHODOLOGY_NOTE_PATH,
    "--methodology-note",
    help="Methodology note Markdown output path.",
)
REPORTING_CHARTS_DIR_OPTION = typer.Option(
    DEFAULT_REPORTING_CHARTS_DIR,
    "--output-dir",
    help="Output directory for event-study PNG charts.",
)
EVENT_STUDY_REPORTING_INPUT_RESULTS_OPTION = typer.Option(
    DEFAULT_EVENT_STUDY_OUTPUT_PATH,
    "--input-results",
    help="Event-study results CSV input path.",
)
EVENT_STUDY_REPORTING_INPUT_CLEAN_EVENTS_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_OUTPUT_PATH,
    "--input-clean-events",
    help="Clean auto-labeled events CSV input path.",
)
EVENT_STUDY_REPORTING_INPUT_MARKET_DATA_OPTION = typer.Option(
    DEFAULT_MARKET_DATA_IMPORT_INPUT_PATH,
    "--input-market-data",
    help="Market-data CSV input path.",
)
EVENT_STUDY_REPORTING_INPUT_THRESHOLD_SENSITIVITY_OPTION = typer.Option(
    DEFAULT_THRESHOLD_SENSITIVITY_CSV_PATH,
    "--input-threshold-sensitivity",
    help="Threshold sensitivity CSV input path.",
)
EVENT_STUDY_REPORTING_INPUT_YFINANCE_SUMMARY_OPTION = typer.Option(
    DEFAULT_YFINANCE_SUMMARY_CSV_PATH,
    "--input-yfinance-summary",
    help="Optional yfinance fetch summary CSV input path.",
)
INTRADAY_FEASIBILITY_INPUT_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_OUTPUT_PATH,
    "--input",
    help="Clean auto-labeled events CSV input path.",
)
INTRADAY_FEASIBILITY_OUTPUT_OPTION = typer.Option(
    DEFAULT_INTRADAY_FEASIBILITY_PATH,
    "--output",
    help="Intraday feasibility CSV output path.",
)
INTRADAY_FEASIBILITY_SUMMARY_OPTION = typer.Option(
    DEFAULT_INTRADAY_FEASIBILITY_SUMMARY_MD_PATH,
    "--summary-md",
    help="Intraday feasibility Markdown summary path.",
)
INTRADAY_FEASIBILITY_ALIASES_OPTION = typer.Option(
    DEFAULT_TICKER_ALIASES_PATH,
    "--ticker-aliases",
    help="Ticker alias CSV path.",
)
INTRADAY_FETCH_INPUT_OPTION = typer.Option(
    DEFAULT_INTRADAY_FEASIBILITY_PATH,
    "--input-feasibility",
    help="Intraday feasibility CSV input path.",
)
INTRADAY_FETCH_OUTPUT_OPTION = typer.Option(
    DEFAULT_INTRADAY_MARKET_DATA_PATH,
    "--output",
    help="Intraday market-data CSV output path.",
)
INTRADAY_FETCH_SUMMARY_MD_OPTION = typer.Option(
    DEFAULT_INTRADAY_FETCH_SUMMARY_MD_PATH,
    "--summary-md",
    help="Intraday yfinance fetch summary Markdown path.",
)
INTRADAY_FETCH_SUMMARY_CSV_OPTION = typer.Option(
    DEFAULT_INTRADAY_FETCH_SUMMARY_CSV_PATH,
    "--summary-csv",
    help="Intraday yfinance fetch summary CSV path.",
)
INTRADAY_EVENT_STUDY_EVENTS_OPTION = typer.Option(
    DEFAULT_CLEAN_AUTO_LABEL_OUTPUT_PATH,
    "--input-events",
    help="Clean events CSV input path.",
)
INTRADAY_EVENT_STUDY_MARKET_DATA_OPTION = typer.Option(
    DEFAULT_INTRADAY_MARKET_DATA_PATH,
    "--input-market-data",
    help="Intraday market-data CSV input path.",
)
INTRADAY_EVENT_STUDY_OUTPUT_OPTION = typer.Option(
    DEFAULT_INTRADAY_EVENT_STUDY_OUTPUT_PATH,
    "--output",
    help="Intraday event-study results CSV output path.",
)
INTRADAY_EVENT_STUDY_SUMMARY_OPTION = typer.Option(
    DEFAULT_INTRADAY_EVENT_STUDY_SUMMARY_MD_PATH,
    "--summary-md",
    help="Intraday event-study summary Markdown path.",
)
INTRADAY_EVENT_STUDY_BY_CREATOR_OPTION = typer.Option(
    DEFAULT_INTRADAY_BY_CREATOR_PATH,
    "--by-creator-output",
    help="Intraday event-study by-creator CSV output path.",
)
INTRADAY_EVENT_STUDY_BY_TICKER_OPTION = typer.Option(
    DEFAULT_INTRADAY_BY_TICKER_PATH,
    "--by-ticker-output",
    help="Intraday event-study by-ticker CSV output path.",
)
INTRADAY_EVENT_STUDY_METHOD_NOTE_OPTION = typer.Option(
    DEFAULT_INTRADAY_METHOD_NOTE_PATH,
    "--methodology-note",
    help="Intraday methodology note output path.",
)
INTRADAY_CHART_INPUT_OPTION = typer.Option(
    DEFAULT_INTRADAY_EVENT_STUDY_OUTPUT_PATH,
    "--input-results",
    help="Intraday event-study results CSV input path.",
)
INTRADAY_CHART_OUTPUT_DIR_OPTION = typer.Option(
    DEFAULT_INTRADAY_CHARTS_DIR,
    "--output-dir",
    help="Intraday chart output directory.",
)
X_EXTENSION_SEED_OPTION = typer.Option(
    DEFAULT_X_CREATOR_CANDIDATES_PATH,
    "--seed-path",
    help="X candidate creator seed CSV path.",
)
X_EXTENSION_OUTPUT_CSV_OPTION = typer.Option(
    DEFAULT_X_EXTENSION_COST_PLAN_CSV_PATH,
    "--output",
    help="X extension cost plan CSV output path.",
)
X_EXTENSION_OUTPUT_MD_OPTION = typer.Option(
    DEFAULT_X_EXTENSION_COST_PLAN_MD_PATH,
    "--summary-md",
    help="X extension cost plan Markdown output path.",
)
X_EXTENSION_QUERIES_OUTPUT_OPTION = typer.Option(
    DEFAULT_X_EXTENSION_QUERIES_CSV_PATH,
    "--queries-output",
    help="X candidate query template CSV output path.",
)


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
    from .youtube_quota import (
        estimate_youtube_history_seed_quota,
        estimate_youtube_seed_quota_units,
        seed_requires_search_list,
    )

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
    seed_table = Table(title="Selected YouTube Pilot Channels")
    seed_table.add_column("Channel")
    seed_table.add_column("Identifier", no_wrap=True)
    seed_table.add_column("search.list?", no_wrap=True)
    seed_table.add_column("Quota units", justify="right", no_wrap=True)
    for row in load_youtube_seed_rows()[:max_channels]:
        identifier = row.collection_identifier
        seed_table.add_row(
            row.channel_name or identifier,
            identifier,
            "yes" if seed_requires_search_list(identifier) else "no",
            str(estimate_youtube_seed_quota_units(identifier, max_pages)),
        )
    console.print(seed_table)
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


@app.command("collect-youtube-transcripts")
def collect_youtube_transcripts_command(
    limit: int | None = typer.Option(None, min=1, help="Maximum videos to attempt."),
    only_candidates: bool = typer.Option(
        True,
        "--only-candidates/--all-videos",
        help="Attempt only YouTube metadata recommendation candidates or all videos.",
    ),
    dry_run: bool = typer.Option(False, help="Print selected videos without fetching transcripts."),
    from_queue: bool = typer.Option(
        False, "--from-queue", help="Collect from transcript_fetch_queue with safety controls."
    ),
    sleep_seconds: float = typer.Option(
        3.0, min=0.0, help="Seconds to sleep between transcript fetches."
    ),
    jitter_seconds: float = typer.Option(
        1.0, min=0.0, help="Random jitter added to sleep seconds."
    ),
    stop_on_block: bool = typer.Option(
        True, help="Stop on ip_blocked or request_blocked."
    ),
    creator_diversify: bool = typer.Option(
        False, help="Diversify across creators rather than strict priority order."
    ),
    max_per_creator: int = typer.Option(
        0, min=0, help="Max transcripts per creator in this run (0=no limit). Requires --creator-diversify and --from-queue."
    ),
    allow_translation: bool = typer.Option(
        False, help="Fall back to translatable non-English transcripts when English is unavailable."
    ),
    min_disk_mb: int = typer.Option(
        500, min=0, help="Stop collection if free disk falls below this threshold in MB."
    ),
) -> None:
    from .youtube_transcripts import collect_transcripts_for_videos, collect_transcripts_from_queue

    if from_queue:
        result = collect_transcripts_from_queue(
            limit=limit or get_settings().transcript_queue_max_live_fetches,
            sleep_seconds=sleep_seconds,
            jitter_seconds=jitter_seconds,
            stop_on_block=stop_on_block,
            dry_run=dry_run,
            allow_translation=allow_translation,
            creator_diversify=creator_diversify,
            max_per_creator=max_per_creator,
            min_disk_mb=min_disk_mb,
        )
    else:
        result = collect_transcripts_for_videos(
            limit=limit,
            only_candidates=only_candidates,
            dry_run=dry_run,
        )
    console.print(
        "YouTube transcript selection: "
        f"selected={result.selected_count}, "
        f"only_candidates={only_candidates or ''}, "
        f"limit={limit or get_settings().youtube_transcript_max_videos_per_run}."
    )
    table = Table(title="Selected Transcript Videos")
    table.add_column("Video ID", no_wrap=True)
    table.add_column("Channel")
    table.add_column("Published")
    table.add_column("Title")
    for video in result.selected_videos:
        table.add_row(
            video.video_id,
            video.channel_title or "",
            video.published_at or "",
            video.title or "",
        )
    console.print(table)
    if dry_run:
        console.print("Dry run only; no transcript fetches or database writes were made.")
        return
    console.print(
        "Transcript collection complete: "
        f"attempted={result.attempted_count}, "
        f"available={result.available_count}, "
        f"statuses={result.status_counts}."
    )
    if result.stopped_reason:
        console.print(f"Stopped early because transcript provider returned {result.stopped_reason}.")


@app.command("build-transcript-events")
def build_transcript_events_command(
    refresh_existing: bool = typer.Option(False, help="Delete and rebuild transcript events/windows."),
) -> None:
    from .transcript_classify import build_transcript_recommendation_events

    result = build_transcript_recommendation_events(refresh_existing=refresh_existing)
    console.print(
        "Transcript event build complete. "
        f"Evaluated {result.candidate_windows} candidate windows and "
        f"inserted {result.events} transcript recommendation events."
    )


@app.command("export-transcript-events")
def export_transcript_events_command() -> None:
    from .transcript_exports import export_transcript_events

    paths = export_transcript_events()
    for name, path in paths.items():
        console.print(f"{name}: {path}")


@app.command("build-event-validation-sample")
def build_event_validation_sample_command(
    sample_size: int = typer.Option(150, min=1, help="Number of events to sample."),
    seed: int = typer.Option(496, help="Deterministic random seed for sampling."),
) -> None:
    from .event_validation import build_event_validation_sample

    result = build_event_validation_sample(sample_size=sample_size, seed=seed)
    console.print(
        "Event validation sample complete: "
        f"rows={result.row_count}, total_events={result.total_events}."
    )
    console.print(f"sample: {result.sample_path}")
    console.print(f"readme: {result.readme_path}")


@app.command("summarize-event-validation")
def summarize_event_validation_command() -> None:
    from .event_validation import summarize_event_validation

    try:
        result = summarize_event_validation()
    except FileNotFoundError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Event validation summary complete: "
        f"sample_size={result.sample_size}, labeled={result.labeled_count}."
    )
    console.print(f"source: {result.source_path}")
    console.print(f"summary_md: {result.markdown_path}")
    console.print(f"summary_csv: {result.csv_path}")


@app.command("auto-label-event-validation")
def auto_label_event_validation_command(
    input_path: Path = AUTO_LABEL_INPUT_OPTION,
    output_path: Path = AUTO_LABEL_OUTPUT_OPTION,
    review_output_path: Path = AUTO_LABEL_REVIEW_OPTION,
    summary_md_path: Path = AUTO_LABEL_SUMMARY_MD_OPTION,
    summary_csv_path: Path = AUTO_LABEL_SUMMARY_CSV_OPTION,
    method: str = typer.Option("hybrid", help="Labeling method: rules, hybrid, or llm."),
    seed: int = typer.Option(496, help="Deterministic row-processing seed."),
    min_auto_confidence: float = typer.Option(
        0.75,
        "--min-auto-confidence",
        min=0.0,
        max=1.0,
        help="Minimum confidence required before a row is excluded from review.",
    ),
    llm_model: str | None = typer.Option(
        None,
        "--llm-model",
        help="OpenAI model. Defaults to AUTO_LABEL_LLM_MODEL or gpt-4o-mini.",
    ),
    confirm_llm_run: bool = typer.Option(
        False,
        "--confirm-llm-run",
        help="Explicitly allow external LLM API calls for ambiguous rows.",
    ),
    dry_run: bool = typer.Option(False, help="Preview labels without writing output files."),
    limit: int | None = typer.Option(None, min=1, help="Maximum input rows to label."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Relabel rows even when an existing auto-labeled output is present.",
    ),
) -> None:
    from .auto_event_labeling import auto_label_event_validation

    try:
        result = auto_label_event_validation(
            input_path=input_path,
            output_path=output_path,
            review_output_path=review_output_path,
            summary_md_path=summary_md_path,
            summary_csv_path=summary_csv_path,
            method=method,
            seed=seed,
            min_auto_confidence=min_auto_confidence,
            llm_model=llm_model,
            confirm_llm_run=confirm_llm_run,
            dry_run=dry_run,
            limit=limit,
            force=force,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Auto-labeling complete: "
        f"rows={result.total_rows}, "
        f"yes={result.rows_labeled_yes}, "
        f"no={result.rows_labeled_no}, "
        f"unclear={result.rows_labeled_unclear}, "
        f"rules={result.rows_labeled_by_rules}, "
        f"llm={result.rows_labeled_by_llm}, "
        f"review_needed={result.rows_needing_review}."
    )
    if result.dry_run:
        console.print("Dry run only; no output files were written and no LLM calls were made.")
        return
    console.print(f"output: {result.output_path}")
    console.print(f"review_output: {result.review_output_path}")
    console.print(f"summary_md: {result.summary_md_path}")
    console.print(f"summary_csv: {result.summary_csv_path}")


@app.command("build-clean-auto-labeled-events")
def build_clean_auto_labeled_events_command(
    input_path: Path = CLEAN_AUTO_LABEL_INPUT_OPTION,
    events_input_path: Path = CLEAN_AUTO_LABEL_EVENTS_INPUT_OPTION,
    output_path: Path = CLEAN_AUTO_LABEL_OUTPUT_OPTION,
    exclusions_output_path: Path = CLEAN_AUTO_LABEL_EXCLUSIONS_OPTION,
    summary_md_path: Path = CLEAN_AUTO_LABEL_SUMMARY_MD_OPTION,
    min_confidence: float = typer.Option(
        0.75,
        "--min-confidence",
        min=0.0,
        max=1.0,
        help="Minimum auto-label confidence for inclusion.",
    ),
    include_weak_evidence: bool = typer.Option(
        False,
        "--include-weak-evidence",
        help="Allow weak evidence rows into the clean event dataset.",
    ),
    include_review_needed: bool = typer.Option(
        False,
        "--include-review-needed",
        help="Allow rows flagged for review into the clean event dataset.",
    ),
    dry_run: bool = typer.Option(False, help="Preview clean/exclusion counts without writing files."),
) -> None:
    from .auto_event_labeling import build_clean_auto_labeled_events

    try:
        result = build_clean_auto_labeled_events(
            input_path=input_path,
            events_input_path=events_input_path,
            output_path=output_path,
            exclusions_output_path=exclusions_output_path,
            summary_md_path=summary_md_path,
            min_confidence=min_confidence,
            include_weak_evidence=include_weak_evidence,
            include_review_needed=include_review_needed,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Clean auto-labeled event build complete: "
        f"included={result.included_rows}, excluded={result.excluded_rows}."
    )
    if result.dry_run:
        console.print("Dry run only; no output files were written.")
        return
    console.print(f"output: {result.output_path}")
    console.print(f"exclusions: {result.exclusions_output_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("build-market-data-request")
def build_market_data_request_command(
    input_path: Path = MARKET_DATA_REQUEST_INPUT_OPTION,
    output_path: Path = MARKET_DATA_REQUEST_OUTPUT_OPTION,
    unique_tickers_path: Path = MARKET_DATA_UNIQUE_TICKERS_OPTION,
    event_dates_by_ticker_path: Path = MARKET_DATA_EVENT_DATES_OPTION,
    summary_md_path: Path = MARKET_DATA_SUMMARY_MD_OPTION,
    preferred_benchmark: str = typer.Option("SPY", help="Preferred event-study benchmark ticker."),
) -> None:
    from .market_data_prep import build_market_data_request

    try:
        result = build_market_data_request(
            input_path=input_path,
            request_path=output_path,
            unique_tickers_path=unique_tickers_path,
            event_dates_by_ticker_path=event_dates_by_ticker_path,
            summary_md_path=summary_md_path,
            preferred_benchmark=preferred_benchmark,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Market-data request build complete: "
        f"clean_events={result.total_clean_events}, "
        f"unique_tickers={result.unique_ticker_count}, "
        f"min_event_date={result.min_event_date}, "
        f"max_event_date={result.max_event_date}."
    )
    console.print(f"request: {result.request_path}")
    console.print(f"unique_tickers: {result.unique_tickers_path}")
    console.print(f"event_dates_by_ticker: {result.event_dates_by_ticker_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("build-clean-event-threshold-sensitivity")
def build_clean_event_threshold_sensitivity_command(
    input_path: Path = THRESHOLD_SENSITIVITY_INPUT_OPTION,
    output_path: Path = THRESHOLD_SENSITIVITY_CSV_OPTION,
    summary_md_path: Path = THRESHOLD_SENSITIVITY_MD_OPTION,
) -> None:
    from .market_data_prep import build_clean_event_threshold_sensitivity

    try:
        result = build_clean_event_threshold_sensitivity(
            input_path=input_path,
            csv_path=output_path,
            markdown_path=summary_md_path,
        )
    except FileNotFoundError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Clean event threshold sensitivity complete: "
        f"input_rows={result.total_rows}, threshold_rows={result.threshold_rows}."
    )
    console.print(f"csv: {result.csv_path}")
    console.print(f"summary_md: {result.markdown_path}")


@app.command("fetch-yfinance-market-data")
def fetch_yfinance_market_data_command(
    input_request_path: Path = YFINANCE_INPUT_REQUEST_OPTION,
    input_tickers_path: Path = YFINANCE_INPUT_TICKERS_OPTION,
    output_path: Path = YFINANCE_OUTPUT_OPTION,
    summary_md_path: Path = YFINANCE_SUMMARY_MD_OPTION,
    summary_csv_path: Path = YFINANCE_SUMMARY_CSV_OPTION,
    ticker_aliases_path: Path = YFINANCE_TICKER_ALIASES_OPTION,
    benchmark: str = typer.Option("SPY", help="Benchmark ticker to download and merge."),
    buffer_days: int = typer.Option(10, min=0, help="Calendar-day buffer around request date range."),
    confirm_yfinance_run: bool = typer.Option(
        False,
        "--confirm-yfinance-run",
        help="Required to download interim Yahoo/yfinance data.",
    ),
    dry_run: bool = typer.Option(False, help="Preview request without calling yfinance."),
) -> None:
    from .yfinance_market_data import build_yfinance_fetch_plan, fetch_yfinance_market_data

    try:
        if dry_run:
            plan = build_yfinance_fetch_plan(
                input_request_path=input_request_path,
                input_tickers_path=input_tickers_path,
                output_path=output_path,
                summary_md_path=summary_md_path,
                summary_csv_path=summary_csv_path,
                ticker_aliases_path=ticker_aliases_path,
                benchmark=benchmark,
                buffer_days=buffer_days,
            )
            console.print("Dry run only; no yfinance/Yahoo downloads were made.")
            console.print(f"tickers: {', '.join(plan.tickers)}")
            if plan.alias_mappings:
                console.print(
                    "ticker_aliases: "
                    + ", ".join(f"{original}->{data}" for original, data in plan.alias_mappings)
                )
            else:
                console.print("ticker_aliases: none")
            console.print(f"benchmark: {plan.benchmark}")
            console.print(f"date_range: {plan.start_date} to {plan.end_date}")
            console.print(f"output: {plan.output_path}")
            console.print(f"summary_md: {plan.summary_md_path}")
            console.print(f"summary_csv: {plan.summary_csv_path}")
            return
        result = fetch_yfinance_market_data(
            input_request_path=input_request_path,
            input_tickers_path=input_tickers_path,
            output_path=output_path,
            summary_md_path=summary_md_path,
            summary_csv_path=summary_csv_path,
            ticker_aliases_path=ticker_aliases_path,
            benchmark=benchmark,
            buffer_days=buffer_days,
            confirm_yfinance_run=confirm_yfinance_run,
            dry_run=False,
        )
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Interim yfinance market-data fetch complete: "
        f"tickers_requested={result.tickers_requested}, "
        f"tickers_downloaded={result.tickers_downloaded}, "
        f"failed_tickers={len(result.failed_tickers)}, "
        f"rows={result.rows_written}."
    )
    console.print("Warning: using interim Yahoo/yfinance data, not Bloomberg data.")
    if result.failed_tickers:
        console.print("failed_tickers: " + ", ".join(result.failed_tickers))
    console.print(f"output: {result.output_path}")
    console.print(f"summary_md: {result.summary_md_path}")
    console.print(f"summary_csv: {result.summary_csv_path}")


@app.command("validate-market-data-import")
def validate_market_data_import_command(
    input_path: Path = MARKET_DATA_IMPORT_INPUT_OPTION,
) -> None:
    from .event_study import validate_market_data_import

    try:
        result = validate_market_data_import(input_path=input_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Market-data import validation complete: "
        f"rows={result.row_count}, tickers={result.ticker_count}, "
        f"date_range={result.min_date} to {result.max_date}, "
        f"missing_adjusted_close={result.missing_adjusted_close_count}, "
        f"missing_benchmark={result.missing_benchmark_count}."
    )
    console.print("data_sources: " + ", ".join(result.data_sources))


@app.command("run-event-study")
def run_event_study_command(
    input_events: Path = EVENT_STUDY_EVENTS_INPUT_OPTION,
    input_market_data: Path | None = EVENT_STUDY_MARKET_DATA_INPUT_OPTION,
    market_data_source: str = typer.Option(
        "auto",
        "--market-data-source",
        help="Market-data source selection: auto, bloomberg, or yfinance.",
    ),
    ticker_aliases_path: Path = EVENT_STUDY_TICKER_ALIASES_OPTION,
    output_path: Path = EVENT_STUDY_OUTPUT_OPTION,
    summary_md_path: Path = EVENT_STUDY_SUMMARY_MD_OPTION,
) -> None:
    from .event_study import run_event_study

    try:
        result = run_event_study(
            input_events=input_events,
            input_market_data=input_market_data,
            market_data_source=market_data_source,
            ticker_aliases_path=ticker_aliases_path,
            output_path=output_path,
            summary_md_path=summary_md_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    if result.warning:
        console.print(result.warning)
    console.print(
        "Event-study prototype complete: "
        f"events_processed={result.events_processed}, events_matched={result.events_matched}."
    )
    console.print(f"market_data: {result.market_data_path}")
    console.print(f"output: {result.output_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("diagnose-event-study-matches")
def diagnose_event_study_matches_command(
    input_results: Path = EVENT_STUDY_REPORTING_INPUT_RESULTS_OPTION,
    input_clean_events: Path = EVENT_STUDY_REPORTING_INPUT_CLEAN_EVENTS_OPTION,
    input_market_data: Path = EVENT_STUDY_REPORTING_INPUT_MARKET_DATA_OPTION,
    ticker_aliases_path: Path = EVENT_STUDY_TICKER_ALIASES_OPTION,
    output_path: Path = EVENT_STUDY_MATCH_DIAGNOSTICS_CSV_OPTION,
    summary_md_path: Path = EVENT_STUDY_MATCH_DIAGNOSTICS_MD_OPTION,
) -> None:
    from .reporting import diagnose_event_study_matches

    try:
        result = diagnose_event_study_matches(
            event_study_results_path=input_results,
            clean_events_path=input_clean_events,
            market_data_path=input_market_data,
            ticker_aliases_path=ticker_aliases_path,
            output_csv_path=output_path,
            output_md_path=summary_md_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Event-study match diagnostics complete: "
        f"total_clean_events={result.total_clean_events}, "
        f"matched_events={result.matched_events}, "
        f"unmatched_events={result.unmatched_events}."
    )
    if result.unmatched_reason_counts:
        console.print(
            "unmatched_reason_counts: "
            + ", ".join(f"{reason}={count}" for reason, count in result.unmatched_reason_counts)
        )
    console.print(f"output: {result.csv_path}")
    console.print(f"summary_md: {result.markdown_path}")


@app.command("build-event-study-reporting")
def build_event_study_reporting_command(
    input_results: Path = EVENT_STUDY_REPORTING_INPUT_RESULTS_OPTION,
    input_clean_events: Path = EVENT_STUDY_REPORTING_INPUT_CLEAN_EVENTS_OPTION,
    input_threshold_sensitivity: Path = EVENT_STUDY_REPORTING_INPUT_THRESHOLD_SENSITIVITY_OPTION,
    input_market_data: Path = EVENT_STUDY_REPORTING_INPUT_MARKET_DATA_OPTION,
    input_yfinance_summary: Path = EVENT_STUDY_REPORTING_INPUT_YFINANCE_SUMMARY_OPTION,
    main_table_csv_path: Path = REPORTING_MAIN_TABLE_CSV_OPTION,
    main_table_md_path: Path = REPORTING_MAIN_TABLE_MD_OPTION,
    by_creator_csv_path: Path = REPORTING_BY_CREATOR_CSV_OPTION,
    by_ticker_csv_path: Path = REPORTING_BY_TICKER_CSV_OPTION,
    by_year_csv_path: Path = REPORTING_BY_YEAR_CSV_OPTION,
    by_recommendation_type_csv_path: Path = REPORTING_BY_RECOMMENDATION_TYPE_CSV_OPTION,
    by_direction_csv_path: Path = REPORTING_BY_DIRECTION_CSV_OPTION,
    robustness_csv_path: Path = REPORTING_ROBUSTNESS_CSV_OPTION,
    summary_md_path: Path = REPORTING_SUMMARY_MD_OPTION,
    methodology_note_path: Path = REPORTING_METHODOLOGY_NOTE_OPTION,
) -> None:
    from .reporting import build_event_study_reporting

    try:
        result = build_event_study_reporting(
            event_study_results_path=input_results,
            clean_events_path=input_clean_events,
            threshold_sensitivity_path=input_threshold_sensitivity,
            market_data_path=input_market_data,
            yfinance_fetch_summary_path=input_yfinance_summary,
            main_table_csv_path=main_table_csv_path,
            main_table_md_path=main_table_md_path,
            by_creator_csv_path=by_creator_csv_path,
            by_ticker_csv_path=by_ticker_csv_path,
            by_year_csv_path=by_year_csv_path,
            by_recommendation_type_csv_path=by_recommendation_type_csv_path,
            by_direction_csv_path=by_direction_csv_path,
            robustness_csv_path=robustness_csv_path,
            report_summary_md_path=summary_md_path,
            methodology_note_path=methodology_note_path,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Event-study reporting build complete: "
        f"event_count={result.event_count}, matched_count={result.matched_count}."
    )
    console.print(f"main_table_csv: {result.main_table_csv_path}")
    console.print(f"main_table_md: {result.main_table_md_path}")
    console.print(f"by_creator_csv: {result.by_creator_csv_path}")
    console.print(f"by_ticker_csv: {result.by_ticker_csv_path}")
    console.print(f"by_year_csv: {result.by_year_csv_path}")
    console.print(f"by_recommendation_type_csv: {result.by_recommendation_type_csv_path}")
    console.print(f"by_direction_csv: {result.by_direction_csv_path}")
    console.print(f"robustness_csv: {result.robustness_csv_path}")
    console.print(f"summary_md: {result.report_summary_md_path}")
    console.print(f"methodology_note: {result.methodology_note_path}")


@app.command("build-event-study-charts")
def build_event_study_charts_command(
    input_results: Path = EVENT_STUDY_REPORTING_INPUT_RESULTS_OPTION,
    input_clean_events: Path = EVENT_STUDY_REPORTING_INPUT_CLEAN_EVENTS_OPTION,
    input_market_data: Path = EVENT_STUDY_REPORTING_INPUT_MARKET_DATA_OPTION,
    output_dir: Path = REPORTING_CHARTS_DIR_OPTION,
) -> None:
    from .reporting import build_event_study_charts

    try:
        result = build_event_study_charts(
            event_study_results_path=input_results,
            clean_events_path=input_clean_events,
            market_data_path=input_market_data,
            output_dir=output_dir,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Event-study charts build complete: "
        f"charts_created={len(result.chart_paths)}."
    )
    console.print(f"output_dir: {result.output_dir}")
    for path in result.chart_paths:
        console.print(f"chart: {path}")


@app.command("scan-intraday-event-feasibility")
def scan_intraday_event_feasibility_command(
    input_path: Path = INTRADAY_FEASIBILITY_INPUT_OPTION,
    output_path: Path = INTRADAY_FEASIBILITY_OUTPUT_OPTION,
    summary_md_path: Path = INTRADAY_FEASIBILITY_SUMMARY_OPTION,
    ticker_aliases_path: Path = INTRADAY_FEASIBILITY_ALIASES_OPTION,
) -> None:
    from .intraday_event_study import scan_intraday_event_feasibility

    try:
        result = scan_intraday_event_feasibility(
            input_path=input_path,
            ticker_aliases_path=ticker_aliases_path,
            output_path=output_path,
            summary_md_path=summary_md_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Intraday feasibility scan complete: "
        f"total_events={result.total_events}, eligible_events={result.eligible_events}."
    )
    console.print(f"output: {result.output_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("fetch-yfinance-intraday-market-data")
def fetch_yfinance_intraday_market_data_command(
    input_feasibility_path: Path = INTRADAY_FETCH_INPUT_OPTION,
    output_path: Path = INTRADAY_FETCH_OUTPUT_OPTION,
    summary_md_path: Path = INTRADAY_FETCH_SUMMARY_MD_OPTION,
    summary_csv_path: Path = INTRADAY_FETCH_SUMMARY_CSV_OPTION,
    interval: str = typer.Option("1m", "--interval", help="yfinance intraday interval."),
    lookback_minutes: int = typer.Option(
        120,
        "--lookback-minutes",
        min=0,
        help="Lookback minutes before event timestamp.",
    ),
    forward_minutes: int = typer.Option(
        390,
        "--forward-minutes",
        min=0,
        help="Forward minutes after event timestamp.",
    ),
    confirm_yfinance_run: bool = typer.Option(
        False,
        "--confirm-yfinance-run",
        help="Required to fetch interim yfinance intraday data.",
    ),
    dry_run: bool = typer.Option(False, help="Preview eligible events without yfinance calls."),
) -> None:
    from .intraday_event_study import fetch_yfinance_intraday_market_data

    try:
        result = fetch_yfinance_intraday_market_data(
            feasibility_input_path=input_feasibility_path,
            output_path=output_path,
            summary_md_path=summary_md_path,
            summary_csv_path=summary_csv_path,
            interval=interval,
            lookback_minutes=lookback_minutes,
            forward_minutes=forward_minutes,
            confirm_yfinance_run=confirm_yfinance_run,
            dry_run=dry_run,
        )
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    if result.dry_run:
        console.print(
            "Dry run only; no yfinance intraday downloads were made. "
            f"eligible_events={result.eligible_events}, "
            f"planned_event_windows={result.planned_event_windows}, "
            f"max_window_days={result.max_window_days:.2f}, "
            f"events_excluded_outside_1m_limit={result.events_excluded_outside_1m_limit}, "
            f"shifted_windows={result.shifted_windows}."
        )
        return
    console.print(
        "Intraday yfinance fetch complete: "
        f"eligible_events={result.eligible_events}, "
        f"tickers_downloaded={result.tickers_downloaded}, "
        f"failed_tickers={len(result.failed_tickers)}, "
        f"rows={result.rows_written}."
    )
    if result.failed_tickers:
        console.print("failed_tickers: " + ", ".join(result.failed_tickers))
    console.print(f"output: {result.output_path}")
    console.print(f"summary_md: {result.summary_md_path}")
    console.print(f"summary_csv: {result.summary_csv_path}")


@app.command("run-intraday-event-study")
def run_intraday_event_study_command(
    input_events: Path = INTRADAY_EVENT_STUDY_EVENTS_OPTION,
    input_market_data: Path = INTRADAY_EVENT_STUDY_MARKET_DATA_OPTION,
    ticker_aliases_path: Path = INTRADAY_FEASIBILITY_ALIASES_OPTION,
    output_path: Path = INTRADAY_EVENT_STUDY_OUTPUT_OPTION,
    summary_md_path: Path = INTRADAY_EVENT_STUDY_SUMMARY_OPTION,
    by_creator_path: Path = INTRADAY_EVENT_STUDY_BY_CREATOR_OPTION,
    by_ticker_path: Path = INTRADAY_EVENT_STUDY_BY_TICKER_OPTION,
    methodology_note_path: Path = INTRADAY_EVENT_STUDY_METHOD_NOTE_OPTION,
) -> None:
    from .intraday_event_study import run_intraday_event_study

    try:
        result = run_intraday_event_study(
            input_events_path=input_events,
            input_intraday_market_data_path=input_market_data,
            ticker_aliases_path=ticker_aliases_path,
            output_path=output_path,
            summary_md_path=summary_md_path,
            by_creator_path=by_creator_path,
            by_ticker_path=by_ticker_path,
            methodology_note_path=methodology_note_path,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Intraday event-study complete: "
        f"events_processed={result.events_processed}, "
        f"events_matched={result.events_matched}, "
        f"missing_events={result.missing_events}."
    )
    console.print(f"output: {result.output_path}")
    console.print(f"summary_md: {result.summary_md_path}")
    console.print(f"by_creator_csv: {result.by_creator_path}")
    console.print(f"by_ticker_csv: {result.by_ticker_path}")
    console.print(f"methodology_note: {result.methodology_note_path}")


@app.command("build-intraday-event-study-charts")
def build_intraday_event_study_charts_command(
    input_results: Path = INTRADAY_CHART_INPUT_OPTION,
    output_dir: Path = INTRADAY_CHART_OUTPUT_DIR_OPTION,
) -> None:
    from .intraday_event_study import build_intraday_event_study_charts

    try:
        result = build_intraday_event_study_charts(
            input_results_path=input_results,
            output_dir=output_dir,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Intraday event-study charts complete: "
        f"charts_created={len(result.chart_paths)}."
    )
    console.print(f"output_dir: {result.output_dir}")
    for path in result.chart_paths:
        console.print(f"chart: {path}")


@app.command("build-x-extension-cost-plan")
def build_x_extension_cost_plan_command(
    seed_path: Path = X_EXTENSION_SEED_OPTION,
    output_path: Path = X_EXTENSION_OUTPUT_CSV_OPTION,
    summary_md_path: Path = X_EXTENSION_OUTPUT_MD_OPTION,
    queries_output_path: Path = X_EXTENSION_QUERIES_OUTPUT_OPTION,
) -> None:
    from .x_extension_plan import build_x_extension_cost_plan

    try:
        result = build_x_extension_cost_plan(
            candidate_seed_path=seed_path,
            output_cost_plan_csv_path=output_path,
            output_cost_plan_md_path=summary_md_path,
            output_candidate_queries_csv_path=queries_output_path,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "X extension cost plan complete (no API calls): "
        f"creators={result.creator_count}, "
        f"estimated_reads={result.total_estimated_reads}, "
        f"estimated_cost_usd={result.total_estimated_cost_usd:.2f}."
    )
    console.print(f"seed_path: {result.candidate_seed_path}")
    console.print(f"output: {result.cost_plan_csv_path}")
    console.print(f"summary_md: {result.cost_plan_md_path}")
    console.print(f"queries_output: {result.candidate_queries_csv_path}")


@app.command("export-transcript-vendor-batch")
def export_transcript_vendor_batch_command(
    limit: int = typer.Option(1000, min=1, help="Maximum videos to export."),
    output: Path = TRANSCRIPT_VENDOR_OUTPUT_OPTION,
    include_blocked: bool = typer.Option(
        False,
        help="Include videos with blocked/cooldown transcript statuses.",
    ),
    start_date: str | None = typer.Option(None, help="Earliest published_at date YYYY-MM-DD."),
    end_date: str | None = typer.Option(None, help="Latest published_at date YYYY-MM-DD."),
    stratify_by: str | None = typer.Option(
        None,
        help="Comma-separated strata such as year,creator.",
    ),
    max_per_creator: int = typer.Option(40, min=1, help="Maximum rows per creator."),
    max_per_creator_year: int = typer.Option(
        10,
        min=1,
        help="Maximum rows per creator-year cell.",
    ),
    max_year_share: float = typer.Option(0.35, min=0.01, max=1.0),
    max_top5_creator_share: float = typer.Option(0.25, min=0.01, max=1.0),
    max_recent_year_share: float = typer.Option(0.55, min=0.01, max=1.0),
    max_category_share: list[str] | None = MAX_CATEGORY_SHARE_OPTION,
    min_years: int = typer.Option(5, min=1),
    diversify_creators: bool = typer.Option(False, help="Round-robin creators within strata."),
    priority_weight: float = typer.Option(0.60, min=0.0, max=1.0),
    balance_weight: float = typer.Option(0.40, min=0.0, max=1.0),
) -> None:
    from .transcript_vendor import export_transcript_vendor_batch

    try:
        result = export_transcript_vendor_batch(
            limit=limit,
            output_path=output,
            include_blocked=include_blocked,
            start_date=start_date,
            end_date=end_date,
            stratify_by=stratify_by,
            max_per_creator=max_per_creator,
            max_per_creator_year=max_per_creator_year,
            max_year_share=max_year_share,
            max_top5_creator_share=max_top5_creator_share,
            max_recent_year_share=max_recent_year_share,
            max_category_share=max_category_share,
            min_years=min_years,
            diversify_creators=diversify_creators,
            priority_weight=priority_weight,
            balance_weight=balance_weight,
        )
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(f"transcript_vendor_batch: {result.output_path}")
    console.print(f"Rows exported: {result.row_count}")
    if result.creator_counts:
        table = Table(title="Vendor Batch Creator Mix")
        table.add_column("Creator")
        table.add_column("Rows", justify="right")
        for creator, count in sorted(result.creator_counts.items(), key=lambda item: (-item[1], item[0]))[:20]:
            table.add_row(creator, str(count))
        console.print(table)


def _add_count_rows(table: Table, rows: dict[str, int], limit: int = 20) -> None:
    for label, count in list(rows.items())[:limit]:
        table.add_row(label, str(count))


@app.command("audit-transcript-vendor-batch")
def audit_transcript_vendor_batch_command(
    input_path: Path = PROVIDER_INPUT_OPTION,
    start_date: str = typer.Option("2020-01-01", help="Earliest allowed published_at date."),
    end_date: str = typer.Option("2026-05-07", help="Latest allowed published_at date."),
) -> None:
    from .transcript_vendor import (
        audit_transcript_vendor_batch,
        write_transcript_vendor_batch_audit,
    )

    audit = audit_transcript_vendor_batch(
        input_path,
        start_date=start_date,
        end_date=end_date,
    )
    csv_path, text_path = write_transcript_vendor_batch_audit(audit)
    console.print(f"Input: {audit.input_path}")
    console.print(f"Rows: {audit.row_count}")
    console.print(f"Unique video IDs: {audit.unique_video_count}")
    console.print(f"Published range: {audit.min_published_at} to {audit.max_published_at}")
    console.print(f"Max single creator: {audit.max_single_creator}")
    console.print(f"Max creator-year cell: {audit.max_creator_year}")
    console.print(f"Top 5 creator share: {audit.top5_creator_share:.1%}")
    console.print(f"2026 share: {audit.year_2026_share:.1%}")
    console.print(f"2025-2026 share: {audit.year_2025_2026_share:.1%}")
    console.print(f"Stock-picker share: {audit.stock_picker_share:.1%}")
    console.print(f"Excluded rows: {audit.excluded_rows}")
    console.print(f"Already-transcribed rows: {audit.already_transcribed_rows}")
    console.print(f"Blocked/cooldown rows: {audit.blocked_cooldown_rows}")
    console.print(f"Missing published_at rows: {audit.missing_published_at_rows}")
    console.print(f"Outside date rows: {audit.outside_date_rows}")
    console.print(f"Pass: {audit.passed}")

    year_table = Table(title="Rows by Year")
    year_table.add_column("Year")
    year_table.add_column("Rows", justify="right")
    _add_count_rows(year_table, audit.rows_by_year)
    console.print(year_table)

    creator_table = Table(title="Top Creators")
    creator_table.add_column("Creator")
    creator_table.add_column("Rows", justify="right")
    _add_count_rows(creator_table, audit.rows_by_creator)
    console.print(creator_table)

    category_table = Table(title="Rows by Category")
    category_table.add_column("Category")
    category_table.add_column("Rows", justify="right")
    _add_count_rows(category_table, audit.rows_by_category)
    console.print(category_table)

    concentration_table = Table(title="Top Creator-Year Cells")
    concentration_table.add_column("Creator-Year")
    concentration_table.add_column("Rows", justify="right")
    _add_count_rows(concentration_table, audit.rows_by_creator_year)
    console.print(concentration_table)

    criteria_table = Table(title="Balance Criteria")
    criteria_table.add_column("Criterion")
    criteria_table.add_column("Result")
    for criterion, passed in audit.pass_fail.items():
        criteria_table.add_row(criterion, "PASS" if passed else "FAIL")
    console.print(criteria_table)
    for warning in audit.warnings:
        console.print(f"WARNING: {warning}")
    console.print(f"audit_csv: {csv_path}")
    console.print(f"audit_txt: {text_path}")


@app.command("import-transcripts-csv")
def import_transcripts_csv_command(
    path: Path = TRANSCRIPT_IMPORT_PATH_OPTION,
    source: str = typer.Option(..., help="Import run source label, e.g. external_provider."),
    overwrite: bool = typer.Option(False, help="Replace existing available transcripts."),
) -> None:
    from .transcript_vendor import import_transcripts_csv

    try:
        result = import_transcripts_csv(path=path, source=source, overwrite=overwrite)
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Transcript import complete: "
        f"imported={result.imported_count}, "
        f"overwritten={result.overwritten_count}, "
        f"segments={result.segment_count}, "
        f"source={result.source}."
    )


@app.command("import-manual-transcripts")
def import_manual_transcripts_command(
    input: Path = MANUAL_TRANSCRIPT_IMPORT_PATH_OPTION,
    dry_run: bool = typer.Option(False, help="Validate and summarize without database writes."),
    confirm_import: bool = typer.Option(False, help="Confirm this manual transcript import."),
    allow_short: bool = typer.Option(False, help="Allow transcripts below the minimum word count."),
    allow_overwrite: bool = typer.Option(
        False,
        "--allow-overwrite",
        "--replace",
        help="Replace existing available transcripts.",
    ),
    min_word_count: int = typer.Option(50, min=1, help="Minimum useful transcript word count."),
) -> None:
    from .transcript_ingestion import (
        ManualTranscriptImportError,
        import_manual_transcripts_with_summary,
    )

    try:
        effective_dry_run = dry_run or not confirm_import
        result = import_manual_transcripts_with_summary(
            input_path=input,
            dry_run=effective_dry_run,
            confirm_import=confirm_import,
            allow_short=allow_short,
            allow_overwrite=allow_overwrite,
            min_word_count=min_word_count,
        )
    except (ManualTranscriptImportError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Manual transcript import complete: "
        f"imported={result.imported_count}, "
        f"rejected={result.rejected_count}, "
        f"skipped_existing={result.skipped_existing_count}, "
        f"duplicate_checksum={result.duplicate_checksum_count}, "
        f"dry_run={result.dry_run}."
    )
    console.print(f"summary_csv: {result.summary_csv_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("plan-next-paid-transcript-batch")
def plan_next_paid_transcript_batch_command(
    credit_budget: int = typer.Option(61, min=1, help="Paid transcript credit budget."),
    output: Path = NEXT_PAID_BATCH_OUTPUT_OPTION,
    summary_md: Path = NEXT_PAID_BATCH_MD_OPTION,
) -> None:
    from .transcript_ingestion import plan_next_paid_transcript_batch

    result = plan_next_paid_transcript_batch(
        credit_budget=credit_budget,
        csv_path=output,
        md_path=summary_md,
    )
    console.print(
        "Paid transcript batch plan complete: "
        f"selected={result.selected_count}, "
        f"credit_budget={result.credit_budget}, "
        f"missing={result.videos_missing_transcripts}."
    )
    console.print(f"batch_csv: {result.csv_path}")
    console.print(f"batch_md: {result.md_path}")


@app.command("collect-paid-transcript-batch")
def collect_paid_transcript_batch_command(
    input: Path = PAID_BATCH_INPUT_OPTION,
    provider: str = typer.Option("transcriptapi", help="Provider: transcriptapi or youtubetranscript_dev."),
    credit_budget: int = typer.Option(61, min=1, max=61, help="Maximum paid credits to spend."),
    batch_size: int = typer.Option(100, min=1, max=100, help="Provider batch size."),
    language: str = typer.Option("en", help="Preferred transcript language."),
    timestamps: bool = typer.Option(False, help="Request timestamped segments."),
    captions_only: bool = typer.Option(False, help="Do not accept provider ASR output."),
    allow_asr: bool = typer.Option(False, help="Explicitly allow provider ASR output."),
    allow_overwrite: bool = typer.Option(
        False,
        "--allow-overwrite",
        help="Replace existing available transcripts.",
    ),
    confirm_paid_transcript_run: bool = typer.Option(
        False,
        help="Confirm this paid/credit-consuming transcript provider run.",
    ),
) -> None:
    from .transcript_ingestion import collect_paid_transcript_batch

    try:
        result = collect_paid_transcript_batch(
            input_path=input,
            confirm_paid_transcript_run=confirm_paid_transcript_run,
            provider=provider,
            credit_budget=credit_budget,
            batch_size=batch_size,
            language=language,
            timestamps=timestamps,
            captions_only=captions_only,
            allow_asr=allow_asr,
            allow_overwrite=allow_overwrite,
        )
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Paid transcript batch complete: "
        f"attempted={result.attempted_count}, "
        f"imported={result.imported_count}, "
        f"failed={result.failed_count}, "
        f"skipped_existing={result.skipped_existing_count}, "
        f"live_api_calls_made={result.live_api_calls_made}."
    )
    console.print(f"summary_csv: {result.summary_csv_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("build-transcript-provenance-report")
def build_transcript_provenance_report_command(
    output: Path = TRANSCRIPT_PROVENANCE_OUTPUT_OPTION,
    summary_md: Path = TRANSCRIPT_PROVENANCE_MD_OPTION,
    methodology_note: Path = TRANSCRIPT_METHODOLOGY_NOTE_OPTION,
) -> None:
    from .transcript_ingestion import build_transcript_provenance_report

    result = build_transcript_provenance_report(
        csv_path=output,
        md_path=summary_md,
        methodology_note_path=methodology_note,
    )
    console.print(
        "Transcript provenance report complete: "
        f"total={result.total_videos}, "
        f"with_transcripts={result.videos_with_transcripts}, "
        f"missing={result.videos_missing_transcripts}."
    )
    console.print(f"summary_csv: {result.csv_path}")
    console.print(f"summary_md: {result.md_path}")
    console.print(f"methodology_note: {result.methodology_note_path}")


@app.command("build-expanded-transcript-coverage-report")
def build_expanded_transcript_coverage_report_command(
    output: Path = EXPANDED_TRANSCRIPT_COVERAGE_OUTPUT_OPTION,
    summary_md: Path = EXPANDED_TRANSCRIPT_COVERAGE_MD_OPTION,
) -> None:
    from .transcript_ingestion import build_expanded_transcript_coverage_report

    result = build_expanded_transcript_coverage_report(csv_path=output, md_path=summary_md)
    console.print(
        "Expanded transcript coverage report complete: "
        f"total={result.total_videos}, "
        f"transcripts={result.total_transcripts}, "
        f"paid_provider={result.paid_provider_transcripts}, "
        f"missing={result.videos_missing_transcripts}, "
        f"provider_failures={result.failed_provider_rows}."
    )
    console.print(f"summary_csv: {result.csv_path}")
    console.print(f"summary_md: {result.md_path}")


@app.command("extract-events-from-new-transcripts")
def extract_events_from_new_transcripts_command(
    summary_csv: Path = NEW_TRANSCRIPT_EVENT_EXTRACTION_CSV_OPTION,
    summary_md: Path = NEW_TRANSCRIPT_EVENT_EXTRACTION_MD_OPTION,
) -> None:
    from .transcript_classify import extract_events_from_new_transcripts

    result = extract_events_from_new_transcripts(
        summary_csv_path=summary_csv,
        summary_md_path=summary_md,
    )
    console.print(
        "New transcript event extraction complete: "
        f"scanned={result.transcripts_scanned}, "
        f"skipped={result.transcripts_skipped_already_processed}, "
        f"ticker_mentions={result.new_ticker_mentions_found}, "
        f"candidate_windows={result.new_candidate_windows_found}, "
        f"events={result.new_events_found}."
    )
    console.print(f"summary_csv: {result.summary_csv_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("build-expanded-robustness")
def build_expanded_robustness_command(
    output_dir: Path = EXPANDED_ROBUSTNESS_DIR_OPTION,
    input_market_data: Path | None = EVENT_STUDY_MARKET_DATA_INPUT_OPTION,
    market_data_source: str = typer.Option(
        "auto",
        "--market-data-source",
        help="Market-data source selection: auto, bloomberg, or yfinance.",
    ),
    min_confidence: float = typer.Option(
        0.75,
        "--min-confidence",
        min=0.0,
        max=1.0,
        help="Minimum auto-label confidence for expanded clean event inclusion.",
    ),
) -> None:
    from .expanded_robustness import build_expanded_robustness_outputs

    try:
        result = build_expanded_robustness_outputs(
            output_dir=output_dir,
            input_market_data=input_market_data,
            market_data_source=market_data_source,
            min_confidence=min_confidence,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Expanded robustness build complete: "
        f"baseline_clean_events={result.baseline_clean_events}, "
        f"expanded_clean_events={result.expanded_clean_events}, "
        f"newly_added_events={result.newly_added_events}, "
        f"baseline_only_events={result.baseline_only_events}, "
        f"expanded_only_events={result.expanded_only_events}, "
        f"expanded_matched_events={result.expanded_matched_events}, "
        f"expanded_missing_market_data_events={result.expanded_missing_market_data_events}."
    )
    console.print(f"expanded_clean_events: {result.expanded_clean_events_path}")
    console.print(f"expanded_event_study_results: {result.expanded_event_study_results_path}")
    console.print(f"membership_audit: {result.membership_audit_md_path}")
    console.print(f"comparison: {result.expanded_comparison_path}")
    console.print(f"methodology: {result.expanded_methodology_path}")


@app.command("export-free-transcript-targets")
def export_free_transcript_targets_command(
    credit_output: Path = FREE_TARGET_CREDIT_OUTPUT_OPTION,
    manual_output: Path = FREE_TARGET_MANUAL_OUTPUT_OPTION,
    template_output: Path = FREE_TARGET_TEMPLATE_OUTPUT_OPTION,
    methods_output: Path = FREE_TARGET_METHODS_OUTPUT_OPTION,
    credit_limit: int = typer.Option(18, min=1, max=18, help="Remaining credit target count."),
    manual_limit: int = typer.Option(100, min=1, help="Manual target count."),
    start_date: str = typer.Option("2020-01-01", help="Earliest eligible published_at date."),
    end_date: str = typer.Option("2026-05-07", help="Latest eligible published_at date."),
) -> None:
    from .transcript_vendor import export_free_transcript_targets

    result = export_free_transcript_targets(
        credit_output_path=credit_output,
        manual_output_path=manual_output,
        template_path=template_output,
        methods_path=methods_output,
        credit_limit=credit_limit,
        manual_limit=manual_limit,
        start_date=start_date,
        end_date=end_date,
    )
    console.print(f"remaining_credit_targets: {result.credit_output_path}")
    console.print(f"remaining_credit_rows: {result.credit_row_count}")
    console.print(f"manual_transcript_targets: {result.manual_output_path}")
    console.print(f"manual_target_rows: {result.manual_row_count}")
    console.print(f"manual_import_template: {result.template_path}")
    console.print(f"methods_text: {result.methods_path}")


@app.command("collect-provider-transcripts")
def collect_provider_transcripts_command(
    provider: str = typer.Option(
        "youtubetranscript_dev",
        help="Provider: youtubetranscript_dev or transcriptapi.",
    ),
    input_path: Path = PROVIDER_INPUT_OPTION,
    output: Path = PROVIDER_OUTPUT_OPTION,
    limit: int = typer.Option(100, min=1, help="Maximum input videos to consider."),
    batch_size: int = typer.Option(100, min=1, max=100, help="Provider batch size."),
    language: str = typer.Option("en", help="Preferred transcript language."),
    timestamps: bool = typer.Option(False, help="Request timestamped segments."),
    captions_only: bool = typer.Option(
        False,
        help="Do not accept provider ASR output.",
    ),
    allow_asr: bool = typer.Option(False, help="Explicitly allow provider ASR output."),
    confirm_provider_run: bool = typer.Option(
        False,
        help="Confirm this paid/credit-consuming provider run.",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--include-existing",
        help="Skip videos that already have available transcripts.",
    ),
) -> None:
    from .provider_transcripts import (
        ProviderConfigError,
        ProviderRequestError,
        collect_provider_transcripts,
    )

    try:
        result = collect_provider_transcripts(
            provider=provider,
            input_path=input_path,
            output_path=output,
            limit=limit,
            batch_size=batch_size,
            language=language,
            timestamps=timestamps,
            captions_only=captions_only,
            allow_asr=allow_asr,
            confirm_provider_run=confirm_provider_run,
            skip_existing=skip_existing,
        )
    except (ProviderConfigError, ProviderRequestError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Provider transcript collection complete: "
        f"provider={result.provider}, "
        f"attempted={result.attempted_count}, "
        f"successful={result.successful_count}, "
        f"failed={result.failed_count}, "
        f"skipped_existing={result.skipped_existing_count}."
    )
    console.print(f"provider_transcripts: {result.output_path}")
    console.print(f"provider_failures: {result.failure_path}")


@app.command("provider-transcript-autopilot")
def provider_transcript_autopilot_command(
    provider: str = typer.Option("transcriptapi", help="Provider: transcriptapi."),
    target_new_transcripts: int = typer.Option(
        100,
        min=1,
        help="Stop after importing this many new transcripts.",
    ),
    max_attempts: int = typer.Option(
        500,
        min=1,
        help="Maximum unique queued videos to attempt.",
    ),
    chunk_size: int = typer.Option(100, min=1, help="Videos per provider chunk."),
    queue_size: int = typer.Option(500, min=1, help="Fresh balanced queue size."),
    min_low_signal_share: float = typer.Option(
        0.25,
        min=0.0,
        max=1.0,
        help="Minimum selected queue share from low title-signal videos when available.",
    ),
    max_per_creator: int = typer.Option(
        0,
        min=0,
        help="Maximum queued videos per creator (0=no hard cap).",
    ),
    max_per_year: int = typer.Option(
        0,
        min=0,
        help="Maximum queued videos per year (0=no hard cap).",
    ),
    language: str = typer.Option("en", help="Preferred transcript language."),
    timestamps: bool = typer.Option(False, help="Request timestamped segments."),
    captions_only: bool = typer.Option(False, help="Do not accept provider ASR output."),
    retry_status: list[str] | None = AUTOPILOT_RETRY_STATUS_OPTION,
    max_retries: int = typer.Option(2, min=0, help="Retries per retryable failed video."),
    sleep_seconds: float = typer.Option(
        3.0,
        min=0.0,
        help="Seconds to sleep between chunks and retry attempts.",
    ),
    confirm_provider_run: bool = typer.Option(
        False,
        help="Confirm this paid/credit-consuming provider run.",
    ),
    dry_run: bool = typer.Option(False, help="Build queue and run artifacts without provider calls."),
    run_name: str | None = typer.Option(None, help="Optional run directory name suffix."),
    resume: Path | None = AUTOPILOT_RESUME_OPTION,
) -> None:
    from .provider_autopilot import (
        ProviderAutopilotConfig,
        ProviderAutopilotError,
        run_provider_transcript_autopilot,
    )

    try:
        result = run_provider_transcript_autopilot(
            ProviderAutopilotConfig(
                provider=provider,
                target_new_transcripts=target_new_transcripts,
                max_attempts=max_attempts,
                chunk_size=chunk_size,
                queue_size=queue_size,
                min_low_signal_share=min_low_signal_share,
                max_per_creator=max_per_creator,
                max_per_year=max_per_year,
                language=language,
                timestamps=timestamps,
                captions_only=captions_only,
                retry_statuses=tuple(retry_status or ("http_408",)),
                max_retries=max_retries,
                sleep_seconds=sleep_seconds,
                confirm_provider_run=confirm_provider_run,
                dry_run=dry_run,
                run_name=run_name,
                resume=resume,
            )
        )
    except (ProviderAutopilotError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    console.print(
        "Provider transcript autopilot complete: "
        f"attempted={result.attempted}, "
        f"successful={result.successful}, "
        f"failed={result.failed}, "
        f"skipped_existing={result.skipped_existing}, "
        f"retries={result.retries}, "
        f"dry_run={result.dry_run}."
    )
    console.print(f"run_dir: {result.run_dir}")
    console.print(f"manifest: {result.manifest_path}")
    console.print(f"final_summary: {result.final_summary_path}")


def _print_summary_table(title: str, rows: list[dict[str, object]], label_key: str, limit: int = 20) -> None:
    table = Table(title=title)
    table.add_column(label_key)
    table.add_column("Covered", justify="right")
    table.add_column("Uncovered", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Coverage", justify="right")
    for row in rows[:limit]:
        table.add_row(
            str(row[label_key]),
            str(row["covered"]),
            str(row["uncovered"]),
            str(row["total"]),
            f"{float(row['coverage_rate']):.1%}",
        )
    console.print(table)


@app.command("transcript-coverage-bias-report")
def transcript_coverage_bias_report_command() -> None:
    from .transcript_vendor import build_transcript_coverage_bias_report

    report = build_transcript_coverage_bias_report()
    for label_key, rows in report.items():
        _print_summary_table(
            title=f"Transcript Coverage by {label_key.replace('_', ' ').title()}",
            rows=rows,
            label_key=label_key,
        )


@app.command("transcript-priority-report")
def transcript_priority_report_command(
    limit: int = typer.Option(1000, min=1, help="Provider batch planning limit."),
) -> None:
    from .transcript_vendor import build_transcript_priority_report

    report = build_transcript_priority_report(limit=limit)
    console.print(f"Eligible videos: {report['eligible_count']}")
    console.print(f"Selected planning batch: {report['selected_count']}")
    console.print(f"Recommended provider batch size: {report['recommended_provider_batch_size']}")
    concentration = report["creator_concentration"]
    console.print(
        "Creator concentration: "
        f"distinct={concentration['distinct_creators']}, "
        f"top_creator_share={float(concentration['top_creator_share']):.1%}"
    )
    yield_estimate = report["estimated_candidate_yield"]
    console.print(
        "Estimated candidate yield: "
        f"high_signal_videos={yield_estimate['high_signal_videos']}, "
        f"observed_event_rate={float(yield_estimate['observed_event_rate']):.1%}, "
        f"estimated_events={yield_estimate['estimated_events']}"
    )

    creator_table = Table(title="Top Creators")
    creator_table.add_column("Creator")
    creator_table.add_column("Rows", justify="right")
    for row in report["top_creators"]:
        creator_table.add_row(str(row["creator"]), str(row["count"]))
    console.print(creator_table)

    category_table = Table(title="Top Categories")
    category_table.add_column("Category")
    category_table.add_column("Rows", justify="right")
    for row in report["top_categories"]:
        category_table.add_row(str(row["creator_category"]), str(row["count"]))
    console.print(category_table)

    video_table = Table(title="Top High-Signal Videos")
    video_table.add_column("Video ID", no_wrap=True)
    video_table.add_column("Creator")
    video_table.add_column("Priority", justify="right")
    video_table.add_column("Ticker Signals", justify="right")
    video_table.add_column("Title")
    for row in report["top_high_signal_videos"][:10]:
        video_table.add_row(
            str(row["video_id"]),
            str(row["creator"]),
            f"{float(row['priority_score']):.1f}",
            str(row["ticker_signal_count"]),
            str(row["title"]),
        )
    console.print(video_table)


@app.command("export-capstone-summary")
def export_capstone_summary_command() -> None:
    from .capstone_summary import export_capstone_summary

    result = export_capstone_summary()
    console.print(f"capstone_summary_tables: {result.output_dir}")
    for name, path in result.paths.items():
        console.print(f"{name}: {path}")


SEED_QUEUE_DEFAULT_CSV = Path("data/exports/transcript_provider_batch_500_balanced.csv")

SEED_QUEUE_INPUT_OPTION = typer.Option(
    SEED_QUEUE_DEFAULT_CSV,
    "--input",
    "-i",
    help="CSV batch file containing video_id column.",
)


@app.command("seed-transcript-queue")
def seed_transcript_queue_command(
    input: Path = SEED_QUEUE_INPUT_OPTION,
) -> None:
    from .db import connect as _connect
    from .youtube_transcripts import seed_transcript_queue_from_csv

    initialize_database()
    with _connect() as conn:
        count = seed_transcript_queue_from_csv(conn, input)
    console.print(f"Seeded transcript fetch queue from {input.name}: {count} videos.")


@app.command("collect-native-transcripts-overtime")
def collect_native_transcripts_overtime_command(
    limit: int = typer.Option(20, min=1, help="Maximum videos to attempt per run."),
    sleep_seconds: float = typer.Option(20.0, min=0.0, help="Seconds sleep between fetches."),
    jitter_seconds: float = typer.Option(10.0, min=0.0, help="Random jitter added to sleep."),
    max_per_creator: int = typer.Option(3, min=1, help="Max transcripts per creator per run."),
    min_disk_mb: int = typer.Option(500, min=0, help="Stop if free disk below this MB."),
    stop_on_block: bool = typer.Option(True, help="Stop on ip_blocked or request_blocked."),
    allow_translation: bool = typer.Option(
        False, help="Fall back to translatable non-English transcripts."
    ),
    creator_diversify: bool = typer.Option(
        True, help="Diversify across creators rather than strict priority order."
    ),
    input: Path = SEED_QUEUE_INPUT_OPTION,
    cooldown_hours: int = typer.Option(24, min=1, help="Hours cooldown after a block."),
    max_daily_attempts: int = typer.Option(50, min=1, help="Max total attempts per 24-hour window."),
    undercovered_years_first: bool = typer.Option(
        True, help="Prefer videos from years with lowest transcript coverage."
    ),
    undercovered_creators_first: bool = typer.Option(
        True, help="Prefer videos from creators with lowest transcript coverage."
    ),
) -> None:
    from .overtime_collection import collect_native_transcripts_overtime

    result = collect_native_transcripts_overtime(
        limit=limit,
        sleep_seconds=sleep_seconds,
        jitter_seconds=jitter_seconds,
        max_per_creator=max_per_creator,
        min_disk_mb=min_disk_mb,
        stop_on_block=stop_on_block,
        allow_translation=allow_translation,
        creator_diversify=creator_diversify,
        input_csv=input,
        cooldown_hours=cooldown_hours,
        max_daily_attempts=max_daily_attempts,
        undercovered_years_first=undercovered_years_first,
        undercovered_creators_first=undercovered_creators_first,
    )

    if result.cooldown_blocked:
        console.print("[bold yellow]Cooldown active.[/bold yellow] "
                       "A previous run was blocked by YouTube. Wait before trying again.")
        return

    console.print(
        f"Overtime collection run {result.run_id} complete: "
        f"attempted={result.attempted_count}, "
        f"available={result.available_count}, "
        f"statuses={result.status_counts}."
    )
    if result.stopped_reason:
        console.print(f"Stopped early: {result.stopped_reason}.")


@app.command("transcript-collection-status")
def transcript_collection_status_command() -> None:
    from .overtime_collection import transcript_collection_status

    status = transcript_collection_status()

    console.print("[bold]Transcript Collection Status[/bold]")
    console.print(f"  Total transcripts:         {status.total_transcripts}")
    console.print(f"  Native (youtube) available: {status.native_transcripts}")
    console.print(f"  Provider available:         {status.provider_transcripts}")
    console.print(f"  Candidate windows:          {status.candidate_windows}")
    console.print(f"  Accepted events:            {status.accepted_events}")
    console.print(f"  Last run at:                {status.last_run_at or 'never'}")
    console.print(f"  Last stopped reason:        {status.last_stopped_reason or 'none'}")
    console.print(f"  Cooldown active:            {'YES' if status.cooldown_active else 'no'}")
    console.print(f"  Next safe run time:         {status.next_safe_run_time or 'now'}")
    console.print(f"  Attempts last 24h:          {status.attempts_last_24h}")
    console.print(f"  Successes last 24h:         {status.successes_last_24h}")
    console.print(f"  Success rate 24h:           {status.attempts_24h_success_rate:.1%}")
    console.print(f"  Blocks last 24h:            {status.blocks_last_24h}")
    console.print(f"  High-risk ticker targets:   {status.high_risk_ticker_targets}")
    console.print(f"  False-positive quarantined: {status.false_positive_quarantine_count}")
    console.print(f"  [bold]Recommendation: {status.recommended_action}[/bold]")

    year_table = Table(title="Coverage by Year")
    year_table.add_column("Year")
    year_table.add_column("Covered", justify="right")
    year_table.add_column("Uncovered", justify="right")
    year_table.add_column("Total", justify="right")
    year_table.add_column("Rate", justify="right")
    for row in status.coverage_by_year:
        total = row["total"]
        rate = row["covered"] / total if total > 0 else 0.0
        year_table.add_row(
            str(row["year"]), str(row["covered"]),
            str(row["uncovered"]), str(total), f"{rate:.1%}",
        )
    console.print(year_table)

    creator_table = Table(title="Coverage by Creator (lowest coverage first, top 20)")
    creator_table.add_column("Creator")
    creator_table.add_column("Covered", justify="right")
    creator_table.add_column("Total", justify="right")
    creator_table.add_column("Rate", justify="right")
    for row in status.coverage_by_creator:
        total = row["total"]
        rate = row["covered"] / total if total > 0 else 0.0
        creator_table.add_row(
            str(row["creator"]), str(row["covered"]),
            str(total), f"{rate:.1%}",
        )
    console.print(creator_table)


@app.command("plan-slow-youtube-transcript-queue")
def plan_slow_youtube_transcript_queue_command(
    start_year: int = typer.Option(2020, "--start-year", help="Start year for queue planning."),
    end_year: int = typer.Option(2023, "--end-year", help="End year for queue planning."),
    max_videos: int = typer.Option(724, "--max-videos", help="Maximum videos to include in queue."),
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        help="Explicit SQLite DATABASE_URL. Defaults to env/DATABASE_URL or sqlite:///data/finfluencer_alpha.db.",
    ),
    exclude_permanent_failures: bool = typer.Option(
        True,
        "--exclude-permanent-failures/--include-permanent-failures",
        help="Exclude videos with permanent no-transcript statuses (disabled, unavailable, no_language).",
    ),
    output_path: Path = SLOW_QUEUE_OUTPUT_OPTION,
    summary_md_path: Path = SLOW_QUEUE_MD_OPTION,
) -> None:
    from .slow_transcript_collection import plan_slow_youtube_transcript_queue

    result = plan_slow_youtube_transcript_queue(
        start_year=start_year,
        end_year=end_year,
        max_videos=max_videos,
        database_url=database_url,
        exclude_permanent_failures=exclude_permanent_failures,
        output_path=output_path,
        summary_md_path=summary_md_path,
    )
    console.print(
        f"Slow transcript queue planned: {result.queue_size} videos "
        f"({start_year}-{end_year})."
    )
    console.print(f"queue_csv: {result.queue_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("refresh-slow-youtube-transcript-queue")
def refresh_slow_youtube_transcript_queue_command(
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        help="Explicit SQLite DATABASE_URL. Defaults to env/DATABASE_URL or sqlite:///data/finfluencer_alpha.db.",
    ),
    output_path: Path = SLOW_QUEUE_OUTPUT_OPTION,
    summary_md_path: Path = SLOW_QUEUE_MD_OPTION,
) -> None:
    from .slow_transcript_collection import refresh_slow_youtube_transcript_queue

    result = refresh_slow_youtube_transcript_queue(
        database_url=database_url,
        output_path=output_path,
        summary_md_path=summary_md_path,
    )
    console.print(
        f"Slow transcript queue refreshed: {result.queue_size} videos."
    )
    console.print(f"queue_csv: {result.queue_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("collect-youtube-transcripts-slow")
def collect_youtube_transcripts_slow_command(
    input_path: Path = SLOW_COLLECT_INPUT_OPTION,
    max_videos: int = typer.Option(10, "--max-videos", help="Max videos to attempt per run."),
    delay_seconds: float = typer.Option(60.0, "--delay-seconds", help="Delay between attempts in seconds."),
    stop_on_block: bool = typer.Option(True, "--stop-on-block", help="Stop immediately on block detection."),
    confirm_run: bool = typer.Option(False, "--confirm-run", help="Required to make live calls and DB writes."),
    allow_overwrite: bool = typer.Option(False, "--allow-overwrite", help="Allow overwriting existing transcripts."),
    allow_translation: bool = typer.Option(True, "--allow-translation", help="Allow translated transcript fallback."),
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        help="Explicit SQLite DATABASE_URL. Defaults to env/DATABASE_URL or sqlite:///data/finfluencer_alpha.db.",
    ),
    output_summary_csv: Path = SLOW_COLLECT_SUMMARY_CSV_OPTION,
    output_summary_md: Path = SLOW_COLLECT_SUMMARY_MD_OPTION,
) -> None:
    from .slow_transcript_collection import collect_youtube_transcripts_slow

    try:
        result = collect_youtube_transcripts_slow(
            input_path=input_path,
            max_videos=max_videos,
            delay_seconds=delay_seconds,
            stop_on_block=stop_on_block,
            confirm_run=confirm_run,
            allow_overwrite=allow_overwrite,
            allow_translation=allow_translation,
            database_url=database_url,
            output_summary_csv=output_summary_csv,
            output_summary_md=output_summary_md,
        )
    except (ValueError, FileNotFoundError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc

    if not confirm_run:
        console.print(
            "Dry run only; no live transcript calls were made. "
            f"queue_size={result.remaining_queue_count}, "
            f"max_videos={max_videos}. "
            "Re-run with --confirm-run to collect."
        )
        return

    console.print(
        f"Slow collection run {result.run_id} complete: "
        f"attempted={result.attempted}, imported={result.imported}, "
        f"skipped_existing={result.skipped_existing}, "
        f"terminal_failures={result.terminal_failures}, "
        f"transient_failures={result.transient_failures}."
    )
    if result.stop_reason:
        console.print(f"Stopped early: {result.stop_reason}.")
    if result.fallback_triggered:
        console.print(f"Fallback triggered: {result.fallback_route}.")
    console.print(f"summary_csv: {result.summary_csv_path}")
    console.print(f"summary_md: {result.summary_md_path}")


@app.command("build-manual-transcript-collection-packet")
def build_manual_transcript_collection_packet_command(
    input_path: Path = SLOW_COLLECT_INPUT_OPTION,
    max_videos: int = typer.Option(100, "--max-videos", help="Max videos in manual packet."),
    output_packet_csv: Path = MANUAL_PACKET_OUTPUT_CSV_OPTION,
    output_packet_md: Path = MANUAL_PACKET_OUTPUT_MD_OPTION,
    output_template_csv: Path = MANUAL_PACKET_TEMPLATE_OPTION,
) -> None:
    from .slow_transcript_collection import build_manual_transcript_collection_packet

    result = build_manual_transcript_collection_packet(
        input_path=input_path,
        max_videos=max_videos,
        output_packet_csv=output_packet_csv,
        output_packet_md=output_packet_md,
        output_template_csv=output_template_csv,
    )
    console.print(
        f"Manual collection packet built: {result.packet_size} videos."
    )
    console.print(f"packet_csv: {result.packet_csv_path}")
    console.print(f"packet_md: {result.packet_md_path}")
    console.print(f"template_csv: {result.template_path}")


@app.command("build-slow-collection-daily-plan")
def build_slow_collection_daily_plan_command(
    output_path: Path = SLOW_DAILY_PLAN_OUTPUT_OPTION,
) -> None:
    from .slow_transcript_collection import build_slow_collection_daily_plan

    path = build_slow_collection_daily_plan(output_path=output_path)
    console.print(f"Slow collection daily plan written: {path}")


@app.command("audit-ticker-false-positives")
def audit_ticker_false_positives_command(
    ticker: str = typer.Option("YOU", help="Ticker symbol to audit for false positives."),
) -> None:
    from .ticker_false_positive import audit_ticker_false_positives

    paths = audit_ticker_false_positives(ticker=ticker.upper())
    for name, path in paths.items():
        console.print(f"{name}: {path}")
    console.print(
        f"Audit complete. Review {paths['summary_txt']} for recommended actions."
    )


@app.command("quarantine-false-positive-tickers")
def quarantine_false_positive_tickers_command(
    ticker: str = typer.Option("YOU", help="Ticker symbol to quarantine."),
    dry_run: bool = typer.Option(True, help="Preview without modifying database."),
    apply: bool = typer.Option(False, "--apply", help="Actually apply quarantines to the database."),
    reason: str = typer.Option(
        "common_word_false_positive", help="Reason for quarantining."
    ),
) -> None:
    from .ticker_false_positive import quarantine_false_positive_tickers

    result = quarantine_false_positive_tickers(
        ticker=ticker.upper(),
        dry_run=not apply,
        reason=reason,
    )
    mode = "DRY RUN" if result.dry_run else "APPLIED"
    console.print(
        f"[bold]{mode}[/bold]: "
        f"candidate windows to exclude={result.windows_excluded}, "
        f"events to exclude={result.events_excluded}."
    )
    if result.dry_run:
        console.print("Re-run with --apply to persist changes.")


@app.command("overnight-readiness-check")
def overnight_readiness_check_command() -> None:
    from .overnight_readiness import overnight_readiness_check

    result = overnight_readiness_check()
    status_label = "[bold green]READY_FOR_OVERNIGHT[/bold green]" if result.ready else "[bold red]NOT_READY_FOR_OVERNIGHT[/bold red]"
    console.print(f"Status: {status_label}")
    console.print(f"  Free disk:     {result.free_disk_mb:.0f} MB")
    console.print(f"  Cooldown:      {'YES' if result.cooldown_active else 'no'}")
    console.print(f"  Attempts 24h:  {result.attempts_last_24h} / {result.max_daily_attempts}")
    console.print(f"  Queue eligible:{result.queue_eligible}")
    console.print(f"  High-risk only:{result.high_risk_only_targets}")
    console.print(f"  Quarantined:   {result.false_positive_quarantine_count}")
    console.print("  Reasons:")
    for reason in result.reasons:
        console.print(f"    - {reason}")
    if result.ready:
        console.print(f"\nRecommended overnight command:\n  {result.recommended_command}")
    else:
        console.print(f"\n{result.recommended_command}")


@app.command("run-overnight-transcript-collection")
def run_overnight_transcript_collection_command(
    batches: int = typer.Option(8, min=1, help="Maximum number of mini-batches."),
    batch_limit: int = typer.Option(5, min=1, help="Videos to attempt per mini-batch."),
    between_batch_sleep_seconds: float = typer.Option(
        2700.0, min=0.0, help="Seconds sleep between mini-batches."
    ),
    sleep_seconds: float = typer.Option(
        35.0, min=0.0, help="Seconds sleep between individual fetches."
    ),
    jitter_seconds: float = typer.Option(
        15.0, min=0.0, help="Random jitter added to sleep."
    ),
    max_per_creator: int = typer.Option(
        1, min=1, help="Max transcripts per creator per mini-batch."
    ),
    min_disk_mb: int = typer.Option(
        500, min=0, help="Stop if free disk below this MB."
    ),
    recommended_disk_mb: int = typer.Option(
        1000, min=0, help="Recommended disk warning threshold."
    ),
    cooldown_hours: int = typer.Option(
        24, min=1, help="Hours cooldown after a block."
    ),
    max_daily_attempts: int = typer.Option(
        50, min=1, help="Max total attempts per 24-hour window."
    ),
    stop_on_block: bool = typer.Option(
        True, help="Stop on ip_blocked or request_blocked."
    ),
    creator_diversify: bool = typer.Option(
        True, help="Diversify across creators rather than strict priority order."
    ),
    allow_translation: bool = typer.Option(
        False, help="Fall back to translatable non-English transcripts."
    ),
    rebuild_events_at_end: bool = typer.Option(
        False, help="Rebuild transcript events and exports after collection."
    ),
      log_path: Path = OVERNIGHT_LOG_PATH_OPTION,
      summary_path: Path = OVERNIGHT_SUMMARY_PATH_OPTION,
    dry_run: bool = typer.Option(
        False, help="Check readiness without fetching transcripts."
    ),
) -> None:
    from .overnight_supervisor import (
        acquire_lock,
        release_lock,
        run_overnight_transcript_collection,
    )

    if not acquire_lock():
        console.print(
            "[bold red]Lock file exists and process appears active. "
            "Refusing to start.[/bold red]"
        )
        raise typer.Exit(code=1)

    try:
        console.print(
            "[bold]Starting overnight transcript collection supervisor...[/bold]"
        )
        if dry_run:
            console.print("[bold yellow]DRY RUN mode — no transcripts will be fetched.[/bold yellow]")

        result = run_overnight_transcript_collection(
            batches=batches,
            batch_limit=batch_limit,
            between_batch_sleep_seconds=between_batch_sleep_seconds,
            sleep_seconds=sleep_seconds,
            jitter_seconds=jitter_seconds,
            max_per_creator=max_per_creator,
            min_disk_mb=min_disk_mb,
            cooldown_hours=cooldown_hours,
            max_daily_attempts=max_daily_attempts,
            stop_on_block=stop_on_block,
            creator_diversify=creator_diversify,
            allow_translation=allow_translation,
            rebuild_events_at_end=rebuild_events_at_end,
            log_path=log_path,
            summary_path=summary_path,
            dry_run=dry_run,
        )

        console.print()
        table = Table(title="Overnight Transcript Collection Summary")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Started at", str(result.started_at))
        table.add_row("Ended at", str(result.ended_at))
        table.add_row("Batches completed", f"{result.batches_completed}/{result.batches_requested}")
        table.add_row("Total attempted", str(result.total_attempted))
        table.add_row("Total available", str(result.total_available))
        table.add_row("Total no transcript", str(result.total_no_transcript))
        table.add_row("Total ip blocked", str(result.total_ip_blocked))
        table.add_row("Total request blocked", str(result.total_request_blocked))
        table.add_row("Total rate limited", str(result.total_rate_limited))
        table.add_row("Total other errors", str(result.total_other_errors))
        table.add_row("Transcripts start", str(result.starting_transcript_count))
        table.add_row("Transcripts end", str(result.ending_transcript_count))
        gain = result.ending_transcript_count - result.starting_transcript_count
        table.add_row("Transcript gain", str(gain))
        table.add_row("Disk start", f"{result.disk_start_mb:.0f} MB")
        table.add_row("Disk end", f"{result.disk_end_mb:.0f} MB")
        table.add_row("Stopped reason", result.stopped_reason or "none")
        table.add_row(
            "[bold]Recommended next action[/bold]",
            f"[bold]{result.recommended_next_action}[/bold]",
        )
        console.print(table)
        console.print(f"\nFull log: {log_path}")
        console.print(f"Summary file: {summary_path}")
    finally:
        release_lock()


@app.command("build-transcript-queue")
def build_transcript_queue_command() -> None:
    from .youtube_transcripts import _queue_stats, build_transcript_fetch_queue

    settings = get_settings()
    initialize_database()
    with connect() as conn:
        count = build_transcript_fetch_queue(
            conn, cooldown_hours=settings.transcript_queue_cooldown_hours
        )
    stats = _queue_stats()
    console.print(f"Built transcript fetch queue with {count} rows.")
    console.print(
        f"Total raw videos: {stats['total_videos']}. "
        f"Available transcripts: {stats['available_transcripts']}. "
        f"Failed statuses: {stats['failed_transcripts']}. "
        f"Excluded videos: {stats['excluded_videos']}. "
        f"Total pending raw videos: {stats['total_pending_raw_videos']}. "
        f"Retry-eligible: {stats['retry_eligible_pending']}. "
        f"Blocked/cooldown: {stats['blocked_or_cooldown']}."
    )


@app.command("preview-transcript-queue")
def preview_transcript_queue_command(
    limit: int = typer.Option(25, min=1, help="Number of queue entries to preview."),
) -> None:
    from .youtube_transcripts import _queue_stats, preview_transcript_queue

    stats = _queue_stats()
    console.print(
        f"Total raw videos: {stats['total_videos']}. "
        f"Available transcripts: {stats['available_transcripts']}. "
        f"Failed statuses: {stats['failed_transcripts']}. "
        f"Excluded videos: {stats['excluded_videos']}. "
        f"Total pending raw videos: {stats['total_pending_raw_videos']}. "
        f"Retry-eligible: {stats['retry_eligible_pending']}. "
        f"Blocked/cooldown: {stats['blocked_or_cooldown']}."
    )
    items = preview_transcript_queue(limit=limit)
    table = Table(title="Transcript Fetch Queue (top by priority)")
    table.add_column("Video ID", no_wrap=True)
    table.add_column("Channel")
    table.add_column("Priority", justify="right")
    table.add_column("Reason")
    for item in items:
        table.add_row(
            item.video_id,
            item.channel_title or "",
            f"{item.priority_score:.1f}",
            item.priority_reason,
        )
    console.print(table)


@app.command("export-transcript-training-windows")
def export_transcript_training_windows_command() -> None:
    from .transcript_exports import export_transcript_training_windows

    path = export_transcript_training_windows()
    console.print(f"transcript_training_windows: {path}")


@app.command("collect-youtube-metadata-expanded")
def collect_youtube_metadata_expanded_command(
    seed_file: str = typer.Option("data/seeds/youtube_creator_seeds.csv", help="Creator seed CSV path."),
    max_videos_per_channel: int = typer.Option(500, min=50, help="Max videos per channel."),
    published_after: str = typer.Option("2019-01-01", help="Earliest publish date YYYY-MM-DD."),
    dry_run: bool = typer.Option(False, help="Print quota estimate without calling the API."),
    only_creator: list[str] | None = None,
) -> None:
    from pathlib import Path as _Path

    from .youtube_metadata_expand import expand_metadata_from_seeds, load_creator_seeds

    if not get_settings().youtube_api_key:
        console.print("Skipping YouTube metadata expansion: YOUTUBE_API_KEY is not set.")
        return

    seeds = load_creator_seeds(_Path(seed_file))
    console.print(f"Loaded {len(seeds)} creator seeds from {seed_file}")

    table = Table(title="Creator Seeds")
    table.add_column("Creator")
    table.add_column("Category")
    table.add_column("Priority", justify="right")
    table.add_column("Identifier")
    for seed in seeds:
        table.add_row(
            seed.creator_name,
            seed.creator_category,
            str(seed.priority),
            seed.collection_identifier,
        )
    console.print(table)

    result = expand_metadata_from_seeds(
        seed_path=_Path(seed_file),
        max_videos_per_channel=max_videos_per_channel,
        published_after=published_after,
        dry_run=dry_run,
        only_channels=only_creator,
    )

    if dry_run:
        console.print(
            f"Dry run only. Estimated ~{result.estimated_quota_units} API quota units "
            f"for {result.creators_processed} channels. "
            f"Expected max processed videos: {result.expected_max_videos}."
        )
        return

    console.print(
        f"Metadata expansion complete. "
        f"Processed {result.creators_processed} seeds, "
        f"resolved {result.channels_resolved} channels, "
        f"collected {result.videos_collected} videos."
    )
    if result.unresolved_creators:
        console.print("Unresolved/skipped creators: " + ", ".join(result.unresolved_creators))
    for warning in result.warnings:
        console.print(f"WARNING: {warning}")


@app.command("backfill-youtube-seed-attribution")
def backfill_youtube_seed_attribution_command(
    seed_file: str = typer.Option("data/seeds/youtube_creator_seeds.csv", help="Creator seed CSV path."),
    refresh_attribution: bool = typer.Option(
        False,
        "--refresh-attribution",
        help="Overwrite existing non-empty seed attribution fields.",
    ),
) -> None:
    from pathlib import Path as _Path

    from .youtube_metadata_expand import backfill_youtube_seed_attribution

    if not get_settings().youtube_api_key:
        console.print("Skipping YouTube seed attribution backfill: YOUTUBE_API_KEY is not set.")
        return

    result = backfill_youtube_seed_attribution(
        seed_path=_Path(seed_file),
        refresh_attribution=refresh_attribution,
    )
    console.print(
        "YouTube seed attribution backfill complete. "
        f"Processed {result.seeds_processed} seeds, "
        f"resolved {result.channels_resolved} channels, "
        f"updated {result.rows_updated} rows."
    )
    if result.unresolved_creators:
        console.print("Unresolved/skipped creators: " + ", ".join(result.unresolved_creators))
    for warning in result.warnings:
        console.print(f"WARNING: {warning}")


@app.command("exclude-youtube-channel")
def exclude_youtube_channel_command(
    channel_id: str = typer.Option(..., help="YouTube channel ID to exclude from transcript queueing."),
    reason: str = typer.Option("bad_resolution", help="Audit reason for excluding the channel."),
) -> None:
    from .youtube_metadata_expand import exclude_youtube_channel

    result = exclude_youtube_channel(channel_id=channel_id, reason=reason)
    console.print(
        "YouTube channel exclusion complete. "
        f"channel_id={result.channel_id}, "
        f"rows_excluded={result.rows_excluded}, "
        f"queue_rows_marked={result.queue_rows_marked}, "
        f"reason={result.reason}."
    )


@app.command("discover-youtube-videos")
def discover_youtube_videos_command(
    queries_file: str = typer.Option("data/seeds/youtube_search_queries.csv", help="Search queries CSV path."),
    published_after: str = typer.Option("2019-01-01", help="Earliest publish date YYYY-MM-DD."),
    max_results_per_query: int = typer.Option(50, min=1, max=50),
    dry_run: bool = typer.Option(False, help="Print quota estimate without calling the API."),
) -> None:
    from pathlib import Path as _Path

    from .youtube_metadata_expand import discover_videos_from_queries, load_search_queries

    if not get_settings().youtube_api_key:
        console.print("Skipping YouTube video discovery: YOUTUBE_API_KEY is not set.")
        return

    queries = load_search_queries(_Path(queries_file))
    console.print(f"Loaded {len(queries)} search queries from {queries_file}")

    result = discover_videos_from_queries(
        query_path=_Path(queries_file),
        published_after=published_after,
        max_results_per_query=max_results_per_query,
        dry_run=dry_run,
    )

    if dry_run:
        console.print(
            f"Dry run only. Estimated ~{result.estimated_quota_units} API quota units "
            f"for {result.queries_processed} queries."
        )
        return

    console.print(
        f"Video discovery complete. "
        f"Processed {result.queries_processed} queries, "
        f"collected {result.videos_collected} videos."
    )


@app.command("transcript-collection-plan")
def transcript_collection_plan_command(
    target_limit: int = typer.Option(100, min=1, help="Target number of transcripts for planning."),
) -> None:
    from .youtube_metadata_expand import build_transcript_collection_plan

    plan = build_transcript_collection_plan(target_limit=target_limit)
    console.print(f"Total raw videos: {plan.total_videos}")
    console.print(f"Available transcripts: {plan.available_transcripts}")
    console.print(f"Failed transcript statuses: {plan.failed_transcripts}")
    console.print(f"Excluded videos: {plan.total_videos - plan.available_transcripts - plan.total_pending_raw_videos}")
    console.print(f"Total pending raw videos: {plan.total_pending_raw_videos}")
    console.print(f"Retry-eligible transcript queue: {plan.pending_transcripts}")
    console.print(f"Blocked/cooldown transcripts: {plan.blocked_or_cooldown_transcripts}")

    if plan.pending_by_category:
        cat_table = Table(title="Pending by Creator Category")
        cat_table.add_column("Category")
        cat_table.add_column("Count", justify="right")
        for category, count in sorted(plan.pending_by_category.items(), key=lambda x: -x[1]):
            cat_table.add_row(category, str(count))
        console.print(cat_table)

    if plan.recently_blocked:
        console.print("WARNING: IP blocked or request blocked within the last 24 hours.")
        console.print("  Do NOT run live transcript collection. Wait for the block to clear.")
    else:
        console.print("No recent blocking detected.")

    if plan.safe_to_collect:
        console.print(f"Recommended batch size: {plan.recommended_batch_size}")
        if plan.estimated_batches:
            batch_table = Table(title="Estimated Batches")
            batch_table.add_column("Batch Size", justify="right")
            batch_table.add_column("Batches", justify="right")
            for size, count in sorted(plan.estimated_batches.items()):
                batch_table.add_row(str(size), str(count))
            console.print(batch_table)
        console.print("")
        console.print("Recommended next dry-run command:")
        console.print(
            f"  python3 -m finfluencer_alpha collect-youtube-transcripts "
            f"--from-queue --limit {plan.recommended_batch_size} --dry-run"
        )
        console.print("Recommended next live command:")
        console.print(
            f"  python3 -m finfluencer_alpha collect-youtube-transcripts "
            f"--from-queue --limit {plan.recommended_batch_size}"
        )
    else:
        console.print("Transcript collection is NOT currently safe.")
        console.print("Reasons may include: recent blocks, no pending videos.")
        console.print("Try a dry-run first:")
        console.print(
            "  python3 -m finfluencer_alpha collect-youtube-transcripts "
            "--from-queue --limit 5 --dry-run"
        )


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
    safe["youtubetranscript_dev_api_key"] = bool(settings.youtubetranscript_dev_api_key)
    safe["transcriptapi_key"] = bool(settings.transcriptapi_key)
    console.print(json.dumps(safe, indent=2))


def main() -> None:
    app()
