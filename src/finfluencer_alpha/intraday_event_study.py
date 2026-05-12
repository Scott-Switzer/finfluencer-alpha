from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .config import EXPORTS_DIR, IMPORTS_DIR, ensure_data_dirs
from .ticker_aliases import DEFAULT_TICKER_ALIASES_PATH, load_ticker_aliases, resolve_data_ticker
from .utils import configure_csv_field_size_limit

INTRADAY_EXPORT_DIR = EXPORTS_DIR / "intraday"
INTRADAY_CHARTS_DIR = INTRADAY_EXPORT_DIR / "charts"
MARKET_DATA_IMPORT_DIR = IMPORTS_DIR / "market_data"
VALIDATION_DIR = EXPORTS_DIR / "validation"

DEFAULT_CLEAN_EVENTS_PATH = VALIDATION_DIR / "clean_auto_labeled_events.csv"
DEFAULT_INTRADAY_FEASIBILITY_PATH = INTRADAY_EXPORT_DIR / "intraday_event_feasibility.csv"
DEFAULT_INTRADAY_FEASIBILITY_SUMMARY_PATH = INTRADAY_EXPORT_DIR / "intraday_event_feasibility_summary.md"
DEFAULT_INTRADAY_MARKET_DATA_PATH = MARKET_DATA_IMPORT_DIR / "yfinance_intraday_market_data.csv"
DEFAULT_INTRADAY_FETCH_SUMMARY_MD_PATH = INTRADAY_EXPORT_DIR / "yfinance_intraday_fetch_summary.md"
DEFAULT_INTRADAY_FETCH_SUMMARY_CSV_PATH = INTRADAY_EXPORT_DIR / "yfinance_intraday_fetch_summary.csv"
DEFAULT_INTRADAY_RESULTS_PATH = INTRADAY_EXPORT_DIR / "intraday_event_study_results.csv"
DEFAULT_INTRADAY_SUMMARY_MD_PATH = INTRADAY_EXPORT_DIR / "intraday_event_study_summary.md"
DEFAULT_INTRADAY_BY_CREATOR_PATH = INTRADAY_EXPORT_DIR / "intraday_event_study_by_creator.csv"
DEFAULT_INTRADAY_BY_TICKER_PATH = INTRADAY_EXPORT_DIR / "intraday_event_study_by_ticker.csv"
DEFAULT_INTRADAY_METHOD_NOTE_PATH = INTRADAY_EXPORT_DIR / "intraday_methodology_note.md"

NY_TZ = ZoneInfo("America/New_York")

INTRADAY_FEASIBILITY_COLUMNS = [
    "event_id",
    "ticker",
    "data_ticker",
    "creator",
    "title",
    "published_at",
    "event_timestamp_utc",
    "event_date",
    "days_from_now",
    "yfinance_intraday_eligible",
    "reason",
]

INTRADAY_MARKET_DATA_COLUMNS = [
    "event_id",
    "original_ticker",
    "data_ticker",
    "datetime_utc",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "benchmark_ticker",
    "benchmark_close",
    "interval",
    "data_source",
    "downloaded_at_utc",
]

INTRADAY_FETCH_SUMMARY_COLUMNS = [
    "event_id",
    "original_ticker",
    "data_ticker",
    "status",
    "row_count",
    "window_start_utc",
    "window_end_utc",
    "error",
]

INTRADAY_RESULT_COLUMNS = [
    "event_id",
    "ticker",
    "data_ticker",
    "creator",
    "title",
    "published_at",
    "event_timestamp_utc",
    "event_timestamp_aligned_utc",
    "event_timestamp_aligned_et",
    "recommendation_type",
    "direction",
    "return_5m",
    "return_15m",
    "return_30m",
    "return_60m",
    "return_to_close",
    "benchmark_return_5m",
    "benchmark_return_15m",
    "benchmark_return_30m",
    "benchmark_return_60m",
    "benchmark_return_to_close",
    "abnormal_return_5m",
    "abnormal_return_15m",
    "abnormal_return_30m",
    "abnormal_return_60m",
    "abnormal_return_to_close",
    "pre_event_return_60m",
    "volume_change_30m",
    "volume_change_60m",
    "missing_intraday_data_flag",
    "missing_intraday_data_reason",
    "data_source",
]

INTRADAY_GROUP_COLUMNS = [
    "group",
    "event_count",
    "matched_count",
    "mean_abnormal_return_5m",
    "mean_abnormal_return_15m",
    "mean_abnormal_return_30m",
    "mean_abnormal_return_60m",
    "mean_abnormal_return_to_close",
]


Downloader = Callable[[str, datetime, datetime, str], pd.DataFrame]


@dataclass(frozen=True)
class IntradayFeasibilityResult:
    output_path: Path
    summary_md_path: Path
    total_events: int
    eligible_events: int


@dataclass(frozen=True)
class IntradayFetchResult:
    output_path: Path
    summary_md_path: Path
    summary_csv_path: Path
    eligible_events: int
    tickers_downloaded: int
    rows_written: int
    failed_tickers: tuple[str, ...]
    dry_run: bool
    planned_event_windows: int = 0
    max_window_days: float = 0.0
    events_excluded_outside_1m_limit: int = 0
    shifted_windows: int = 0


@dataclass(frozen=True)
class IntradayEventStudyResult:
    output_path: Path
    summary_md_path: Path
    by_creator_path: Path
    by_ticker_path: Path
    methodology_note_path: Path
    events_processed: int
    events_matched: int
    missing_events: int


@dataclass(frozen=True)
class IntradayChartsResult:
    output_dir: Path
    chart_paths: tuple[Path, ...]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _parse_timestamp_utc(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_date(value: object) -> date | None:
    timestamp = _parse_timestamp_utc(value)
    return timestamp.date() if timestamp is not None else None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _format_float(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def _format_int(value: int | None) -> str:
    return "" if value is None else str(value)


def _float_or_none(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _intraday_eligibility_reason(event_timestamp: datetime | None, now_utc: datetime) -> tuple[bool, str, str]:
    if event_timestamp is None:
        return False, "malformed published_at timestamp", ""
    days = (now_utc.date() - event_timestamp.date()).days
    if days < 0:
        return False, "future event timestamp", str(days)
    if days > 60:
        return False, "outside yfinance intraday lookback window (>60 days)", str(days)
    return True, "eligible recent event", str(days)


def scan_intraday_event_feasibility(
    *,
    input_path: Path = DEFAULT_CLEAN_EVENTS_PATH,
    ticker_aliases_path: Path = DEFAULT_TICKER_ALIASES_PATH,
    output_path: Path = DEFAULT_INTRADAY_FEASIBILITY_PATH,
    summary_md_path: Path = DEFAULT_INTRADAY_FEASIBILITY_SUMMARY_PATH,
    now_utc: datetime | None = None,
) -> IntradayFeasibilityResult:
    ensure_data_dirs()
    rows = _read_csv(input_path)
    aliases = load_ticker_aliases(ticker_aliases_path)
    reference_now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    output_rows: list[dict[str, Any]] = []
    eligible = 0
    reason_counts: Counter[str] = Counter()
    for row in rows:
        event_timestamp = _parse_timestamp_utc(row.get("published_at"))
        event_date = event_timestamp.date().isoformat() if event_timestamp is not None else ""
        event_ticker = _clean(row.get("ticker")).upper()
        data_ticker, _ = resolve_data_ticker(event_ticker, aliases=aliases, event_date=event_date)
        is_eligible, reason, days_from_now = _intraday_eligibility_reason(event_timestamp, reference_now)
        eligible += int(is_eligible)
        reason_counts[reason] += 1
        output_rows.append(
            {
                "event_id": _clean(row.get("event_id")),
                "ticker": event_ticker,
                "data_ticker": data_ticker,
                "creator": _clean(row.get("creator")),
                "title": _clean(row.get("title")),
                "published_at": _clean(row.get("published_at")),
                "event_timestamp_utc": (
                    event_timestamp.isoformat().replace("+00:00", "Z") if event_timestamp else ""
                ),
                "event_date": event_date,
                "days_from_now": days_from_now,
                "yfinance_intraday_eligible": bool(is_eligible),
                "reason": reason,
            }
        )
    _write_csv(output_path, output_rows, INTRADAY_FEASIBILITY_COLUMNS)
    lines = [
        "# Intraday Event Feasibility Summary",
        "",
        f"- Input clean events: `{input_path}`",
        f"- Total clean events: {len(rows)}",
        f"- Intraday-eligible events (<=60 days): {eligible}",
        "",
        "## Eligibility Reasons",
        "",
    ]
    for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {reason}: {count}")
    summary_md_path.parent.mkdir(parents=True, exist_ok=True)
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return IntradayFeasibilityResult(
        output_path=output_path,
        summary_md_path=summary_md_path,
        total_events=len(rows),
        eligible_events=eligible,
    )


def _default_downloader(symbol: str, start_utc: datetime, end_utc: datetime, interval: str) -> pd.DataFrame:
    import yfinance as yf

    # yfinance accepts YYYY-MM-DD strings more reliably than ISO timestamps with time zones.
    # Add one day to end so the range is inclusive.
    start_str = start_utc.strftime("%Y-%m-%d")
    end_str = (end_utc + timedelta(days=1)).strftime("%Y-%m-%d")
    return yf.download(
        symbol,
        start=start_str,
        end=end_str,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
        prepost=True,
    )


def _event_window_valid_for_1m(
    start_utc: datetime, end_utc: datetime, now_utc: datetime
) -> tuple[bool, str]:
    """Validate that an event window is within yfinance 1m limits. No shifting allowed."""
    max_span = timedelta(days=8)
    max_lookback = timedelta(days=30)
    if end_utc - start_utc > max_span:
        return False, f"window span {(end_utc - start_utc).days}d exceeds yfinance 1m max 8 days"
    if end_utc < now_utc - max_lookback:
        return False, "event window outside yfinance 1m 30-day lookback"
    if start_utc < now_utc - max_lookback:
        return False, "event window start outside yfinance 1m 30-day lookback"
    return True, ""


def _normalize_intraday_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = [column[0] if isinstance(column, tuple) else column for column in normalized.columns]
    if normalized.index.tz is None:
        normalized.index = normalized.index.tz_localize(UTC)
    else:
        normalized.index = normalized.index.tz_convert(UTC)
    return normalized


def _benchmark_map(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {}
    normalized = _normalize_intraday_frame(frame)
    close_col = "Adj Close" if "Adj Close" in normalized.columns else "Close"
    if close_col not in normalized.columns:
        return {}
    mapping: dict[str, float] = {}
    for index, row in normalized.iterrows():
        value = _float_or_none(row.get(close_col))
        if value is None:
            continue
        key = pd.Timestamp(index).tz_convert(UTC).isoformat().replace("+00:00", "Z")
        mapping[key] = value
    return mapping


def fetch_yfinance_intraday_market_data(
    *,
    feasibility_input_path: Path = DEFAULT_INTRADAY_FEASIBILITY_PATH,
    output_path: Path = DEFAULT_INTRADAY_MARKET_DATA_PATH,
    summary_md_path: Path = DEFAULT_INTRADAY_FETCH_SUMMARY_MD_PATH,
    summary_csv_path: Path = DEFAULT_INTRADAY_FETCH_SUMMARY_CSV_PATH,
    interval: str = "1m",
    lookback_minutes: int = 120,
    forward_minutes: int = 390,
    confirm_yfinance_run: bool = False,
    dry_run: bool = False,
    downloader: Downloader | None = None,
) -> IntradayFetchResult:
    if lookback_minutes < 0 or forward_minutes < 0:
        raise ValueError("lookback_minutes and forward_minutes must be non-negative")
    ensure_data_dirs()
    rows = _read_csv(feasibility_input_path)
    eligible_rows = [row for row in rows if _clean(row.get("yfinance_intraday_eligible")).lower() == "true"]

    now_utc = datetime.now(UTC)
    planned_windows = 0
    max_window_days = 0.0
    excluded_count = 0
    shifted_windows = 0

    for row in eligible_rows:
        event_timestamp = _parse_timestamp_utc(row.get("event_timestamp_utc"))
        if event_timestamp is None:
            continue
        start = event_timestamp - timedelta(minutes=lookback_minutes)
        end = event_timestamp + timedelta(minutes=forward_minutes)
        window_days = (end - start).total_seconds() / 86400
        max_window_days = max(max_window_days, window_days)
        if interval == "1m":
            valid, reason = _event_window_valid_for_1m(start, end, now_utc)
            if not valid:
                excluded_count += 1
                continue
        planned_windows += 1

    if dry_run:
        return IntradayFetchResult(
            output_path=output_path,
            summary_md_path=summary_md_path,
            summary_csv_path=summary_csv_path,
            eligible_events=len(eligible_rows),
            tickers_downloaded=0,
            rows_written=0,
            failed_tickers=(),
            dry_run=True,
            planned_event_windows=planned_windows,
            max_window_days=max_window_days,
            events_excluded_outside_1m_limit=excluded_count,
            shifted_windows=shifted_windows,
        )
    if not confirm_yfinance_run:
        raise PermissionError(
            "Refusing yfinance intraday download. Re-run with --confirm-yfinance-run to fetch interim intraday data."
        )
    if not eligible_rows:
        lines = [
            "# yfinance Intraday Fetch Summary",
            "",
            "- No eligible events found in feasibility scan.",
            "- No yfinance download calls were made.",
        ]
        summary_md_path.parent.mkdir(parents=True, exist_ok=True)
        summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _write_csv(summary_csv_path, [], INTRADAY_FETCH_SUMMARY_COLUMNS)
        _write_csv(output_path, [], INTRADAY_MARKET_DATA_COLUMNS)
        return IntradayFetchResult(
            output_path=output_path,
            summary_md_path=summary_md_path,
            summary_csv_path=summary_csv_path,
            eligible_events=0,
            tickers_downloaded=0,
            rows_written=0,
            failed_tickers=(),
            dry_run=False,
        )

    active_downloader = downloader or _default_downloader
    downloaded_at_utc = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    summary_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    failed_tickers: list[str] = []
    fetched_event_ids: set[str] = set()

    for row in eligible_rows:
        event_id = _clean(row.get("event_id"))
        data_ticker = _clean(row.get("data_ticker")).upper()
        original_ticker = _clean(row.get("ticker")).upper()
        event_timestamp = _parse_timestamp_utc(row.get("event_timestamp_utc"))
        if not data_ticker or event_timestamp is None:
            excluded_count += 1
            continue
        start = event_timestamp - timedelta(minutes=lookback_minutes)
        end = event_timestamp + timedelta(minutes=forward_minutes)
        if interval == "1m":
            valid, reason = _event_window_valid_for_1m(start, end, now_utc)
            if not valid:
                summary_rows.append(
                    {
                        "event_id": event_id,
                        "original_ticker": original_ticker,
                        "data_ticker": data_ticker,
                        "status": "excluded",
                        "row_count": 0,
                        "window_start_utc": start.isoformat().replace("+00:00", "Z"),
                        "window_end_utc": end.isoformat().replace("+00:00", "Z"),
                        "error": reason,
                    }
                )
                continue

        try:
            frame = active_downloader(data_ticker, start, end, interval)
            spy_frame = active_downloader("SPY", start, end, interval)
            normalized = _normalize_intraday_frame(frame)
            spy_normalized = _normalize_intraday_frame(spy_frame)
            benchmark_close_by_dt = _benchmark_map(spy_normalized)
            if normalized.empty:
                failed_tickers.append(original_ticker)
                summary_rows.append(
                    {
                        "event_id": event_id,
                        "original_ticker": original_ticker,
                        "data_ticker": data_ticker,
                        "status": "failed",
                        "row_count": 0,
                        "window_start_utc": start.isoformat().replace("+00:00", "Z"),
                        "window_end_utc": end.isoformat().replace("+00:00", "Z"),
                        "error": "empty intraday response",
                    }
                )
                continue
            close_col = "Adj Close" if "Adj Close" in normalized.columns else "Close"
            for index, record in normalized.iterrows():
                dt_utc = pd.Timestamp(index).tz_convert(UTC).isoformat().replace("+00:00", "Z")
                close = _float_or_none(record.get("Close"))
                adjusted = _float_or_none(record.get(close_col))
                benchmark_close = benchmark_close_by_dt.get(dt_utc)
                output_rows.append(
                    {
                        "event_id": event_id,
                        "original_ticker": original_ticker,
                        "data_ticker": data_ticker,
                        "datetime_utc": dt_utc,
                        "open": _format_float(_float_or_none(record.get("Open"))),
                        "high": _format_float(_float_or_none(record.get("High"))),
                        "low": _format_float(_float_or_none(record.get("Low"))),
                        "close": _format_float(close),
                        "adjusted_close": _format_float(adjusted if adjusted is not None else close),
                        "volume": _format_int(int(_float_or_none(record.get("Volume")) or 0)),
                        "benchmark_ticker": "SPY",
                        "benchmark_close": _format_float(benchmark_close),
                        "interval": interval,
                        "data_source": "yfinance_yahoo_intraday_prototype",
                        "downloaded_at_utc": downloaded_at_utc,
                    }
                )
            summary_rows.append(
                {
                    "event_id": event_id,
                    "original_ticker": original_ticker,
                    "data_ticker": data_ticker,
                    "status": "downloaded",
                    "row_count": len(normalized),
                    "window_start_utc": start.isoformat().replace("+00:00", "Z"),
                    "window_end_utc": end.isoformat().replace("+00:00", "Z"),
                    "error": "",
                }
            )
            fetched_event_ids.add(event_id)
        except Exception as exc:
            failed_tickers.append(original_ticker)
            summary_rows.append(
                {
                    "event_id": event_id,
                    "original_ticker": original_ticker,
                    "data_ticker": data_ticker,
                    "status": "failed",
                    "row_count": 0,
                    "window_start_utc": start.isoformat().replace("+00:00", "Z"),
                    "window_end_utc": end.isoformat().replace("+00:00", "Z"),
                    "error": str(exc),
                }
            )

    output_rows.sort(key=lambda row: (_clean(row.get("event_id")), _clean(row.get("datetime_utc"))))
    _write_csv(output_path, output_rows, INTRADAY_MARKET_DATA_COLUMNS)
    _write_csv(summary_csv_path, summary_rows, INTRADAY_FETCH_SUMMARY_COLUMNS)
    unique_failed = sorted(set(failed_tickers))
    lines = [
        "# yfinance Intraday Fetch Summary",
        "",
        f"- Feasibility input: `{feasibility_input_path}`",
        f"- Eligible events: {len(eligible_rows)}",
        f"- Planned event windows: {planned_windows}",
        f"- Events excluded outside 1m limit: {excluded_count}",
        f"- Shifted windows: {shifted_windows}",
        f"- Event windows downloaded: {len(fetched_event_ids)}",
        f"- Event windows failed: {len(unique_failed)}",
        f"- Rows written: {len(output_rows)}",
        f"- Interval: {interval}",
        f"- Lookback minutes: {lookback_minutes}",
        f"- Forward minutes: {forward_minutes}",
        "",
        "Prototype warning: yfinance intraday data is interim and should be replaced with licensed data for final inference.",
    ]
    if unique_failed:
        lines.extend(["", "## Failed Tickers", ""])
        lines.extend([f"- {ticker}" for ticker in unique_failed])
    summary_md_path.parent.mkdir(parents=True, exist_ok=True)
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return IntradayFetchResult(
        output_path=output_path,
        summary_md_path=summary_md_path,
        summary_csv_path=summary_csv_path,
        eligible_events=len(eligible_rows),
        tickers_downloaded=len(fetched_event_ids),
        rows_written=len(output_rows),
        failed_tickers=tuple(unique_failed),
        dry_run=False,
        planned_event_windows=planned_windows,
        max_window_days=max_window_days,
        events_excluded_outside_1m_limit=excluded_count,
        shifted_windows=shifted_windows,
    )


def _next_weekday_open(dt_et: datetime) -> datetime:
    candidate = dt_et
    while candidate.weekday() >= 5:
        candidate = (candidate + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
    return candidate


def _align_event_timestamp(
    event_utc: datetime,
    ticker_index_utc: pd.DatetimeIndex,
    *,
    allow_premarket: bool = True,
) -> tuple[datetime | None, str]:
    if ticker_index_utc.empty:
        return None, "no intraday ticker data"
    event_et = event_utc.astimezone(NY_TZ)
    open_et = event_et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_et = event_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if event_et.weekday() >= 5:
        target_et = _next_weekday_open((event_et + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0))
    elif event_et < open_et:
        if allow_premarket:
            target_et = event_et
        else:
            target_et = open_et
    elif event_et > close_et:
        target_et = _next_weekday_open((event_et + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0))
    else:
        target_et = event_et
    target_utc = target_et.astimezone(UTC)
    position = ticker_index_utc.searchsorted(pd.Timestamp(target_utc), side="left")
    if position >= len(ticker_index_utc):
        return None, "no available minute after aligned timestamp"
    aligned = ticker_index_utc[position].to_pydatetime().astimezone(UTC)
    return aligned, ""


def _return_for_minutes(
    frame: pd.DataFrame,
    aligned_ts: pd.Timestamp,
    minutes: int,
    *,
    column: str,
) -> float | None:
    end_target = aligned_ts + pd.Timedelta(minutes=minutes)
    position = frame.index.searchsorted(end_target, side="left")
    start_pos = frame.index.get_loc(aligned_ts)
    if isinstance(start_pos, slice):
        start_pos = start_pos.start
    if position >= len(frame.index):
        return None
    start_value = _float_or_none(frame.iloc[int(start_pos)][column])
    end_value = _float_or_none(frame.iloc[int(position)][column])
    if start_value in (None, 0) or end_value is None:
        return None
    return (end_value / start_value) - 1.0


def _return_to_close(frame: pd.DataFrame, aligned_ts: pd.Timestamp, *, column: str) -> float | None:
    aligned_et = aligned_ts.tz_convert(NY_TZ)
    day_start = aligned_et.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = aligned_et.replace(hour=23, minute=59, second=59, microsecond=999999)
    same_day = frame[(frame.index.tz_convert(NY_TZ) >= day_start) & (frame.index.tz_convert(NY_TZ) <= day_end)]
    if same_day.empty:
        return None
    regular = same_day[same_day.index.tz_convert(NY_TZ).time <= time(16, 0)]
    close_slice = regular if not regular.empty else same_day
    start_value = _float_or_none(frame.loc[aligned_ts, column])
    end_value = _float_or_none(close_slice.iloc[-1][column])
    if start_value in (None, 0) or end_value is None:
        return None
    return (end_value / start_value) - 1.0


def _pre_event_return_60m(frame: pd.DataFrame, aligned_ts: pd.Timestamp, *, column: str) -> float | None:
    target = aligned_ts - pd.Timedelta(minutes=60)
    position = frame.index.searchsorted(target, side="left")
    if position >= len(frame.index):
        return None
    start_ts = frame.index[position]
    if start_ts >= aligned_ts:
        return None
    start_value = _float_or_none(frame.loc[start_ts, column])
    end_value = _float_or_none(frame.loc[aligned_ts, column])
    if start_value in (None, 0) or end_value is None:
        return None
    return (end_value / start_value) - 1.0


def _volume_change(frame: pd.DataFrame, aligned_ts: pd.Timestamp, minutes: int) -> float | None:
    end_target = aligned_ts + pd.Timedelta(minutes=minutes)
    position = frame.index.searchsorted(end_target, side="left")
    if position >= len(frame.index):
        return None
    start_volume = _float_or_none(frame.loc[aligned_ts, "volume"])
    end_volume = _float_or_none(frame.iloc[position]["volume"])
    if start_volume in (None, 0) or end_volume is None:
        return None
    return (end_volume / start_volume) - 1.0


def _group_rows(rows: list[dict[str, Any]], *, key_name: str, value_name: str = "group") -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _clean(row.get(key_name)) or "unknown"
        grouped.setdefault(key, []).append(row)
    output: list[dict[str, Any]] = []
    for key in sorted(grouped):
        subset = grouped[key]
        abnormal_5m = [_float_or_none(item.get("abnormal_return_5m")) for item in subset]
        abnormal_15m = [_float_or_none(item.get("abnormal_return_15m")) for item in subset]
        abnormal_30m = [_float_or_none(item.get("abnormal_return_30m")) for item in subset]
        abnormal_60m = [_float_or_none(item.get("abnormal_return_60m")) for item in subset]
        abnormal_close = [_float_or_none(item.get("abnormal_return_to_close")) for item in subset]

        def _mean(values: list[float | None]) -> str:
            present = [value for value in values if value is not None]
            if not present:
                return ""
            return f"{(sum(present) / len(present)):.6f}"

        output.append(
            {
                value_name: key,
                "event_count": len(subset),
                "matched_count": sum(
                    1
                    for item in subset
                    if _clean(item.get("missing_intraday_data_flag")).lower() in {"false", ""}
                ),
                "mean_abnormal_return_5m": _mean(abnormal_5m),
                "mean_abnormal_return_15m": _mean(abnormal_15m),
                "mean_abnormal_return_30m": _mean(abnormal_30m),
                "mean_abnormal_return_60m": _mean(abnormal_60m),
                "mean_abnormal_return_to_close": _mean(abnormal_close),
            }
        )
    return output


def _write_intraday_methodology_note(path: Path) -> Path:
    lines = [
        "# Intraday Event-Study Methodology Note",
        "",
        "- yfinance intraday minute data is limited to recent periods and does not cover the full 2020-2026 sample.",
        "- This intraday extension is therefore feasibility-oriented and applies only to recently eligible events.",
        "- YouTube `published_at` is an imperfect proxy for when investors process recommendation content.",
        "- X post timestamps would be cleaner for intraday timing tests because they are more immediate and text-native.",
        "- Intraday results are an extension and should not replace the primary daily event-study evidence.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_intraday_event_study(
    *,
    input_events_path: Path = DEFAULT_CLEAN_EVENTS_PATH,
    input_intraday_market_data_path: Path = DEFAULT_INTRADAY_MARKET_DATA_PATH,
    ticker_aliases_path: Path = DEFAULT_TICKER_ALIASES_PATH,
    output_path: Path = DEFAULT_INTRADAY_RESULTS_PATH,
    summary_md_path: Path = DEFAULT_INTRADAY_SUMMARY_MD_PATH,
    by_creator_path: Path = DEFAULT_INTRADAY_BY_CREATOR_PATH,
    by_ticker_path: Path = DEFAULT_INTRADAY_BY_TICKER_PATH,
    methodology_note_path: Path = DEFAULT_INTRADAY_METHOD_NOTE_PATH,
) -> IntradayEventStudyResult:
    ensure_data_dirs()
    events = _read_csv(input_events_path)
    market_rows = _read_csv(input_intraday_market_data_path)
    aliases = load_ticker_aliases(ticker_aliases_path)
    market_df = pd.DataFrame(market_rows)
    if market_df.empty:
        raise ValueError("Intraday market-data input has no rows.")
    required_columns = {
        "event_id",
        "data_ticker",
        "datetime_utc",
        "adjusted_close",
        "close",
        "volume",
        "benchmark_close",
        "data_source",
    }
    missing = [column for column in required_columns if column not in market_df.columns]
    if missing:
        raise ValueError("Intraday market-data input is missing columns: " + ", ".join(sorted(missing)))
    market_df["datetime_utc"] = pd.to_datetime(market_df["datetime_utc"], utc=True, errors="coerce")
    market_df = market_df.dropna(subset=["datetime_utc"])
    market_df["event_id"] = market_df["event_id"].astype(str)
    market_df["data_ticker"] = market_df["data_ticker"].astype(str).str.upper()
    market_df["adjusted_close"] = pd.to_numeric(market_df["adjusted_close"], errors="coerce")
    market_df["close"] = pd.to_numeric(market_df["close"], errors="coerce")
    market_df["volume"] = pd.to_numeric(market_df["volume"], errors="coerce")
    market_df["benchmark_close"] = pd.to_numeric(market_df["benchmark_close"], errors="coerce")
    market_df["price_for_returns"] = market_df["adjusted_close"].fillna(market_df["close"])

    rows_by_event_id: dict[str, pd.DataFrame] = {}
    for eid, subset in market_df.groupby("event_id"):
        sorted_subset = subset.sort_values("datetime_utc").copy()
        sorted_subset = sorted_subset.set_index("datetime_utc")
        rows_by_event_id[str(eid)] = sorted_subset

    output_rows: list[dict[str, Any]] = []
    missing_count = 0
    for event in events:
        event_id = _clean(event.get("event_id"))
        ticker = _clean(event.get("ticker")).upper()
        published_at = _clean(event.get("published_at"))
        event_timestamp = _parse_timestamp_utc(published_at)
        if event_timestamp is None:
            missing_count += 1
            output_rows.append(
                {
                    "event_id": event_id,
                    "ticker": ticker,
                    "data_ticker": ticker,
                    "creator": _clean(event.get("creator")),
                    "title": _clean(event.get("title")),
                    "published_at": published_at,
                    "event_timestamp_utc": "",
                    "event_timestamp_aligned_utc": "",
                    "event_timestamp_aligned_et": "",
                    "recommendation_type": _clean(event.get("recommendation_type")),
                    "direction": _clean(event.get("direction")),
                    "missing_intraday_data_flag": True,
                    "missing_intraday_data_reason": "malformed published_at timestamp",
                    "data_source": "",
                }
            )
            continue
        event_date = event_timestamp.date().isoformat()
        data_ticker, _ = resolve_data_ticker(ticker, aliases=aliases, event_date=event_date)
        event_df = rows_by_event_id.get(event_id)
        if event_df is None or event_df.empty:
            missing_count += 1
            output_rows.append(
                {
                    "event_id": event_id,
                    "ticker": ticker,
                    "data_ticker": data_ticker,
                    "creator": _clean(event.get("creator")),
                    "title": _clean(event.get("title")),
                    "published_at": published_at,
                    "event_timestamp_utc": event_timestamp.isoformat().replace("+00:00", "Z"),
                    "event_timestamp_aligned_utc": "",
                    "event_timestamp_aligned_et": "",
                    "recommendation_type": _clean(event.get("recommendation_type")),
                    "direction": _clean(event.get("direction")),
                    "missing_intraday_data_flag": True,
                    "missing_intraday_data_reason": "no intraday data for this event_id",
                    "data_source": "",
                }
            )
            continue

        aligned_utc, alignment_reason = _align_event_timestamp(event_timestamp, event_df.index)
        if aligned_utc is None:
            missing_count += 1
            output_rows.append(
                {
                    "event_id": event_id,
                    "ticker": ticker,
                    "data_ticker": data_ticker,
                    "creator": _clean(event.get("creator")),
                    "title": _clean(event.get("title")),
                    "published_at": published_at,
                    "event_timestamp_utc": event_timestamp.isoformat().replace("+00:00", "Z"),
                    "event_timestamp_aligned_utc": "",
                    "event_timestamp_aligned_et": "",
                    "recommendation_type": _clean(event.get("recommendation_type")),
                    "direction": _clean(event.get("direction")),
                    "missing_intraday_data_flag": True,
                    "missing_intraday_data_reason": alignment_reason or "no aligned intraday minute",
                    "data_source": "",
                }
            )
            continue

        aligned_ts = pd.Timestamp(aligned_utc).tz_convert(UTC)
        if aligned_ts not in event_df.index:
            pos = event_df.index.searchsorted(aligned_ts, side="left")
            if pos >= len(event_df.index):
                missing_count += 1
                output_rows.append(
                    {
                        "event_id": event_id,
                        "ticker": ticker,
                        "data_ticker": data_ticker,
                        "creator": _clean(event.get("creator")),
                        "title": _clean(event.get("title")),
                        "published_at": published_at,
                        "event_timestamp_utc": event_timestamp.isoformat().replace("+00:00", "Z"),
                        "event_timestamp_aligned_utc": "",
                        "event_timestamp_aligned_et": "",
                        "recommendation_type": _clean(event.get("recommendation_type")),
                        "direction": _clean(event.get("direction")),
                        "missing_intraday_data_flag": True,
                        "missing_intraday_data_reason": "no aligned intraday minute",
                        "data_source": "",
                    }
                )
                continue
            aligned_ts = event_df.index[pos]

        return_5m = _return_for_minutes(event_df, aligned_ts, 5, column="price_for_returns")
        return_15m = _return_for_minutes(event_df, aligned_ts, 15, column="price_for_returns")
        return_30m = _return_for_minutes(event_df, aligned_ts, 30, column="price_for_returns")
        return_60m = _return_for_minutes(event_df, aligned_ts, 60, column="price_for_returns")
        return_to_close = _return_to_close(event_df, aligned_ts, column="price_for_returns")

        benchmark_return_5m = _return_for_minutes(event_df, aligned_ts, 5, column="benchmark_close")
        benchmark_return_15m = _return_for_minutes(event_df, aligned_ts, 15, column="benchmark_close")
        benchmark_return_30m = _return_for_minutes(event_df, aligned_ts, 30, column="benchmark_close")
        benchmark_return_60m = _return_for_minutes(event_df, aligned_ts, 60, column="benchmark_close")
        benchmark_return_to_close = _return_to_close(event_df, aligned_ts, column="benchmark_close")

        def _abnormal(stock: float | None, benchmark: float | None) -> float | None:
            if stock is None or benchmark is None:
                return None
            return stock - benchmark

        abnormal_5m = _abnormal(return_5m, benchmark_return_5m)
        abnormal_15m = _abnormal(return_15m, benchmark_return_15m)
        abnormal_30m = _abnormal(return_30m, benchmark_return_30m)
        abnormal_60m = _abnormal(return_60m, benchmark_return_60m)
        abnormal_to_close = _abnormal(return_to_close, benchmark_return_to_close)

        pre_event_return_60m = _pre_event_return_60m(event_df, aligned_ts, column="price_for_returns")
        volume_change_30m = _volume_change(event_df, aligned_ts, 30)
        volume_change_60m = _volume_change(event_df, aligned_ts, 60)

        missing_intraday_data_flag = all(
            value is None for value in [abnormal_5m, abnormal_15m, abnormal_30m, abnormal_60m, abnormal_to_close]
        )
        missing_intraday_data_reason = (
            "insufficient forward intraday window" if missing_intraday_data_flag else ""
        )
        if missing_intraday_data_flag:
            missing_count += 1

        output_rows.append(
            {
                "event_id": event_id,
                "ticker": ticker,
                "data_ticker": data_ticker,
                "creator": _clean(event.get("creator")),
                "title": _clean(event.get("title")),
                "published_at": published_at,
                "event_timestamp_utc": event_timestamp.isoformat().replace("+00:00", "Z"),
                "event_timestamp_aligned_utc": aligned_ts.isoformat().replace("+00:00", "Z"),
                "event_timestamp_aligned_et": aligned_ts.tz_convert(NY_TZ).isoformat(),
                "recommendation_type": _clean(event.get("recommendation_type")),
                "direction": _clean(event.get("direction")),
                "return_5m": _format_float(return_5m),
                "return_15m": _format_float(return_15m),
                "return_30m": _format_float(return_30m),
                "return_60m": _format_float(return_60m),
                "return_to_close": _format_float(return_to_close),
                "benchmark_return_5m": _format_float(benchmark_return_5m),
                "benchmark_return_15m": _format_float(benchmark_return_15m),
                "benchmark_return_30m": _format_float(benchmark_return_30m),
                "benchmark_return_60m": _format_float(benchmark_return_60m),
                "benchmark_return_to_close": _format_float(benchmark_return_to_close),
                "abnormal_return_5m": _format_float(abnormal_5m),
                "abnormal_return_15m": _format_float(abnormal_15m),
                "abnormal_return_30m": _format_float(abnormal_30m),
                "abnormal_return_60m": _format_float(abnormal_60m),
                "abnormal_return_to_close": _format_float(abnormal_to_close),
                "pre_event_return_60m": _format_float(pre_event_return_60m),
                "volume_change_30m": _format_float(volume_change_30m),
                "volume_change_60m": _format_float(volume_change_60m),
                "missing_intraday_data_flag": bool(missing_intraday_data_flag),
                "missing_intraday_data_reason": missing_intraday_data_reason,
                "data_source": _clean(event_df.iloc[0].get("data_source")),
            }
        )

    _write_csv(output_path, output_rows, INTRADAY_RESULT_COLUMNS)
    by_creator_rows = _group_rows(output_rows, key_name="creator")
    by_ticker_rows = _group_rows(output_rows, key_name="ticker")
    _write_csv(by_creator_path, by_creator_rows, INTRADAY_GROUP_COLUMNS)
    _write_csv(by_ticker_path, by_ticker_rows, INTRADAY_GROUP_COLUMNS)
    methodology_path = _write_intraday_methodology_note(methodology_note_path)

    matched = len(output_rows) - missing_count
    lines = [
        "# Intraday Event Study Summary",
        "",
        f"- Events input: `{input_events_path}`",
        f"- Intraday market-data input: `{input_intraday_market_data_path}`",
        f"- Events processed: {len(events)}",
        f"- Events matched with intraday windows: {matched}",
        f"- Events missing intraday data: {missing_count}",
        f"- Results CSV: `{output_path}`",
        f"- By creator CSV: `{by_creator_path}`",
        f"- By ticker CSV: `{by_ticker_path}`",
        f"- Methodology note: `{methodology_path}`",
        "",
        "Intraday extension warning: this uses recent yfinance minute data and is not a replacement for the main daily study.",
    ]
    summary_md_path.parent.mkdir(parents=True, exist_ok=True)
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return IntradayEventStudyResult(
        output_path=output_path,
        summary_md_path=summary_md_path,
        by_creator_path=by_creator_path,
        by_ticker_path=by_ticker_path,
        methodology_note_path=methodology_path,
        events_processed=len(events),
        events_matched=matched,
        missing_events=missing_count,
    )


def build_intraday_event_study_charts(
    *,
    input_results_path: Path = DEFAULT_INTRADAY_RESULTS_PATH,
    output_dir: Path = INTRADAY_CHARTS_DIR,
) -> IntradayChartsResult:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError("matplotlib is required to generate intraday charts.") from exc

    rows = _read_csv(input_results_path)
    if not rows:
        raise ValueError("Intraday event-study results are empty.")
    frame = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)

    def _numeric_series(column: str) -> pd.Series:
        return pd.to_numeric(frame[column], errors="coerce").dropna()

    chart_paths: list[Path] = []

    def _hist(column: str, filename: str, title: str) -> None:
        values = _numeric_series(column)
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(values, bins=25)
        ax.set_title(title)
        ax.set_xlabel(column)
        ax.set_ylabel("count")
        fig.tight_layout()
        path = output_dir / filename
        fig.savefig(path, format="png")
        plt.close(fig)
        chart_paths.append(path)

    _hist("abnormal_return_5m", "abnormal_return_5m_distribution.png", "Abnormal Return 5m")
    _hist("abnormal_return_15m", "abnormal_return_15m_distribution.png", "Abnormal Return 15m")
    _hist("abnormal_return_60m", "abnormal_return_60m_distribution.png", "Abnormal Return 60m")

    mean_by_window = {
        "5m": _numeric_series("abnormal_return_5m").mean(),
        "15m": _numeric_series("abnormal_return_15m").mean(),
        "30m": _numeric_series("abnormal_return_30m").mean(),
        "60m": _numeric_series("abnormal_return_60m").mean(),
        "to_close": _numeric_series("abnormal_return_to_close").mean(),
    }
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(list(mean_by_window.keys()), list(mean_by_window.values()))
    ax.set_title("Mean Intraday Abnormal Return by Window")
    ax.set_xlabel("window")
    ax.set_ylabel("mean abnormal return")
    fig.tight_layout()
    path = output_dir / "mean_intraday_abnormal_return_by_window.png"
    fig.savefig(path, format="png")
    plt.close(fig)
    chart_paths.append(path)

    by_ticker = frame["ticker"].fillna("").replace("", "unknown").str.upper().value_counts()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(by_ticker.index.tolist(), by_ticker.values.tolist())
    ax.set_title("Intraday Events by Ticker")
    ax.set_xlabel("ticker")
    ax.set_ylabel("events")
    fig.tight_layout()
    path = output_dir / "intraday_events_by_ticker.png"
    fig.savefig(path, format="png")
    plt.close(fig)
    chart_paths.append(path)

    return IntradayChartsResult(output_dir=output_dir, chart_paths=tuple(chart_paths))
