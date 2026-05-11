from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .config import SEEDS_DIR
from .utils import configure_csv_field_size_limit

DEFAULT_TICKER_ALIASES_PATH = SEEDS_DIR / "ticker_aliases.csv"


@dataclass(frozen=True)
class TickerAlias:
    original_ticker: str
    data_ticker: str
    company_name: str
    effective_date: date | None
    reason: str


def _clean(value: object) -> str:
    return str(value or "").strip()


def _parse_date(value: object) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid ticker alias effective_date: {text}") from exc


def _parse_event_date(value: object) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_ticker_aliases(path: Path = DEFAULT_TICKER_ALIASES_PATH) -> dict[str, TickerAlias]:
    if not path.exists():
        return {}
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    aliases: dict[str, TickerAlias] = {}
    for row in rows:
        original_ticker = _clean(row.get("original_ticker")).upper()
        data_ticker = _clean(row.get("data_ticker")).upper()
        if not original_ticker or not data_ticker:
            continue
        if original_ticker == data_ticker:
            continue
        alias = TickerAlias(
            original_ticker=original_ticker,
            data_ticker=data_ticker,
            company_name=_clean(row.get("company_name")),
            effective_date=_parse_date(row.get("effective_date")),
            reason=_clean(row.get("reason")),
        )
        aliases[original_ticker] = alias
    return aliases


def resolve_data_ticker(
    original_ticker: str,
    *,
    aliases: dict[str, TickerAlias],
    event_date: object = "",
) -> tuple[str, bool]:
    normalized_ticker = _clean(original_ticker).upper()
    alias = aliases.get(normalized_ticker)
    if alias is None:
        return normalized_ticker, False
    event_day = _parse_event_date(event_date)
    if alias.effective_date is not None and event_day is not None and event_day < alias.effective_date:
        return normalized_ticker, False
    return alias.data_ticker, True
