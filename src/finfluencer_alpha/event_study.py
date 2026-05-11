from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import EXPORTS_DIR, IMPORTS_DIR, ensure_data_dirs
from .market_data_prep import weekday_adjust_event_date
from .ticker_aliases import DEFAULT_TICKER_ALIASES_PATH, load_ticker_aliases, resolve_data_ticker
from .utils import configure_csv_field_size_limit
from .yfinance_market_data import YFINANCE_MARKET_DATA_COLUMNS

MARKET_DATA_IMPORT_DIR = IMPORTS_DIR / "market_data"
EVENT_STUDY_DIR = EXPORTS_DIR / "event_study"
VALIDATION_DIR = EXPORTS_DIR / "validation"

DEFAULT_BLOOMBERG_MARKET_DATA_PATH = MARKET_DATA_IMPORT_DIR / "bloomberg_market_data.csv"
DEFAULT_YFINANCE_MARKET_DATA_PATH = MARKET_DATA_IMPORT_DIR / "yfinance_market_data.csv"
DEFAULT_CLEAN_EVENTS_PATH = VALIDATION_DIR / "clean_auto_labeled_events.csv"
DEFAULT_EVENT_STUDY_OUTPUT_PATH = EVENT_STUDY_DIR / "event_study_results.csv"
DEFAULT_EVENT_STUDY_SUMMARY_PATH = EVENT_STUDY_DIR / "event_study_summary.md"

EVENT_STUDY_COLUMNS = [
    "event_id",
    "ticker",
    "data_ticker",
    "ticker_alias_applied",
    "event_date_weekday_adjusted",
    "matched_market_date",
    "recommendation_type",
    "direction",
    "confidence",
    "adjusted_close",
    "benchmark_ticker",
    "benchmark_adjusted_close",
    "return_1d",
    "benchmark_return_1d",
    "abnormal_return_1d",
    "return_5d",
    "benchmark_return_5d",
    "abnormal_return_5d",
    "data_source",
]

REQUIRED_MARKET_DATA_COLUMNS = [column for column in YFINANCE_MARKET_DATA_COLUMNS if column != "original_ticker"]


@dataclass(frozen=True)
class MarketDataValidationResult:
    input_path: Path
    row_count: int
    ticker_count: int
    min_date: str
    max_date: str
    data_sources: tuple[str, ...]
    duplicate_count: int
    missing_adjusted_close_count: int
    missing_benchmark_count: int


@dataclass(frozen=True)
class MarketDataSourceSelection:
    path: Path
    source_name: str
    warning: str


@dataclass(frozen=True)
class EventStudyResult:
    output_path: Path
    summary_md_path: Path
    events_processed: int
    events_matched: int
    market_data_path: Path
    warning: str


def _clean(value: object) -> str:
    return str(value or "").strip()


def _float_or_none(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _parse_date_text(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()


def _event_date(row: dict[str, Any]) -> str:
    if _clean(row.get("event_date_weekday_adjusted")):
        return _parse_date_text(row.get("event_date_weekday_adjusted"))
    if _clean(row.get("published_at")):
        raw_date = datetime.fromisoformat(_clean(row.get("published_at")).replace("Z", "+00:00")).date()
        return weekday_adjust_event_date(raw_date).isoformat()
    return _parse_date_text(row.get("event_date_utc"))


def validate_market_data_import(
    *,
    input_path: Path,
) -> MarketDataValidationResult:
    if not input_path.exists():
        raise FileNotFoundError(f"Market-data import not found: {input_path}")
    rows = _read_csv(input_path)
    if not rows:
        raise ValueError(f"Market-data import contains no rows: {input_path}")
    missing_columns = [column for column in REQUIRED_MARKET_DATA_COLUMNS if column not in rows[0]]
    if missing_columns:
        raise ValueError("Market-data import is missing required columns: " + ", ".join(missing_columns))
    keys = [(_clean(row.get("ticker")).upper(), _parse_date_text(row.get("date"))) for row in rows]
    duplicate_count = len(keys) - len(set(keys))
    if duplicate_count:
        raise ValueError(f"Market-data import has {duplicate_count} duplicate ticker/date rows.")
    dates = sorted(date_text for _, date_text in keys if date_text)
    tickers = sorted({ticker for ticker, _ in keys if ticker})
    data_sources = sorted({_clean(row.get("data_source")) or "unknown" for row in rows})
    missing_adjusted_close_count = sum(1 for row in rows if _float_or_none(row.get("adjusted_close")) is None)
    missing_benchmark_count = sum(
        1 for row in rows if _float_or_none(row.get("benchmark_adjusted_close")) is None
    )
    return MarketDataValidationResult(
        input_path=input_path,
        row_count=len(rows),
        ticker_count=len(tickers),
        min_date=dates[0] if dates else "",
        max_date=dates[-1] if dates else "",
        data_sources=tuple(data_sources),
        duplicate_count=duplicate_count,
        missing_adjusted_close_count=missing_adjusted_close_count,
        missing_benchmark_count=missing_benchmark_count,
    )


def select_market_data_source(
    *,
    input_market_data: Path | None = None,
    market_data_source: str = "auto",
) -> MarketDataSourceSelection:
    if input_market_data is not None:
        source_name = "yfinance" if "yfinance" in input_market_data.name.lower() else "explicit"
        warning = (
            "Using interim yfinance market data. Replace with Bloomberg data for final results."
            if source_name == "yfinance"
            else ""
        )
        return MarketDataSourceSelection(input_market_data, source_name, warning)
    source = _clean(market_data_source).lower() or "auto"
    if source not in {"auto", "bloomberg", "yfinance"}:
        raise ValueError("market_data_source must be one of: auto, bloomberg, yfinance")
    if source == "bloomberg":
        return MarketDataSourceSelection(DEFAULT_BLOOMBERG_MARKET_DATA_PATH, "bloomberg", "")
    if source == "yfinance":
        return MarketDataSourceSelection(
            DEFAULT_YFINANCE_MARKET_DATA_PATH,
            "yfinance",
            "Using interim yfinance market data. Replace with Bloomberg data for final results.",
        )
    if DEFAULT_BLOOMBERG_MARKET_DATA_PATH.exists():
        return MarketDataSourceSelection(DEFAULT_BLOOMBERG_MARKET_DATA_PATH, "bloomberg", "")
    if DEFAULT_YFINANCE_MARKET_DATA_PATH.exists():
        return MarketDataSourceSelection(
            DEFAULT_YFINANCE_MARKET_DATA_PATH,
            "yfinance",
            "Using interim yfinance market data. Replace with Bloomberg data for final results.",
        )
    raise FileNotFoundError(
        f"No market-data import found at {DEFAULT_BLOOMBERG_MARKET_DATA_PATH} or "
        f"{DEFAULT_YFINANCE_MARKET_DATA_PATH}."
    )


def _market_rows_by_ticker(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        ticker = _clean(row.get("ticker")).upper()
        grouped.setdefault(ticker, []).append(row)
    for ticker_rows in grouped.values():
        ticker_rows.sort(key=lambda row: _parse_date_text(row.get("date")))
    return grouped


def _first_row_on_or_after(rows: list[dict[str, str]], event_date: str) -> int | None:
    for index, row in enumerate(rows):
        if _parse_date_text(row.get("date")) >= event_date:
            return index
    return None


def _return_at(rows: list[dict[str, str]], start_index: int, horizon: int, price_key: str) -> float | None:
    end_index = start_index + horizon
    if end_index >= len(rows):
        return None
    start_price = _float_or_none(rows[start_index].get(price_key))
    end_price = _float_or_none(rows[end_index].get(price_key))
    if start_price in (None, 0) or end_price is None:
        return None
    return round((end_price / start_price) - 1, 6)


def _format_float(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def _event_study_row(
    event: dict[str, str],
    market_rows: list[dict[str, str]],
    *,
    data_ticker: str,
    ticker_alias_applied: bool,
    start_index: int,
) -> dict[str, Any]:
    market_row = market_rows[start_index]
    return_1d = _return_at(market_rows, start_index, 1, "adjusted_close")
    benchmark_return_1d = _return_at(market_rows, start_index, 1, "benchmark_adjusted_close")
    return_5d = _return_at(market_rows, start_index, 5, "adjusted_close")
    benchmark_return_5d = _return_at(market_rows, start_index, 5, "benchmark_adjusted_close")
    abnormal_1d = (
        round(return_1d - benchmark_return_1d, 6)
        if return_1d is not None and benchmark_return_1d is not None
        else None
    )
    abnormal_5d = (
        round(return_5d - benchmark_return_5d, 6)
        if return_5d is not None and benchmark_return_5d is not None
        else None
    )
    return {
        "event_id": _clean(event.get("event_id")),
        "ticker": _clean(event.get("ticker")).upper(),
        "data_ticker": data_ticker,
        "ticker_alias_applied": ticker_alias_applied,
        "event_date_weekday_adjusted": _event_date(event),
        "matched_market_date": _parse_date_text(market_row.get("date")),
        "recommendation_type": _clean(event.get("recommendation_type")),
        "direction": _clean(event.get("direction")),
        "confidence": _clean(event.get("confidence") or event.get("auto_label_confidence")),
        "adjusted_close": _clean(market_row.get("adjusted_close")),
        "benchmark_ticker": _clean(market_row.get("benchmark_ticker")),
        "benchmark_adjusted_close": _clean(market_row.get("benchmark_adjusted_close")),
        "return_1d": _format_float(return_1d),
        "benchmark_return_1d": _format_float(benchmark_return_1d),
        "abnormal_return_1d": _format_float(abnormal_1d),
        "return_5d": _format_float(return_5d),
        "benchmark_return_5d": _format_float(benchmark_return_5d),
        "abnormal_return_5d": _format_float(abnormal_5d),
        "data_source": _clean(market_row.get("data_source")),
    }


def _write_event_study_summary(
    path: Path,
    *,
    events_path: Path,
    market_data_path: Path,
    rows: list[dict[str, Any]],
    processed_count: int,
    warning: str,
) -> Path:
    lines = [
        "# Event Study Prototype Summary",
        "",
        f"- Events input: `{events_path}`",
        f"- Market-data input: `{market_data_path}`",
        f"- Events processed: {processed_count}",
        f"- Events matched to market data: {len(rows)}",
        f"- Warning: {warning or 'None'}",
        "",
        "This is a prototype event-study join and return calculation. Final inference should use "
        "Bloomberg market data where possible.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_event_study(
    *,
    input_events: Path = DEFAULT_CLEAN_EVENTS_PATH,
    input_market_data: Path | None = None,
    market_data_source: str = "auto",
    ticker_aliases_path: Path = DEFAULT_TICKER_ALIASES_PATH,
    output_path: Path = DEFAULT_EVENT_STUDY_OUTPUT_PATH,
    summary_md_path: Path = DEFAULT_EVENT_STUDY_SUMMARY_PATH,
) -> EventStudyResult:
    if not input_events.exists():
        raise FileNotFoundError(f"Clean event input not found: {input_events}")
    selection = select_market_data_source(
        input_market_data=input_market_data,
        market_data_source=market_data_source,
    )
    validate_market_data_import(input_path=selection.path)
    ensure_data_dirs()
    events = _read_csv(input_events)
    market_rows = _read_csv(selection.path)
    aliases = load_ticker_aliases(ticker_aliases_path)
    grouped_market_rows = _market_rows_by_ticker(market_rows)
    result_rows: list[dict[str, Any]] = []
    for event in events:
        event_ticker = _clean(event.get("ticker")).upper()
        event_date = _event_date(event)
        data_ticker, alias_applied = resolve_data_ticker(
            event_ticker,
            aliases=aliases,
            event_date=event_date,
        )
        ticker_rows = grouped_market_rows.get(data_ticker, [])
        if not ticker_rows:
            continue
        start_index = _first_row_on_or_after(ticker_rows, event_date)
        if start_index is None:
            continue
        result_rows.append(
            _event_study_row(
                event,
                ticker_rows,
                data_ticker=data_ticker,
                ticker_alias_applied=alias_applied,
                start_index=start_index,
            )
        )
    _write_csv(output_path, result_rows, EVENT_STUDY_COLUMNS)
    _write_event_study_summary(
        summary_md_path,
        events_path=input_events,
        market_data_path=selection.path,
        rows=result_rows,
        processed_count=len(events),
        warning=selection.warning,
    )
    return EventStudyResult(
        output_path=output_path,
        summary_md_path=summary_md_path,
        events_processed=len(events),
        events_matched=len(result_rows),
        market_data_path=selection.path,
        warning=selection.warning,
    )
