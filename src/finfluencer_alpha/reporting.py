from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from .config import EXPORTS_DIR, IMPORTS_DIR, ensure_data_dirs
from .ticker_aliases import DEFAULT_TICKER_ALIASES_PATH, load_ticker_aliases, resolve_data_ticker
from .utils import configure_csv_field_size_limit

EVENT_STUDY_DIR = EXPORTS_DIR / "event_study"
VALIDATION_DIR = EXPORTS_DIR / "validation"
REPORTING_DIR = EXPORTS_DIR / "reporting"
REPORTING_CHARTS_DIR = REPORTING_DIR / "charts"
MARKET_DATA_DIR = IMPORTS_DIR / "market_data"
MARKET_DATA_EXPORT_DIR = EXPORTS_DIR / "market_data"

DEFAULT_EVENT_STUDY_RESULTS_PATH = EVENT_STUDY_DIR / "event_study_results.csv"
DEFAULT_CLEAN_EVENTS_PATH = VALIDATION_DIR / "clean_auto_labeled_events.csv"
DEFAULT_MARKET_DATA_PATH = MARKET_DATA_DIR / "yfinance_market_data.csv"
DEFAULT_THRESHOLD_SENSITIVITY_PATH = VALIDATION_DIR / "clean_event_threshold_sensitivity.csv"
DEFAULT_YFINANCE_FETCH_SUMMARY_PATH = MARKET_DATA_EXPORT_DIR / "yfinance_fetch_summary.csv"

DEFAULT_MATCH_DIAGNOSTICS_CSV_PATH = EVENT_STUDY_DIR / "event_study_match_diagnostics.csv"
DEFAULT_MATCH_DIAGNOSTICS_MD_PATH = EVENT_STUDY_DIR / "event_study_match_diagnostics.md"

DEFAULT_MAIN_TABLE_CSV_PATH = REPORTING_DIR / "event_study_main_table.csv"
DEFAULT_MAIN_TABLE_MD_PATH = REPORTING_DIR / "event_study_main_table.md"
DEFAULT_BY_CREATOR_CSV_PATH = REPORTING_DIR / "event_study_by_creator.csv"
DEFAULT_BY_TICKER_CSV_PATH = REPORTING_DIR / "event_study_by_ticker.csv"
DEFAULT_BY_YEAR_CSV_PATH = REPORTING_DIR / "event_study_by_year.csv"
DEFAULT_BY_RECOMMENDATION_TYPE_CSV_PATH = REPORTING_DIR / "event_study_by_recommendation_type.csv"
DEFAULT_BY_DIRECTION_CSV_PATH = REPORTING_DIR / "event_study_by_direction.csv"
DEFAULT_ROBUSTNESS_CSV_PATH = REPORTING_DIR / "event_study_robustness_thresholds.csv"
DEFAULT_REPORT_SUMMARY_MD_PATH = REPORTING_DIR / "event_study_report_summary.md"
DEFAULT_METHODOLOGY_NOTE_PATH = REPORTING_DIR / "methodology_note_yfinance_prototype.md"

CHART_FILENAMES = (
    "abnormal_return_1d_distribution.png",
    "abnormal_return_5d_distribution.png",
    "abnormal_return_20d_distribution.png",
    "car_5d_distribution.png",
    "car_20d_distribution.png",
    "mean_abnormal_return_by_window.png",
    "events_by_year.png",
    "events_by_creator_top10.png",
    "events_by_ticker_top10.png",
    "mean_car_20d_by_creator_top10.png",
)

GROUP_SUMMARY_COLUMNS = [
    "group",
    "event_count",
    "matched_count",
    "mean_abnormal_return_1d",
    "mean_abnormal_return_5d",
    "mean_abnormal_return_20d",
    "mean_car_5d",
    "mean_car_20d",
    "positive_abnormal_return_5d_share",
    "mean_volume_change_5d",
]


@dataclass(frozen=True)
class MatchDiagnosticsResult:
    csv_path: Path
    markdown_path: Path
    total_clean_events: int
    matched_events: int
    unmatched_events: int
    unmatched_reason_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class EventStudyReportingResult:
    main_table_csv_path: Path
    main_table_md_path: Path
    by_creator_csv_path: Path
    by_ticker_csv_path: Path
    by_year_csv_path: Path
    by_recommendation_type_csv_path: Path
    by_direction_csv_path: Path
    robustness_csv_path: Path
    report_summary_md_path: Path
    methodology_note_path: Path
    event_count: int
    matched_count: int


@dataclass(frozen=True)
class EventStudyChartsResult:
    output_dir: Path
    chart_paths: tuple[Path, ...]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _parse_date(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def _event_date(row: dict[str, str]) -> str:
    adjusted = _parse_date(row.get("event_date_weekday_adjusted"))
    if adjusted:
        return adjusted
    event_utc = _parse_date(row.get("event_date_utc"))
    if event_utc:
        return event_utc
    published = _clean(row.get("published_at"))
    if not published:
        return ""
    try:
        return datetime.fromisoformat(published.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def _event_year(row: dict[str, str]) -> str:
    event_date = _event_date(row)
    return event_date[:4] if len(event_date) >= 4 else "unknown"


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


def _float_or_none(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _share_positive(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value > 0) / len(values)


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def _is_true(value: object) -> bool:
    return _clean(value).lower() in {"1", "true", "yes", "y"}


def _market_rows_by_ticker(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        ticker = _clean(row.get("ticker")).upper()
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(row)
    for ticker_rows in grouped.values():
        ticker_rows.sort(key=lambda row: _parse_date(row.get("date")))
    return grouped


def _first_index_on_or_after(rows: list[dict[str, str]], event_date: str) -> int | None:
    if not event_date:
        return None
    for index, row in enumerate(rows):
        if _parse_date(row.get("date")) >= event_date:
            return index
    return None


def _period_return(rows: list[dict[str, str]], start_index: int, days: int, key: str) -> float | None:
    end_index = start_index + days
    if end_index >= len(rows):
        return None
    start_value = _float_or_none(rows[start_index].get(key))
    end_value = _float_or_none(rows[end_index].get(key))
    if start_value in (None, 0) or end_value is None:
        return None
    return (end_value / start_value) - 1.0


def _volume_change(rows: list[dict[str, str]], start_index: int, days: int) -> float | None:
    end_index = start_index + days
    if end_index >= len(rows):
        return None
    start_value = _float_or_none(rows[start_index].get("volume"))
    end_value = _float_or_none(rows[end_index].get("volume"))
    if start_value in (None, 0) or end_value is None:
        return None
    return (end_value / start_value) - 1.0


def _car(rows: list[dict[str, str]], start_index: int, days: int) -> float | None:
    if start_index + days >= len(rows):
        return None
    cumulative = 0.0
    for step in range(1, days + 1):
        prev = rows[start_index + step - 1]
        current = rows[start_index + step]
        prev_stock = _float_or_none(prev.get("adjusted_close"))
        current_stock = _float_or_none(current.get("adjusted_close"))
        prev_bench = _float_or_none(prev.get("benchmark_adjusted_close"))
        current_bench = _float_or_none(current.get("benchmark_adjusted_close"))
        if (
            prev_stock in (None, 0)
            or current_stock is None
            or prev_bench in (None, 0)
            or current_bench is None
        ):
            return None
        stock_ret = (current_stock / prev_stock) - 1.0
        bench_ret = (current_bench / prev_bench) - 1.0
        cumulative += stock_ret - bench_ret
    return cumulative


def _safe_t_stat(values: list[float]) -> tuple[float | None, float | None, str]:
    n = len(values)
    if n < 2:
        return None, None, ""
    mean_value = _mean(values)
    if mean_value is None:
        return None, None, ""
    squared = sum((value - mean_value) ** 2 for value in values)
    variance = squared / (n - 1) if n > 1 else 0.0
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return None, None, ""
    t_stat = mean_value / (std_dev / math.sqrt(n))
    try:
        from scipy.stats import t as student_t  # type: ignore

        p_value = 2.0 * (1.0 - float(student_t.cdf(abs(t_stat), df=n - 1)))
        return t_stat, p_value, ""
    except Exception:
        return t_stat, None, "scipy_unavailable_p_value_blank"


def _event_lookup(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for row in rows:
        event_id = _clean(row.get("event_id"))
        if event_id and event_id not in lookup:
            lookup[event_id] = row
    return lookup


def _infer_unmatched_reason(
    event: dict[str, str],
    *,
    resolved_data_ticker: str,
    alias_applied: bool,
    market_rows_by_ticker: dict[str, list[dict[str, str]]],
) -> str:
    event_date = _event_date(event)
    if not event_date:
        return "malformed event date"
    ticker_rows = market_rows_by_ticker.get(resolved_data_ticker, [])
    if not ticker_rows:
        return "ticker alias issue" if alias_applied else "no ticker data"
    start_index = _first_index_on_or_after(ticker_rows, event_date)
    if start_index is None:
        last_date = _parse_date(ticker_rows[-1].get("date")) if ticker_rows else ""
        if last_date and event_date > last_date:
            return "too-recent event date"
        return "no trading day"
    if start_index + 20 >= len(ticker_rows):
        return "insufficient forward window"
    return "unknown"


def diagnose_event_study_matches(
    *,
    event_study_results_path: Path = DEFAULT_EVENT_STUDY_RESULTS_PATH,
    clean_events_path: Path = DEFAULT_CLEAN_EVENTS_PATH,
    market_data_path: Path = DEFAULT_MARKET_DATA_PATH,
    ticker_aliases_path: Path = DEFAULT_TICKER_ALIASES_PATH,
    output_csv_path: Path = DEFAULT_MATCH_DIAGNOSTICS_CSV_PATH,
    output_md_path: Path = DEFAULT_MATCH_DIAGNOSTICS_MD_PATH,
) -> MatchDiagnosticsResult:
    ensure_data_dirs()
    clean_rows = _read_csv(clean_events_path)
    result_rows = _read_csv(event_study_results_path)
    market_rows = _read_csv(market_data_path)
    aliases = load_ticker_aliases(ticker_aliases_path)
    results_by_event_id = _event_lookup(result_rows)
    market_rows_by_ticker = _market_rows_by_ticker(market_rows)

    diagnostic_rows: list[dict[str, Any]] = []
    unmatched_reason_counts: dict[str, int] = {}

    for event in clean_rows:
        event_id = _clean(event.get("event_id"))
        matched_row = results_by_event_id.get(event_id)
        event_ticker = _clean(event.get("ticker")).upper()
        event_date = _event_date(event)
        resolved_data_ticker, alias_applied = resolve_data_ticker(
            event_ticker,
            aliases=aliases,
            event_date=event_date,
        )
        if matched_row:
            data_ticker = _clean(matched_row.get("data_ticker")).upper() or resolved_data_ticker
            reason = ""
            missing_flag = False
        else:
            data_ticker = resolved_data_ticker
            reason = _infer_unmatched_reason(
                event,
                resolved_data_ticker=resolved_data_ticker,
                alias_applied=alias_applied,
                market_rows_by_ticker=market_rows_by_ticker,
            )
            missing_flag = True
            unmatched_reason_counts[reason] = unmatched_reason_counts.get(reason, 0) + 1

        diagnostic_rows.append(
            {
                "event_id": event_id,
                "ticker": event_ticker,
                "data_ticker": data_ticker,
                "creator": _clean(event.get("creator")),
                "title": _clean(event.get("title")),
                "published_at": _clean(event.get("published_at")),
                "event_date_weekday_adjusted": event_date,
                "matched_event_study_row": bool(matched_row),
                "missing_market_data_flag": missing_flag,
                "missing_market_data_reason": reason,
                "ticker_alias_applied": alias_applied,
            }
        )

    diagnostic_columns = [
        "event_id",
        "ticker",
        "data_ticker",
        "creator",
        "title",
        "published_at",
        "event_date_weekday_adjusted",
        "matched_event_study_row",
        "missing_market_data_flag",
        "missing_market_data_reason",
        "ticker_alias_applied",
    ]
    _write_csv(output_csv_path, diagnostic_rows, diagnostic_columns)

    total_clean_events = len(clean_rows)
    total_result_rows = len(result_rows)
    matched_events = sum(1 for row in diagnostic_rows if _is_true(row.get("matched_event_study_row")))
    unmatched_events = total_clean_events - matched_events

    lines = [
        "# Event Study Match Diagnostics",
        "",
        f"- Clean events input: `{clean_events_path}`",
        f"- Event-study results input: `{event_study_results_path}`",
        f"- Market-data input: `{market_data_path}`",
        f"- Total clean events: {total_clean_events}",
        f"- Total event-study result rows: {total_result_rows}",
        f"- Matched events: {matched_events}",
        f"- Unmatched events: {unmatched_events}",
        "",
        "## Unmatched Reason Counts",
        "",
    ]
    if unmatched_reason_counts:
        for reason, count in sorted(unmatched_reason_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Unmatched Event IDs", ""])
    unmatched_rows = [row for row in diagnostic_rows if _is_true(row.get("missing_market_data_flag"))]
    if unmatched_rows:
        for row in unmatched_rows:
            lines.append(
                f"- event_id={row['event_id']}, ticker={row['ticker']}, "
                f"data_ticker={row['data_ticker']}, reason={row['missing_market_data_reason']}"
            )
    else:
        lines.append("- None.")
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text("\n".join(lines), encoding="utf-8")

    return MatchDiagnosticsResult(
        csv_path=output_csv_path,
        markdown_path=output_md_path,
        total_clean_events=total_clean_events,
        matched_events=matched_events,
        unmatched_events=unmatched_events,
        unmatched_reason_counts=tuple(
            sorted(unmatched_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
    )


def _enriched_event_rows(
    result_rows: list[dict[str, str]],
    *,
    clean_rows_by_event_id: dict[str, dict[str, str]],
    market_rows_by_ticker: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in result_rows:
        event_id = _clean(row.get("event_id"))
        event_row = clean_rows_by_event_id.get(event_id, {})
        data_ticker = _clean(row.get("data_ticker") or row.get("ticker")).upper()
        match_date = _parse_date(row.get("matched_market_date"))
        ticker_rows = market_rows_by_ticker.get(data_ticker, [])
        start_index = _first_index_on_or_after(ticker_rows, match_date) if match_date else None
        return_20d = None
        benchmark_return_20d = None
        abnormal_return_20d = None
        car_5d = None
        car_20d = None
        volume_change_5d = None
        volume_change_20d = None
        if start_index is not None:
            return_20d = _period_return(ticker_rows, start_index, 20, "adjusted_close")
            benchmark_return_20d = _period_return(ticker_rows, start_index, 20, "benchmark_adjusted_close")
            if return_20d is not None and benchmark_return_20d is not None:
                abnormal_return_20d = return_20d - benchmark_return_20d
            car_5d = _car(ticker_rows, start_index, 5)
            car_20d = _car(ticker_rows, start_index, 20)
            volume_change_5d = _volume_change(ticker_rows, start_index, 5)
            volume_change_20d = _volume_change(ticker_rows, start_index, 20)

        enriched.append(
            {
                **row,
                "creator": _clean(event_row.get("creator")),
                "title": _clean(event_row.get("title")),
                "published_at": _clean(event_row.get("published_at")),
                "event_year": _event_year(event_row) if event_row else "",
                "return_1d_num": _float_or_none(row.get("return_1d")),
                "return_5d_num": _float_or_none(row.get("return_5d")),
                "abnormal_return_1d_num": _float_or_none(row.get("abnormal_return_1d")),
                "abnormal_return_5d_num": _float_or_none(row.get("abnormal_return_5d")),
                "return_20d_num": return_20d,
                "benchmark_return_20d_num": benchmark_return_20d,
                "abnormal_return_20d_num": abnormal_return_20d,
                "car_5d_num": car_5d,
                "car_20d_num": car_20d,
                "volume_change_5d_num": volume_change_5d,
                "volume_change_20d_num": volume_change_20d,
            }
        )
    return enriched


def _column_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, int | float):
            values.append(float(value))
    return values


def _build_main_metrics(
    *,
    event_count: int,
    matched_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    return_1d = _column_values(matched_rows, "return_1d_num")
    return_5d = _column_values(matched_rows, "return_5d_num")
    return_20d = _column_values(matched_rows, "return_20d_num")
    abnormal_1d = _column_values(matched_rows, "abnormal_return_1d_num")
    abnormal_5d = _column_values(matched_rows, "abnormal_return_5d_num")
    abnormal_20d = _column_values(matched_rows, "abnormal_return_20d_num")
    car_5d = _column_values(matched_rows, "car_5d_num")
    car_20d = _column_values(matched_rows, "car_20d_num")
    volume_change_5d = _column_values(matched_rows, "volume_change_5d_num")
    volume_change_20d = _column_values(matched_rows, "volume_change_20d_num")

    notes: list[str] = []
    t_targets = {
        "abnormal_return_1d": abnormal_1d,
        "abnormal_return_5d": abnormal_5d,
        "abnormal_return_20d": abnormal_20d,
        "car_5d": car_5d,
        "car_20d": car_20d,
    }
    t_results: dict[str, tuple[float | None, float | None]] = {}
    for key, values in t_targets.items():
        t_stat, p_value, note = _safe_t_stat(values)
        t_results[key] = (t_stat, p_value)
        if note and note not in notes:
            notes.append(note)

    row = {
        "event_count": event_count,
        "matched_count": len(matched_rows),
        "mean_return_1d": _fmt(_mean(return_1d)),
        "median_return_1d": _fmt(_median(return_1d)),
        "mean_return_5d": _fmt(_mean(return_5d)),
        "median_return_5d": _fmt(_median(return_5d)),
        "mean_return_20d": _fmt(_mean(return_20d)),
        "median_return_20d": _fmt(_median(return_20d)),
        "mean_abnormal_return_1d": _fmt(_mean(abnormal_1d)),
        "median_abnormal_return_1d": _fmt(_median(abnormal_1d)),
        "mean_abnormal_return_5d": _fmt(_mean(abnormal_5d)),
        "median_abnormal_return_5d": _fmt(_median(abnormal_5d)),
        "mean_abnormal_return_20d": _fmt(_mean(abnormal_20d)),
        "median_abnormal_return_20d": _fmt(_median(abnormal_20d)),
        "mean_car_5d": _fmt(_mean(car_5d)),
        "median_car_5d": _fmt(_median(car_5d)),
        "mean_car_20d": _fmt(_mean(car_20d)),
        "median_car_20d": _fmt(_median(car_20d)),
        "positive_abnormal_return_1d_share": _fmt(_share_positive(abnormal_1d)),
        "positive_abnormal_return_5d_share": _fmt(_share_positive(abnormal_5d)),
        "positive_abnormal_return_20d_share": _fmt(_share_positive(abnormal_20d)),
        "mean_volume_change_5d": _fmt(_mean(volume_change_5d)),
        "median_volume_change_5d": _fmt(_median(volume_change_5d)),
        "mean_volume_change_20d": _fmt(_mean(volume_change_20d)),
        "median_volume_change_20d": _fmt(_median(volume_change_20d)),
        "t_stat_abnormal_return_1d": _fmt(t_results["abnormal_return_1d"][0]),
        "p_value_abnormal_return_1d": _fmt(t_results["abnormal_return_1d"][1]),
        "t_stat_abnormal_return_5d": _fmt(t_results["abnormal_return_5d"][0]),
        "p_value_abnormal_return_5d": _fmt(t_results["abnormal_return_5d"][1]),
        "t_stat_abnormal_return_20d": _fmt(t_results["abnormal_return_20d"][0]),
        "p_value_abnormal_return_20d": _fmt(t_results["abnormal_return_20d"][1]),
        "t_stat_car_5d": _fmt(t_results["car_5d"][0]),
        "p_value_car_5d": _fmt(t_results["car_5d"][1]),
        "t_stat_car_20d": _fmt(t_results["car_20d"][0]),
        "p_value_car_20d": _fmt(t_results["car_20d"][1]),
    }
    return row, notes


def _write_main_markdown(path: Path, row: dict[str, Any], *, notes: list[str]) -> Path:
    lines = [
        "# Event Study Main Table (Prototype)",
        "",
        f"- event_count: {row['event_count']}",
        f"- matched_count: {row['matched_count']}",
        f"- mean_abnormal_return_1d: {row['mean_abnormal_return_1d']}",
        f"- mean_abnormal_return_5d: {row['mean_abnormal_return_5d']}",
        f"- mean_abnormal_return_20d: {row['mean_abnormal_return_20d']}",
        f"- mean_car_5d: {row['mean_car_5d']}",
        f"- mean_car_20d: {row['mean_car_20d']}",
        "",
        "## Statistical Tests",
        "",
        f"- abnormal_return_1d: t={row['t_stat_abnormal_return_1d']}, p={row['p_value_abnormal_return_1d']}",
        f"- abnormal_return_5d: t={row['t_stat_abnormal_return_5d']}, p={row['p_value_abnormal_return_5d']}",
        f"- abnormal_return_20d: t={row['t_stat_abnormal_return_20d']}, p={row['p_value_abnormal_return_20d']}",
        f"- car_5d: t={row['t_stat_car_5d']}, p={row['p_value_car_5d']}",
        f"- car_20d: t={row['t_stat_car_20d']}, p={row['p_value_car_20d']}",
    ]
    if notes:
        lines.extend(["", "## Notes", ""])
        for note in notes:
            if note == "scipy_unavailable_p_value_blank":
                lines.append("- scipy unavailable; p-values are left blank.")
            else:
                lines.append(f"- {note}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _group_summary_rows(
    *,
    group_key: str,
    clean_rows: list[dict[str, str]],
    matched_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clean_counts: dict[str, int] = {}
    for row in clean_rows:
        group_value = _clean(row.get(group_key)).upper() if group_key == "ticker" else _clean(row.get(group_key))
        if group_key == "event_year":
            group_value = _event_year(row)
        group_value = group_value or "unknown"
        clean_counts[group_value] = clean_counts.get(group_value, 0) + 1

    matched_groups: dict[str, list[dict[str, Any]]] = {}
    for row in matched_rows:
        if group_key == "event_year":
            group_value = _clean(row.get("event_year"))
        elif group_key == "ticker":
            group_value = _clean(row.get("ticker")).upper()
        else:
            group_value = _clean(row.get(group_key))
        group_value = group_value or "unknown"
        matched_groups.setdefault(group_value, []).append(row)

    all_groups = sorted(set(clean_counts) | set(matched_groups))
    output_rows: list[dict[str, Any]] = []
    for group_value in all_groups:
        rows = matched_groups.get(group_value, [])
        output_rows.append(
            {
                "group": group_value,
                "event_count": clean_counts.get(group_value, 0),
                "matched_count": len(rows),
                "mean_abnormal_return_1d": _fmt(_mean(_column_values(rows, "abnormal_return_1d_num"))),
                "mean_abnormal_return_5d": _fmt(_mean(_column_values(rows, "abnormal_return_5d_num"))),
                "mean_abnormal_return_20d": _fmt(_mean(_column_values(rows, "abnormal_return_20d_num"))),
                "mean_car_5d": _fmt(_mean(_column_values(rows, "car_5d_num"))),
                "mean_car_20d": _fmt(_mean(_column_values(rows, "car_20d_num"))),
                "positive_abnormal_return_5d_share": _fmt(
                    _share_positive(_column_values(rows, "abnormal_return_5d_num"))
                ),
                "mean_volume_change_5d": _fmt(_mean(_column_values(rows, "volume_change_5d_num"))),
            }
        )
    return output_rows


def _write_methodology_note(path: Path) -> Path:
    lines = [
        "# Methodology Note: yfinance Prototype Event Study",
        "",
        "- Transcript records were collected and recommendation events were classified automatically.",
        "- The clean event sample reflects strict rules-based validation outputs.",
        "- Market data in this report is interim yfinance/Yahoo Finance prototype data.",
        "- yfinance is not Bloomberg-quality data and should be replaced before final inference.",
        "- Abnormal returns are benchmark-adjusted against SPY.",
        "- Event-study evidence here is associational and does not prove causality.",
        "- The most recent event dates may not have complete 20-trading-day forward windows.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_event_study_reporting(
    *,
    event_study_results_path: Path = DEFAULT_EVENT_STUDY_RESULTS_PATH,
    clean_events_path: Path = DEFAULT_CLEAN_EVENTS_PATH,
    threshold_sensitivity_path: Path = DEFAULT_THRESHOLD_SENSITIVITY_PATH,
    market_data_path: Path = DEFAULT_MARKET_DATA_PATH,
    yfinance_fetch_summary_path: Path = DEFAULT_YFINANCE_FETCH_SUMMARY_PATH,
    main_table_csv_path: Path = DEFAULT_MAIN_TABLE_CSV_PATH,
    main_table_md_path: Path = DEFAULT_MAIN_TABLE_MD_PATH,
    by_creator_csv_path: Path = DEFAULT_BY_CREATOR_CSV_PATH,
    by_ticker_csv_path: Path = DEFAULT_BY_TICKER_CSV_PATH,
    by_year_csv_path: Path = DEFAULT_BY_YEAR_CSV_PATH,
    by_recommendation_type_csv_path: Path = DEFAULT_BY_RECOMMENDATION_TYPE_CSV_PATH,
    by_direction_csv_path: Path = DEFAULT_BY_DIRECTION_CSV_PATH,
    robustness_csv_path: Path = DEFAULT_ROBUSTNESS_CSV_PATH,
    report_summary_md_path: Path = DEFAULT_REPORT_SUMMARY_MD_PATH,
    methodology_note_path: Path = DEFAULT_METHODOLOGY_NOTE_PATH,
) -> EventStudyReportingResult:
    ensure_data_dirs()
    clean_rows = _read_csv(clean_events_path)
    result_rows = _read_csv(event_study_results_path)
    threshold_rows = _read_csv(threshold_sensitivity_path)
    market_rows = _read_csv(market_data_path)
    fetch_summary_rows = _read_csv(yfinance_fetch_summary_path) if yfinance_fetch_summary_path.exists() else []

    clean_by_event = _event_lookup(clean_rows)
    market_by_ticker = _market_rows_by_ticker(market_rows)
    enriched_rows = _enriched_event_rows(
        result_rows,
        clean_rows_by_event_id=clean_by_event,
        market_rows_by_ticker=market_by_ticker,
    )

    event_count = len(clean_rows)
    matched_count = len(result_rows)
    main_row, t_notes = _build_main_metrics(event_count=event_count, matched_rows=enriched_rows)
    _write_csv(main_table_csv_path, [main_row], list(main_row.keys()))
    _write_main_markdown(main_table_md_path, main_row, notes=t_notes)

    by_creator_rows = _group_summary_rows(
        group_key="creator",
        clean_rows=clean_rows,
        matched_rows=enriched_rows,
    )
    by_ticker_rows = _group_summary_rows(
        group_key="ticker",
        clean_rows=clean_rows,
        matched_rows=enriched_rows,
    )
    by_year_rows = _group_summary_rows(
        group_key="event_year",
        clean_rows=clean_rows,
        matched_rows=enriched_rows,
    )
    by_recommendation_type_rows = _group_summary_rows(
        group_key="recommendation_type",
        clean_rows=clean_rows,
        matched_rows=enriched_rows,
    )
    by_direction_rows = _group_summary_rows(
        group_key="direction",
        clean_rows=clean_rows,
        matched_rows=enriched_rows,
    )

    _write_csv(by_creator_csv_path, by_creator_rows, GROUP_SUMMARY_COLUMNS)
    _write_csv(by_ticker_csv_path, by_ticker_rows, GROUP_SUMMARY_COLUMNS)
    _write_csv(by_year_csv_path, by_year_rows, GROUP_SUMMARY_COLUMNS)
    _write_csv(by_recommendation_type_csv_path, by_recommendation_type_rows, GROUP_SUMMARY_COLUMNS)
    _write_csv(by_direction_csv_path, by_direction_rows, GROUP_SUMMARY_COLUMNS)

    robustness_rows: list[dict[str, Any]] = []
    for row in threshold_rows:
        robustness_rows.append(
            {
                "min_confidence": _clean(row.get("min_confidence")),
                "included_strict_count": _clean(row.get("included_strict_count")),
                "included_with_review_count": _clean(row.get("included_with_review_count")),
                "included_with_weak_evidence_count": _clean(row.get("included_with_weak_evidence_count")),
                "excluded_count": _clean(row.get("excluded_count")),
                "unique_ticker_count": _clean(row.get("unique_ticker_count")),
                "unique_creator_count": _clean(row.get("unique_creator_count")),
                "current_matched_count": matched_count,
                "current_match_rate": _fmt((matched_count / event_count) if event_count else None),
            }
        )
    robustness_columns = [
        "min_confidence",
        "included_strict_count",
        "included_with_review_count",
        "included_with_weak_evidence_count",
        "excluded_count",
        "unique_ticker_count",
        "unique_creator_count",
        "current_matched_count",
        "current_match_rate",
    ]
    _write_csv(robustness_csv_path, robustness_rows, robustness_columns)

    methodology_path = _write_methodology_note(methodology_note_path)
    report_lines = [
        "# Event Study Reporting Summary",
        "",
        f"- Clean events: {event_count}",
        f"- Matched event-study rows: {matched_count}",
        f"- Match rate: {_fmt((matched_count / event_count) if event_count else None)}",
        f"- Main table: `{main_table_csv_path}`",
        f"- Grouped by creator: `{by_creator_csv_path}`",
        f"- Grouped by ticker: `{by_ticker_csv_path}`",
        f"- Grouped by year: `{by_year_csv_path}`",
        f"- Grouped by recommendation_type: `{by_recommendation_type_csv_path}`",
        f"- Grouped by direction: `{by_direction_csv_path}`",
        f"- Robustness table: `{robustness_csv_path}`",
        f"- Methodology note: `{methodology_path}`",
        "",
        "Prototype caveat: this reporting uses interim yfinance/Yahoo data and should be replaced with Bloomberg data before final inference.",
    ]
    if fetch_summary_rows:
        alias_count = sum(
            1
            for row in fetch_summary_rows
            if _clean(row.get("role")) == "security" and _is_true(row.get("ticker_alias_applied"))
        )
        report_lines.append(f"- yfinance alias mappings observed in fetch summary: {alias_count}")
    report_summary_md_path.parent.mkdir(parents=True, exist_ok=True)
    report_summary_md_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return EventStudyReportingResult(
        main_table_csv_path=main_table_csv_path,
        main_table_md_path=main_table_md_path,
        by_creator_csv_path=by_creator_csv_path,
        by_ticker_csv_path=by_ticker_csv_path,
        by_year_csv_path=by_year_csv_path,
        by_recommendation_type_csv_path=by_recommendation_type_csv_path,
        by_direction_csv_path=by_direction_csv_path,
        robustness_csv_path=robustness_csv_path,
        report_summary_md_path=report_summary_md_path,
        methodology_note_path=methodology_path,
        event_count=event_count,
        matched_count=matched_count,
    )


def _load_reporting_frame(event_study_results_path: Path, clean_events_path: Path, market_data_path: Path) -> pd.DataFrame:
    result_rows = _read_csv(event_study_results_path)
    clean_rows = _read_csv(clean_events_path)
    market_rows = _read_csv(market_data_path)
    clean_by_event = _event_lookup(clean_rows)
    market_by_ticker = _market_rows_by_ticker(market_rows)
    enriched_rows = _enriched_event_rows(
        result_rows,
        clean_rows_by_event_id=clean_by_event,
        market_rows_by_ticker=market_by_ticker,
    )
    return pd.DataFrame(enriched_rows)


def build_event_study_charts(
    *,
    event_study_results_path: Path = DEFAULT_EVENT_STUDY_RESULTS_PATH,
    clean_events_path: Path = DEFAULT_CLEAN_EVENTS_PATH,
    market_data_path: Path = DEFAULT_MARKET_DATA_PATH,
    output_dir: Path = REPORTING_CHARTS_DIR,
) -> EventStudyChartsResult:
    ensure_data_dirs()
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError("matplotlib is required to build event-study charts.") from exc

    frame = _load_reporting_frame(event_study_results_path, clean_events_path, market_data_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    def _hist(column: str, filename: str, title: str) -> Path:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(values, bins=25)
        ax.set_title(title)
        ax.set_xlabel(column)
        ax.set_ylabel("count")
        fig.tight_layout()
        path = output_dir / filename
        fig.savefig(path, format="png")
        plt.close(fig)
        return path

    chart_paths: list[Path] = []
    chart_paths.append(
        _hist("abnormal_return_1d_num", "abnormal_return_1d_distribution.png", "Abnormal Return 1D")
    )
    chart_paths.append(
        _hist("abnormal_return_5d_num", "abnormal_return_5d_distribution.png", "Abnormal Return 5D")
    )
    chart_paths.append(
        _hist("abnormal_return_20d_num", "abnormal_return_20d_distribution.png", "Abnormal Return 20D")
    )
    chart_paths.append(_hist("car_5d_num", "car_5d_distribution.png", "CAR 5D"))
    chart_paths.append(_hist("car_20d_num", "car_20d_distribution.png", "CAR 20D"))

    mean_by_window = {
        "1d": pd.to_numeric(frame["abnormal_return_1d_num"], errors="coerce").mean(),
        "5d": pd.to_numeric(frame["abnormal_return_5d_num"], errors="coerce").mean(),
        "20d": pd.to_numeric(frame["abnormal_return_20d_num"], errors="coerce").mean(),
    }
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(list(mean_by_window.keys()), list(mean_by_window.values()))
    ax.set_title("Mean Abnormal Return by Window")
    ax.set_xlabel("window")
    ax.set_ylabel("mean abnormal return")
    fig.tight_layout()
    path = output_dir / "mean_abnormal_return_by_window.png"
    fig.savefig(path, format="png")
    plt.close(fig)
    chart_paths.append(path)

    clean_df = pd.DataFrame(_read_csv(clean_events_path))
    clean_df["event_year"] = clean_df.apply(lambda row: _event_year(dict(row)), axis=1)
    by_year = clean_df["event_year"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(by_year.index.tolist(), by_year.values.tolist())
    ax.set_title("Events by Year")
    ax.set_xlabel("year")
    ax.set_ylabel("events")
    fig.tight_layout()
    path = output_dir / "events_by_year.png"
    fig.savefig(path, format="png")
    plt.close(fig)
    chart_paths.append(path)

    creator_counts = clean_df["creator"].fillna("").replace("", "unknown").value_counts().head(10)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(creator_counts.index.tolist(), creator_counts.values.tolist())
    ax.set_title("Events by Creator (Top 10)")
    ax.set_xlabel("creator")
    ax.set_ylabel("events")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    path = output_dir / "events_by_creator_top10.png"
    fig.savefig(path, format="png")
    plt.close(fig)
    chart_paths.append(path)

    ticker_counts = clean_df["ticker"].fillna("").replace("", "unknown").str.upper().value_counts().head(10)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(ticker_counts.index.tolist(), ticker_counts.values.tolist())
    ax.set_title("Events by Ticker (Top 10)")
    ax.set_xlabel("ticker")
    ax.set_ylabel("events")
    fig.tight_layout()
    path = output_dir / "events_by_ticker_top10.png"
    fig.savefig(path, format="png")
    plt.close(fig)
    chart_paths.append(path)

    car_creator = (
        frame.assign(car_20d_num=pd.to_numeric(frame["car_20d_num"], errors="coerce"))
        .groupby("creator", dropna=False)["car_20d_num"]
        .mean()
        .dropna()
        .sort_values(ascending=False)
        .head(10)
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(car_creator.index.tolist(), car_creator.values.tolist())
    ax.set_title("Mean CAR 20D by Creator (Top 10)")
    ax.set_xlabel("creator")
    ax.set_ylabel("mean car 20d")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    path = output_dir / "mean_car_20d_by_creator_top10.png"
    fig.savefig(path, format="png")
    plt.close(fig)
    chart_paths.append(path)

    return EventStudyChartsResult(output_dir=output_dir, chart_paths=tuple(chart_paths))
