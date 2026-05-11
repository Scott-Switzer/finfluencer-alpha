from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import EXPORTS_DIR, ensure_data_dirs
from .utils import configure_csv_field_size_limit

VALIDATION_DIR = EXPORTS_DIR / "validation"
MARKET_DATA_DIR = EXPORTS_DIR / "market_data"

DEFAULT_CLEAN_EVENTS_INPUT_PATH = VALIDATION_DIR / "clean_auto_labeled_events.csv"
DEFAULT_AUTO_LABELED_INPUT_PATH = VALIDATION_DIR / "event_validation_sample_auto_labeled.csv"
DEFAULT_MARKET_DATA_REQUEST_PATH = MARKET_DATA_DIR / "market_data_request.csv"
DEFAULT_UNIQUE_TICKERS_PATH = MARKET_DATA_DIR / "unique_tickers.csv"
DEFAULT_EVENT_DATES_BY_TICKER_PATH = MARKET_DATA_DIR / "event_dates_by_ticker.csv"
DEFAULT_MARKET_DATA_SUMMARY_PATH = MARKET_DATA_DIR / "market_data_request_summary.md"
DEFAULT_THRESHOLD_SENSITIVITY_CSV_PATH = (
    VALIDATION_DIR / "clean_event_threshold_sensitivity.csv"
)
DEFAULT_THRESHOLD_SENSITIVITY_MD_PATH = VALIDATION_DIR / "clean_event_threshold_sensitivity.md"

REQUESTED_PRICE_FIELDS = "adjusted_close, volume"
REQUESTED_SECURITY_FIELDS = "sector, industry, market_cap, beta, average_dollar_volume"
DEFAULT_BENCHMARK = "SPY"
MARKET_DATA_NOTE = "weekday adjusted only; market holiday calendar not yet applied."
THRESHOLDS = [0.90, 0.85, 0.80, 0.75, 0.70, 0.65]

MARKET_DATA_REQUEST_COLUMNS = [
    "event_id",
    "video_id",
    "ticker",
    "company_name",
    "creator",
    "title",
    "published_at",
    "event_date_utc",
    "event_date_weekday_adjusted",
    "recommended_start_date",
    "recommended_end_date",
    "recommendation_type",
    "direction",
    "confidence",
    "evidence_quality",
    "source_transcript_type",
    "video_url",
    "requested_price_fields",
    "requested_security_fields",
    "preferred_benchmark",
    "notes",
]

UNIQUE_TICKER_COLUMNS = [
    "ticker",
    "company_name",
    "event_count",
    "first_event_date",
    "last_event_date",
]

EVENT_DATES_BY_TICKER_COLUMNS = [
    "ticker",
    "event_id",
    "event_date_weekday_adjusted",
    "creator",
    "recommendation_type",
    "direction",
    "confidence",
]

THRESHOLD_SENSITIVITY_COLUMNS = [
    "min_confidence",
    "included_strict_count",
    "included_with_review_count",
    "included_with_weak_evidence_count",
    "excluded_count",
    "unique_ticker_count",
    "unique_creator_count",
]


@dataclass(frozen=True)
class MarketDataRequestResult:
    request_path: Path
    unique_tickers_path: Path
    event_dates_by_ticker_path: Path
    summary_md_path: Path
    total_clean_events: int
    unique_ticker_count: int
    min_event_date: str
    max_event_date: str


@dataclass(frozen=True)
class ThresholdSensitivityResult:
    csv_path: Path
    markdown_path: Path
    total_rows: int
    threshold_rows: int


def _clean(value: object) -> str:
    return str(value or "").strip()


def _float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _boolish(value: object) -> bool:
    return _clean(value).lower() in {"1", "true", "yes", "y"}


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


def _parse_published_date(value: object) -> date:
    text = _clean(value)
    if not text:
        raise ValueError("published_at is required for market-data request rows")
    iso_text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"Could not parse published_at value: {text}") from exc


def weekday_adjust_event_date(event_date: date) -> date:
    if event_date.weekday() == 5:
        return event_date + timedelta(days=2)
    if event_date.weekday() == 6:
        return event_date + timedelta(days=1)
    return event_date


def _market_request_row(row: dict[str, Any], *, preferred_benchmark: str) -> dict[str, Any]:
    event_date_utc = _parse_published_date(row.get("published_at"))
    adjusted_date = weekday_adjust_event_date(event_date_utc)
    return {
        "event_id": _clean(row.get("event_id")),
        "video_id": _clean(row.get("video_id")),
        "ticker": _clean(row.get("ticker")).upper(),
        "company_name": _clean(row.get("company_name")),
        "creator": _clean(row.get("creator")),
        "title": _clean(row.get("title")),
        "published_at": _clean(row.get("published_at")),
        "event_date_utc": event_date_utc.isoformat(),
        "event_date_weekday_adjusted": adjusted_date.isoformat(),
        "recommended_start_date": (adjusted_date - timedelta(days=260)).isoformat(),
        "recommended_end_date": (adjusted_date + timedelta(days=45)).isoformat(),
        "recommendation_type": _clean(row.get("recommendation_type")),
        "direction": _clean(row.get("direction")),
        "confidence": _clean(row.get("confidence") or row.get("auto_label_confidence")),
        "evidence_quality": _clean(row.get("evidence_quality")),
        "source_transcript_type": _clean(row.get("source_transcript_type")),
        "video_url": _clean(row.get("video_url")),
        "requested_price_fields": REQUESTED_PRICE_FIELDS,
        "requested_security_fields": REQUESTED_SECURITY_FIELDS,
        "preferred_benchmark": preferred_benchmark,
        "notes": MARKET_DATA_NOTE,
    }


def _unique_ticker_rows(request_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in request_rows:
        grouped[_clean(row.get("ticker")).upper()].append(row)

    rows: list[dict[str, Any]] = []
    for ticker, ticker_rows in sorted(grouped.items()):
        event_dates = sorted(_clean(row.get("event_date_weekday_adjusted")) for row in ticker_rows)
        company_counter = Counter(_clean(row.get("company_name")) for row in ticker_rows)
        company_name = company_counter.most_common(1)[0][0] if company_counter else ""
        rows.append(
            {
                "ticker": ticker,
                "company_name": company_name,
                "event_count": len(ticker_rows),
                "first_event_date": event_dates[0] if event_dates else "",
                "last_event_date": event_dates[-1] if event_dates else "",
            }
        )
    return rows


def _event_dates_by_ticker_rows(request_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "ticker": _clean(row.get("ticker")).upper(),
            "event_id": _clean(row.get("event_id")),
            "event_date_weekday_adjusted": _clean(row.get("event_date_weekday_adjusted")),
            "creator": _clean(row.get("creator")),
            "recommendation_type": _clean(row.get("recommendation_type")),
            "direction": _clean(row.get("direction")),
            "confidence": _clean(row.get("confidence")),
        }
        for row in request_rows
    ]
    rows.sort(
        key=lambda row: (
            row["ticker"],
            row["event_date_weekday_adjusted"],
            row["event_id"],
        )
    )
    return rows


def _counter_lines(counter: Counter[str], *, limit: int = 10) -> list[str]:
    if not counter:
        return ["- None."]
    return [f"- {segment}: {count}" for segment, count in counter.most_common(limit)]


def _write_market_summary(
    path: Path,
    *,
    input_path: Path,
    request_path: Path,
    unique_tickers_path: Path,
    event_dates_by_ticker_path: Path,
    request_rows: list[dict[str, Any]],
    unique_rows: list[dict[str, Any]],
    preferred_benchmark: str,
) -> Path:
    event_dates = sorted(_clean(row.get("event_date_weekday_adjusted")) for row in request_rows)
    years = Counter(date_text[:4] for date_text in event_dates if len(date_text) >= 4)
    creators = Counter(_clean(row.get("creator")) or "unknown" for row in request_rows)
    tickers = Counter(_clean(row.get("ticker")) or "unknown" for row in request_rows)
    recommendation_types = Counter(
        _clean(row.get("recommendation_type")) or "unknown" for row in request_rows
    )
    directions = Counter(_clean(row.get("direction")) or "unknown" for row in request_rows)
    lines = [
        "# Market Data Request Summary",
        "",
        f"- Source clean events: `{input_path}`",
        f"- Market-data request: `{request_path}`",
        f"- Unique tickers: `{unique_tickers_path}`",
        f"- Event dates by ticker: `{event_dates_by_ticker_path}`",
        f"- Total clean events: {len(request_rows)}",
        f"- Unique ticker count: {len(unique_rows)}",
        f"- Min event date: {event_dates[0] if event_dates else ''}",
        f"- Max event date: {event_dates[-1] if event_dates else ''}",
        f"- Benchmark used: {preferred_benchmark}",
        "",
        "## Events By Year",
        "",
        *_counter_lines(years),
        "",
        "## Top Creators",
        "",
        *_counter_lines(creators),
        "",
        "## Top Tickers",
        "",
        *_counter_lines(tickers),
        "",
        "## Recommendation Types",
        "",
        *_counter_lines(recommendation_types),
        "",
        "## Directions",
        "",
        *_counter_lines(directions),
        "",
        "## Licensed Data Warning",
        "",
        "Bloomberg or other licensed raw market data should not be committed to this repository. "
        "Commit only derived, shareable outputs allowed by the data license.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_market_data_request(
    *,
    input_path: Path = DEFAULT_CLEAN_EVENTS_INPUT_PATH,
    request_path: Path = DEFAULT_MARKET_DATA_REQUEST_PATH,
    unique_tickers_path: Path = DEFAULT_UNIQUE_TICKERS_PATH,
    event_dates_by_ticker_path: Path = DEFAULT_EVENT_DATES_BY_TICKER_PATH,
    summary_md_path: Path = DEFAULT_MARKET_DATA_SUMMARY_PATH,
    preferred_benchmark: str = DEFAULT_BENCHMARK,
) -> MarketDataRequestResult:
    if not input_path.exists():
        raise FileNotFoundError(f"Clean auto-labeled events input not found: {input_path}")
    ensure_data_dirs()
    request_rows = [
        _market_request_row(row, preferred_benchmark=preferred_benchmark)
        for row in _read_csv(input_path)
    ]
    request_rows.sort(
        key=lambda row: (
            row["event_date_weekday_adjusted"],
            row["ticker"],
            row["event_id"],
        )
    )
    unique_rows = _unique_ticker_rows(request_rows)
    event_date_rows = _event_dates_by_ticker_rows(request_rows)
    _write_csv(request_path, request_rows, MARKET_DATA_REQUEST_COLUMNS)
    _write_csv(unique_tickers_path, unique_rows, UNIQUE_TICKER_COLUMNS)
    _write_csv(event_dates_by_ticker_path, event_date_rows, EVENT_DATES_BY_TICKER_COLUMNS)
    _write_market_summary(
        summary_md_path,
        input_path=input_path,
        request_path=request_path,
        unique_tickers_path=unique_tickers_path,
        event_dates_by_ticker_path=event_dates_by_ticker_path,
        request_rows=request_rows,
        unique_rows=unique_rows,
        preferred_benchmark=preferred_benchmark,
    )
    event_dates = sorted(_clean(row.get("event_date_weekday_adjusted")) for row in request_rows)
    return MarketDataRequestResult(
        request_path=request_path,
        unique_tickers_path=unique_tickers_path,
        event_dates_by_ticker_path=event_dates_by_ticker_path,
        summary_md_path=summary_md_path,
        total_clean_events=len(request_rows),
        unique_ticker_count=len(unique_rows),
        min_event_date=event_dates[0] if event_dates else "",
        max_event_date=event_dates[-1] if event_dates else "",
    )


def _threshold_base_filter(row: dict[str, Any], *, threshold: float) -> bool:
    return (
        _clean(row.get("is_true_recommendation")).lower() == "yes"
        and _clean(row.get("direction")).lower() != "unclear"
        and _float_or_zero(row.get("auto_label_confidence")) >= threshold
    )


def _threshold_rows_for_mode(
    rows: list[dict[str, Any]],
    *,
    threshold: float,
    include_review_needed: bool,
    include_weak_evidence: bool,
) -> list[dict[str, Any]]:
    included: list[dict[str, Any]] = []
    for row in rows:
        evidence_quality = _clean(row.get("evidence_quality")).lower()
        if not _threshold_base_filter(row, threshold=threshold):
            continue
        if evidence_quality not in {"strong", "medium"} and not include_weak_evidence:
            continue
        if _boolish(row.get("auto_label_needs_review")) and not include_review_needed:
            continue
        included.append(row)
    return included


def _threshold_sensitivity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sensitivity_rows: list[dict[str, Any]] = []
    total = len(rows)
    for threshold in THRESHOLDS:
        strict_rows = _threshold_rows_for_mode(
            rows,
            threshold=threshold,
            include_review_needed=False,
            include_weak_evidence=False,
        )
        with_review_rows = _threshold_rows_for_mode(
            rows,
            threshold=threshold,
            include_review_needed=True,
            include_weak_evidence=False,
        )
        with_weak_rows = _threshold_rows_for_mode(
            rows,
            threshold=threshold,
            include_review_needed=False,
            include_weak_evidence=True,
        )
        sensitivity_rows.append(
            {
                "min_confidence": f"{threshold:.2f}",
                "included_strict_count": len(strict_rows),
                "included_with_review_count": len(with_review_rows),
                "included_with_weak_evidence_count": len(with_weak_rows),
                "excluded_count": total - len(strict_rows),
                "unique_ticker_count": len(
                    {_clean(row.get("ticker")).upper() for row in strict_rows if _clean(row.get("ticker"))}
                ),
                "unique_creator_count": len(
                    {_clean(row.get("creator")) for row in strict_rows if _clean(row.get("creator"))}
                ),
            }
        )
    return sensitivity_rows


def _write_threshold_summary(
    path: Path,
    *,
    input_path: Path,
    csv_path: Path,
    rows: list[dict[str, Any]],
    sensitivity_rows: list[dict[str, Any]],
) -> Path:
    lines = [
        "# Clean Event Threshold Sensitivity",
        "",
        f"- Source auto-labeled validation file: `{input_path}`",
        f"- CSV output: `{csv_path}`",
        f"- Total auto-labeled rows: {len(rows)}",
        "",
        "| Min confidence | Strict included | With review | With weak evidence | Excluded | Unique tickers | Unique creators |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sensitivity_rows:
        lines.append(
            "| "
            f"{row['min_confidence']} | "
            f"{row['included_strict_count']} | "
            f"{row['included_with_review_count']} | "
            f"{row['included_with_weak_evidence_count']} | "
            f"{row['excluded_count']} | "
            f"{row['unique_ticker_count']} | "
            f"{row['unique_creator_count']} |"
        )
    lines.extend(
        [
            "",
            "Strict included rows require `is_true_recommendation=yes`, direction not `unclear`, "
            "strong or medium evidence, `auto_label_needs_review=false`, and confidence at or "
            "above the threshold.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_clean_event_threshold_sensitivity(
    *,
    input_path: Path = DEFAULT_AUTO_LABELED_INPUT_PATH,
    csv_path: Path = DEFAULT_THRESHOLD_SENSITIVITY_CSV_PATH,
    markdown_path: Path = DEFAULT_THRESHOLD_SENSITIVITY_MD_PATH,
) -> ThresholdSensitivityResult:
    if not input_path.exists():
        raise FileNotFoundError(f"Auto-labeled validation input not found: {input_path}")
    ensure_data_dirs()
    rows = _read_csv(input_path)
    sensitivity_rows = _threshold_sensitivity_rows(rows)
    _write_csv(csv_path, sensitivity_rows, THRESHOLD_SENSITIVITY_COLUMNS)
    _write_threshold_summary(
        markdown_path,
        input_path=input_path,
        csv_path=csv_path,
        rows=rows,
        sensitivity_rows=sensitivity_rows,
    )
    return ThresholdSensitivityResult(
        csv_path=csv_path,
        markdown_path=markdown_path,
        total_rows=len(rows),
        threshold_rows=len(sensitivity_rows),
    )
