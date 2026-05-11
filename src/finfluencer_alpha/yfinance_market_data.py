from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .config import EXPORTS_DIR, IMPORTS_DIR, ensure_data_dirs
from .ticker_aliases import DEFAULT_TICKER_ALIASES_PATH, load_ticker_aliases, resolve_data_ticker
from .utils import configure_csv_field_size_limit

MARKET_DATA_EXPORT_DIR = EXPORTS_DIR / "market_data"
MARKET_DATA_IMPORT_DIR = IMPORTS_DIR / "market_data"

DEFAULT_MARKET_DATA_REQUEST_PATH = MARKET_DATA_EXPORT_DIR / "market_data_request.csv"
DEFAULT_UNIQUE_TICKERS_PATH = MARKET_DATA_EXPORT_DIR / "unique_tickers.csv"
DEFAULT_YFINANCE_OUTPUT_PATH = MARKET_DATA_IMPORT_DIR / "yfinance_market_data.csv"
DEFAULT_YFINANCE_SUMMARY_MD_PATH = MARKET_DATA_EXPORT_DIR / "yfinance_fetch_summary.md"
DEFAULT_YFINANCE_SUMMARY_CSV_PATH = MARKET_DATA_EXPORT_DIR / "yfinance_fetch_summary.csv"

YFINANCE_MARKET_DATA_COLUMNS = [
    "original_ticker",
    "ticker",
    "date",
    "adjusted_close",
    "volume",
    "benchmark_ticker",
    "benchmark_adjusted_close",
    "market_cap",
    "sector",
    "industry",
    "beta",
    "average_dollar_volume",
    "data_source",
    "downloaded_at_utc",
]

YFINANCE_SUMMARY_COLUMNS = [
    "original_ticker",
    "data_ticker",
    "ticker_alias_applied",
    "ticker",
    "role",
    "status",
    "row_count",
    "first_date",
    "last_date",
    "error",
]

Downloader = Callable[[str, date, date], pd.DataFrame]


@dataclass(frozen=True)
class YFinanceFetchPlan:
    tickers: list[str]
    data_ticker_by_original: dict[str, str]
    alias_mappings: tuple[tuple[str, str], ...]
    benchmark: str
    start_date: date
    end_date: date
    output_path: Path
    summary_md_path: Path
    summary_csv_path: Path


@dataclass(frozen=True)
class YFinanceFetchResult:
    output_path: Path
    summary_md_path: Path
    summary_csv_path: Path
    tickers_requested: int
    tickers_downloaded: int
    failed_tickers: tuple[str, ...]
    rows_written: int
    start_date: str
    end_date: str
    benchmark: str
    dry_run: bool


def _clean(value: object) -> str:
    return str(value or "").strip()


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


def _parse_date(value: object, *, field_name: str) -> date:
    text = _clean(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Could not parse {field_name}: {text}") from exc


def _unique_tickers(rows: list[dict[str, str]]) -> list[str]:
    tickers = sorted({_clean(row.get("ticker")).upper() for row in rows if _clean(row.get("ticker"))})
    if not tickers:
        raise ValueError("No tickers found in unique_tickers input.")
    return tickers


def _resolve_data_tickers(
    *,
    tickers: list[str],
    ticker_aliases_path: Path,
) -> tuple[dict[str, str], tuple[tuple[str, str], ...]]:
    aliases = load_ticker_aliases(ticker_aliases_path)
    resolved: dict[str, str] = {}
    alias_pairs: list[tuple[str, str]] = []
    for ticker in tickers:
        resolved_ticker, alias_applied = resolve_data_ticker(ticker, aliases=aliases)
        resolved[ticker] = resolved_ticker
        if alias_applied:
            alias_pairs.append((ticker, resolved_ticker))
    alias_pairs = sorted(set(alias_pairs))
    return resolved, tuple(alias_pairs)


def build_yfinance_fetch_plan(
    *,
    input_request_path: Path = DEFAULT_MARKET_DATA_REQUEST_PATH,
    input_tickers_path: Path = DEFAULT_UNIQUE_TICKERS_PATH,
    output_path: Path = DEFAULT_YFINANCE_OUTPUT_PATH,
    summary_md_path: Path = DEFAULT_YFINANCE_SUMMARY_MD_PATH,
    summary_csv_path: Path = DEFAULT_YFINANCE_SUMMARY_CSV_PATH,
    ticker_aliases_path: Path = DEFAULT_TICKER_ALIASES_PATH,
    benchmark: str = "SPY",
    buffer_days: int = 10,
) -> YFinanceFetchPlan:
    if not input_request_path.exists():
        raise FileNotFoundError(f"Market-data request input not found: {input_request_path}")
    if not input_tickers_path.exists():
        raise FileNotFoundError(f"Unique tickers input not found: {input_tickers_path}")
    if buffer_days < 0:
        raise ValueError("buffer_days must be non-negative")
    request_rows = _read_csv(input_request_path)
    ticker_rows = _read_csv(input_tickers_path)
    start_dates = [
        _parse_date(row.get("recommended_start_date"), field_name="recommended_start_date")
        for row in request_rows
        if _clean(row.get("recommended_start_date"))
    ]
    end_dates = [
        _parse_date(row.get("recommended_end_date"), field_name="recommended_end_date")
        for row in request_rows
        if _clean(row.get("recommended_end_date"))
    ]
    if not start_dates or not end_dates:
        raise ValueError("Market-data request must include recommended_start_date and recommended_end_date.")
    tickers = _unique_tickers(ticker_rows)
    data_ticker_by_original, alias_mappings = _resolve_data_tickers(
        tickers=tickers,
        ticker_aliases_path=ticker_aliases_path,
    )
    return YFinanceFetchPlan(
        tickers=tickers,
        data_ticker_by_original=data_ticker_by_original,
        alias_mappings=alias_mappings,
        benchmark=_clean(benchmark).upper() or "SPY",
        start_date=min(start_dates) - timedelta(days=buffer_days),
        end_date=max(end_dates) + timedelta(days=buffer_days),
        output_path=output_path,
        summary_md_path=summary_md_path,
        summary_csv_path=summary_csv_path,
    )


def _default_downloader(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    import yfinance as yf

    return yf.download(
        ticker,
        start=start_date.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        progress=False,
        threads=False,
    )


def _flatten_single_ticker_frame(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        if ticker in frame.columns.get_level_values(0):
            return frame[ticker].copy()
        if ticker.upper() in frame.columns.get_level_values(0):
            return frame[ticker.upper()].copy()
        if ticker in frame.columns.get_level_values(-1):
            return frame.xs(ticker, axis=1, level=-1).copy()
        if ticker.upper() in frame.columns.get_level_values(-1):
            return frame.xs(ticker.upper(), axis=1, level=-1).copy()
        if len(frame.columns.levels) > 1:
            flattened = frame.copy()
            flattened.columns = [
                " ".join(str(part) for part in column if str(part)) for column in flattened.columns
            ]
            return flattened
    return frame.copy()


def _history_rows(
    *,
    original_ticker: str,
    ticker: str,
    frame: pd.DataFrame,
    benchmark_ticker: str,
    benchmark_by_date: dict[str, float],
    downloaded_at_utc: str,
) -> list[dict[str, Any]]:
    normalized = _flatten_single_ticker_frame(frame, ticker)
    if normalized.empty:
        return []
    adjusted_column = "Adj Close" if "Adj Close" in normalized.columns else "Close"
    if adjusted_column not in normalized.columns:
        return []
    volume_column = "Volume" if "Volume" in normalized.columns else ""
    rows: list[dict[str, Any]] = []
    for index, record in normalized.iterrows():
        date_value = pd.Timestamp(index).date().isoformat()
        adjusted_close = record.get(adjusted_column)
        if pd.isna(adjusted_close):
            continue
        volume = record.get(volume_column) if volume_column else ""
        rows.append(
            {
                "original_ticker": original_ticker,
                "ticker": ticker,
                "date": date_value,
                "adjusted_close": float(adjusted_close),
                "volume": "" if pd.isna(volume) else int(volume),
                "benchmark_ticker": benchmark_ticker,
                "benchmark_adjusted_close": benchmark_by_date.get(date_value, ""),
                "market_cap": "",
                "sector": "",
                "industry": "",
                "beta": "",
                "average_dollar_volume": "",
                "data_source": "yfinance_yahoo_prototype",
                "downloaded_at_utc": downloaded_at_utc,
            }
        )
    return rows


def _benchmark_by_date(frame: pd.DataFrame, benchmark: str) -> dict[str, float]:
    normalized = _flatten_single_ticker_frame(frame, benchmark)
    if normalized.empty:
        return {}
    adjusted_column = "Adj Close" if "Adj Close" in normalized.columns else "Close"
    if adjusted_column not in normalized.columns:
        return {}
    values: dict[str, float] = {}
    for index, record in normalized.iterrows():
        adjusted_close = record.get(adjusted_column)
        if not pd.isna(adjusted_close):
            values[pd.Timestamp(index).date().isoformat()] = float(adjusted_close)
    return values


def _summary_row(
    original_ticker: str,
    data_ticker: str,
    ticker: str,
    *,
    role: str,
    status: str,
    ticker_alias_applied: bool = False,
    rows: list[dict[str, Any]] | None = None,
    error: str = "",
) -> dict[str, Any]:
    rows = rows or []
    dates = sorted(_clean(row.get("date")) for row in rows if _clean(row.get("date")))
    return {
        "original_ticker": original_ticker,
        "data_ticker": data_ticker,
        "ticker_alias_applied": ticker_alias_applied,
        "ticker": ticker,
        "role": role,
        "status": status,
        "row_count": len(rows),
        "first_date": dates[0] if dates else "",
        "last_date": dates[-1] if dates else "",
        "error": error,
    }


def _validate_unique_ticker_dates(rows: list[dict[str, Any]]) -> None:
    keys = [(row["ticker"], row["date"]) for row in rows]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        example = ", ".join(f"{ticker}/{date_value}" for ticker, date_value in duplicates[:5])
        raise ValueError(f"Duplicate ticker/date rows in yfinance output: {example}")


def _event_window_warning_count(
    request_rows: list[dict[str, str]],
    rows_by_ticker: dict[str, list[dict[str, Any]]],
) -> int:
    warning_count = 0
    for request in request_rows:
        ticker = _clean(request.get("ticker")).upper()
        start = _clean(request.get("recommended_start_date"))
        end = _clean(request.get("recommended_end_date"))
        event_date = _clean(request.get("event_date_weekday_adjusted"))
        ticker_rows = rows_by_ticker.get(ticker, [])
        dates = sorted(_clean(row.get("date")) for row in ticker_rows)
        window_dates = [date_value for date_value in dates if start <= date_value <= end]
        has_pre_event = any(date_value <= event_date for date_value in window_dates)
        has_post_event = any(date_value >= event_date for date_value in window_dates)
        if len(window_dates) < 30 or not has_pre_event or not has_post_event:
            warning_count += 1
    return warning_count


def _write_summary_markdown(
    path: Path,
    *,
    plan: YFinanceFetchPlan,
    request_path: Path,
    tickers_path: Path,
    summary_rows: list[dict[str, Any]],
    rows_written: int,
    benchmark_missing_count: int,
    sparse_window_count: int,
    dry_run: bool,
) -> Path:
    failed = [row["original_ticker"] for row in summary_rows if row["status"] == "failed"]
    downloaded = [
        row["data_ticker"]
        for row in summary_rows
        if row["role"] == "security" and row["status"] == "downloaded"
    ]
    alias_mappings = [
        (row["original_ticker"], row["data_ticker"])
        for row in summary_rows
        if row["role"] == "security" and bool(row.get("ticker_alias_applied"))
    ]
    alias_mappings = sorted(set(alias_mappings))
    lines = [
        "# yfinance Prototype Market Data Fetch Summary",
        "",
        "This is interim Yahoo/yfinance prototype data, not Bloomberg data. "
        "Final research results should use Bloomberg where possible.",
        "",
        f"- Market-data request input: `{request_path}`",
        f"- Unique tickers input: `{tickers_path}`",
        f"- Output CSV: `{plan.output_path}`",
        f"- Date range requested: {plan.start_date} to {plan.end_date}",
        f"- Benchmark: {plan.benchmark}",
        f"- Dry run: {dry_run}",
        f"- Requested original security tickers: {len(plan.tickers)}",
        f"- Downloaded data security tickers: {len(set(downloaded))}",
        f"- Alias mappings applied: {len(alias_mappings)}",
        f"- Rows written: {rows_written}",
        f"- Missing benchmark values on ticker rows: {benchmark_missing_count}",
        f"- Event windows with sparse yfinance coverage warning: {sparse_window_count}",
        "",
        "## Adjusted Close Handling",
        "",
        "`Adj Close` is used when yfinance returns it. If `Adj Close` is unavailable, "
        "`Close` is used as a fallback. The downloader calls yfinance with `auto_adjust=False`.",
        "",
        "## Downloaded Tickers",
        "",
    ]
    lines.extend([f"- {ticker}" for ticker in downloaded] or ["- None."])
    lines.extend(["", "## Alias Mappings Applied", ""])
    lines.extend([f"- {original} -> {data}" for original, data in alias_mappings] or ["- None."])
    lines.extend(["", "## Failed Tickers", ""])
    lines.extend([f"- {ticker}" for ticker in failed] or ["- None."])
    lines.extend(
        [
            "",
            "## Provenance Warning",
            "",
            "Do not commit raw/interim downloaded market data. Store it under "
            "`data/imports/market_data/` and replace it with Bloomberg data before final results.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def fetch_yfinance_market_data(
    *,
    input_request_path: Path = DEFAULT_MARKET_DATA_REQUEST_PATH,
    input_tickers_path: Path = DEFAULT_UNIQUE_TICKERS_PATH,
    output_path: Path = DEFAULT_YFINANCE_OUTPUT_PATH,
    summary_md_path: Path = DEFAULT_YFINANCE_SUMMARY_MD_PATH,
    summary_csv_path: Path = DEFAULT_YFINANCE_SUMMARY_CSV_PATH,
    ticker_aliases_path: Path = DEFAULT_TICKER_ALIASES_PATH,
    benchmark: str = "SPY",
    buffer_days: int = 10,
    confirm_yfinance_run: bool = False,
    dry_run: bool = False,
    downloader: Downloader | None = None,
) -> YFinanceFetchResult:
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
    if dry_run:
        return YFinanceFetchResult(
            output_path=plan.output_path,
            summary_md_path=plan.summary_md_path,
            summary_csv_path=plan.summary_csv_path,
            tickers_requested=len(plan.tickers),
            tickers_downloaded=0,
            failed_tickers=(),
            rows_written=0,
            start_date=plan.start_date.isoformat(),
            end_date=plan.end_date.isoformat(),
            benchmark=plan.benchmark,
            dry_run=True,
        )
    if not confirm_yfinance_run:
        raise PermissionError(
            "Refusing yfinance download. Re-run with --confirm-yfinance-run to fetch interim Yahoo/yfinance data."
        )

    ensure_data_dirs()
    request_rows = _read_csv(input_request_path)
    active_downloader = downloader or _default_downloader
    downloaded_at_utc = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    summary_rows: list[dict[str, Any]] = []
    try:
        benchmark_frame = active_downloader(plan.benchmark, plan.start_date, plan.end_date)
    except Exception as exc:
        raise RuntimeError(f"Benchmark download failed for {plan.benchmark}: {exc}") from exc
    benchmark_values = _benchmark_by_date(benchmark_frame, plan.benchmark)
    if not benchmark_values:
        raise RuntimeError(f"Benchmark download returned no usable adjusted close data for {plan.benchmark}.")
    summary_rows.append(
        _summary_row(
            original_ticker=plan.benchmark,
            data_ticker=plan.benchmark,
            ticker=plan.benchmark,
            ticker_alias_applied=False,
            role="benchmark",
            status="downloaded",
            rows=[
                {"date": date_value, "adjusted_close": adjusted_close}
                for date_value, adjusted_close in benchmark_values.items()
            ],
        )
    )

    all_rows: list[dict[str, Any]] = []
    rows_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    failed_tickers: list[str] = []
    for original_ticker in plan.tickers:
        data_ticker = plan.data_ticker_by_original.get(original_ticker, original_ticker)
        alias_applied = data_ticker != original_ticker
        try:
            frame = active_downloader(data_ticker, plan.start_date, plan.end_date)
            ticker_rows = _history_rows(
                original_ticker=original_ticker,
                ticker=data_ticker,
                frame=frame,
                benchmark_ticker=plan.benchmark,
                benchmark_by_date=benchmark_values,
                downloaded_at_utc=downloaded_at_utc,
            )
            if not ticker_rows:
                failed_tickers.append(original_ticker)
                summary_rows.append(
                    _summary_row(
                        original_ticker=original_ticker,
                        data_ticker=data_ticker,
                        ticker=data_ticker,
                        role="security",
                        status="failed",
                        ticker_alias_applied=alias_applied,
                        error="download returned no usable adjusted close rows",
                    )
                )
                continue
            all_rows.extend(ticker_rows)
            rows_by_ticker[original_ticker].extend(ticker_rows)
            summary_rows.append(
                _summary_row(
                    original_ticker=original_ticker,
                    data_ticker=data_ticker,
                    ticker=data_ticker,
                    role="security",
                    status="downloaded",
                    ticker_alias_applied=alias_applied,
                    rows=ticker_rows,
                )
            )
        except Exception as exc:
            failed_tickers.append(original_ticker)
            summary_rows.append(
                _summary_row(
                    original_ticker=original_ticker,
                    data_ticker=data_ticker,
                    ticker=data_ticker,
                    role="security",
                    status="failed",
                    ticker_alias_applied=alias_applied,
                    error=str(exc),
                )
            )

    all_rows.sort(key=lambda row: (row["ticker"], row["date"]))
    _validate_unique_ticker_dates(all_rows)
    benchmark_missing_count = sum(
        1 for row in all_rows if _clean(row.get("benchmark_adjusted_close")) == ""
    )
    sparse_window_count = _event_window_warning_count(request_rows, rows_by_ticker)
    _write_csv(output_path, all_rows, YFINANCE_MARKET_DATA_COLUMNS)
    _write_csv(summary_csv_path, summary_rows, YFINANCE_SUMMARY_COLUMNS)
    _write_summary_markdown(
        summary_md_path,
        plan=plan,
        request_path=input_request_path,
        tickers_path=input_tickers_path,
        summary_rows=summary_rows,
        rows_written=len(all_rows),
        benchmark_missing_count=benchmark_missing_count,
        sparse_window_count=sparse_window_count,
        dry_run=False,
    )
    return YFinanceFetchResult(
        output_path=output_path,
        summary_md_path=summary_md_path,
        summary_csv_path=summary_csv_path,
        tickers_requested=len(plan.tickers),
        tickers_downloaded=len(plan.tickers) - len(failed_tickers),
        failed_tickers=tuple(failed_tickers),
        rows_written=len(all_rows),
        start_date=plan.start_date.isoformat(),
        end_date=plan.end_date.isoformat(),
        benchmark=plan.benchmark,
        dry_run=False,
    )
