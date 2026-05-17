"""Shared helpers for conservative public-news confound layers."""

from __future__ import annotations

import json
import math
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

try:
    from scripts import information_environment_utils as ie
except ModuleNotFoundError:  # pragma: no cover - script execution path
    import information_environment_utils as ie

USER_AGENT = "FIN496 public news confound layer/1.0"
DATE_COLUMNS = ("published_at", "publishedDate", "date", "datetime", "time_published", "published")
MATERIAL_TERMS = (
    "earnings",
    "eps",
    "revenue",
    "guidance",
    "forecast",
    "8-k",
    "10-q",
    "10-k",
    "6-k",
    "20-f",
    "merger",
    "acquisition",
    "lawsuit",
    "settlement",
    "investigation",
    "regulator",
    "sec",
    "fda",
    "product",
    "launch",
    "recall",
    "contract",
    "partnership",
)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=False)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(parsed):
        return None
    if hasattr(parsed, "date"):
        return parsed.date()
    return None


def compact_text(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def bool_series(frame: pd.DataFrame, col: str, default: bool = False) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index)
    return frame[col].astype(str).str.lower().isin({"true", "1", "yes"})


def load_credential(name: str) -> tuple[str | None, str]:
    return ie.load_api_key(name)


def window_bounds(event_date: date, days: int) -> tuple[str, str]:
    return (event_date - timedelta(days=days)).isoformat(), (event_date + timedelta(days=days)).isoformat()


def event_window_counts(article_dates: list[date], event_date: date, days: int) -> tuple[int, int]:
    pre = 0
    post = 0
    for item_date in article_dates:
        delta = (item_date - event_date).days
        if -days <= delta < 0:
            pre += 1
        elif 0 <= delta <= days:
            post += 1
    return pre, post


def title_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("title"),
        item.get("headline"),
        item.get("summary"),
        item.get("description"),
        item.get("text"),
    ]
    return compact_text(" ".join(str(p or "") for p in parts), 500)


def first_item_date(item: dict[str, Any]) -> date | None:
    for col in DATE_COLUMNS:
        parsed = parse_date(item.get(col))
        if parsed is not None:
            return parsed
    return None


def company_terms(company_name: Any) -> set[str]:
    text = re.sub(r"[^A-Za-z0-9 ]", " ", str(company_name or "").lower())
    stop = {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "limited",
        "plc",
        "holdings",
        "class",
        "common",
        "stock",
    }
    return {part for part in text.split() if len(part) >= 4 and part not in stop}


def relevant_item(item: dict[str, Any], ticker: str, company_name: str) -> bool:
    text = title_text(item).lower()
    ticker_l = str(ticker or "").lower()
    if ticker_l and re.search(rf"(?<![a-z0-9]){re.escape(ticker_l)}(?![a-z0-9])", text):
        return True
    terms = company_terms(company_name)
    return bool(terms and any(term in text for term in terms))


def material_item(item: dict[str, Any]) -> bool:
    text = title_text(item).lower()
    return any(term in text for term in MATERIAL_TERMS)


def query_json(
    url: str,
    params: dict[str, Any],
    *,
    timeout: int = 30,
    pause_after_429: float = 2.0,
) -> tuple[str, Any | None, str]:
    try:
        response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        return "request_failed", None, compact_text(type(exc).__name__, 80)
    if response.status_code == 429:
        time.sleep(pause_after_429)
        return "rate_limited", None, "http_429"
    if response.status_code != 200:
        return f"http_{response.status_code}", None, compact_text(response.text, 180)
    try:
        return "ok", response.json(), ""
    except json.JSONDecodeError:
        return "parse_error", None, compact_text(response.text, 180)


def payload_items(payload: Any, candidates: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def compact_provider_result(
    provider: str,
    event: pd.Series,
    status: str,
    items: list[dict[str, Any]],
    *,
    error_class: str = "",
) -> dict[str, Any]:
    event_date = parse_date(event.get("event_date"))
    relevant_dates: list[date] = []
    material_hit = False
    if event_date is not None and status == "ok":
        start = event_date - timedelta(days=7)
        end = event_date + timedelta(days=7)
        for item in items:
            item_date = first_item_date(item)
            if item_date is None or item_date < start or item_date > end:
                continue
            if not relevant_item(item, str(event.get("ticker", "")), str(event.get("company_name", ""))):
                continue
            relevant_dates.append(item_date)
            material_hit = material_hit or material_item(item)
    counts: dict[str, int] = {}
    if event_date is not None:
        for days in (1, 3, 7):
            pre, post = event_window_counts(relevant_dates, event_date, days)
            counts[f"pre_{days}d_count"] = pre
            counts[f"post_{days}d_count"] = post
    total_count = len(relevant_dates)
    return {
        "provider": provider,
        "event_id": int(event.get("event_id")),
        "ticker": event.get("ticker", ""),
        "event_date": event.get("event_date", ""),
        "query_status": status,
        "provider_success": status == "ok",
        "provider_hit": total_count > 0,
        "provider_material_hit": material_hit,
        "relevant_count_pm7": total_count,
        "error_class_safe": compact_text(error_class, 80),
        **counts,
    }


def normal_p_value(t_stat: float | None) -> float | None:
    if t_stat is None or math.isnan(t_stat):
        return None
    return 2.0 * (1.0 - (0.5 * (1.0 + math.erf(abs(t_stat) / math.sqrt(2.0)))))
