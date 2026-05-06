from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import requests

from .config import RAW_X_COUNTS_DIR, get_settings
from .db import connect, init_db
from .utils import get_logger, slugify, utc_now_iso

X_COUNTS_ALL_URL = "https://api.x.com/2/tweets/counts/all"

logger = get_logger(__name__)


class XCountsAccessError(RuntimeError):
    """Raised when the X counts endpoint is unavailable for the current account."""


@dataclass(frozen=True)
class XCountResult:
    query: str
    start_date: str
    end_date: str
    granularity: str
    total_tweet_count: int
    period_counts: list[dict[str, Any]]


def x_stockpick_query(handle: str) -> str:
    return (
        f"from:{handle} "
        '(has:cashtags OR buy OR buying OR bought OR long OR short OR sell OR selling OR '
        'watchlist OR undervalued OR overvalued OR "price target" OR PT OR calls OR puts OR '
        "bullish OR bearish OR multibagger OR 10x) "
        "lang:en -is:retweet"
    )


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _iso_start(value: date) -> str:
    return datetime.combine(value, time.min).isoformat(timespec="seconds") + "Z"


def _month_periods(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = _parse_date(start_date)
    final_exclusive = _parse_date(end_date) + timedelta(days=1)
    periods: list[tuple[str, str]] = []
    current = start
    while current < final_exclusive:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        period_end = min(next_month, final_exclusive)
        periods.append((_iso_start(current), _iso_start(period_end)))
        current = period_end
    return periods


def _save_counts_raw(prefix: str, payload: dict[str, Any]) -> Path:
    RAW_X_COUNTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_X_COUNTS_DIR / f"{utc_now_iso().replace(':', '').replace('-', '')}_{slugify(prefix)}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def parse_counts_response(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    periods = payload.get("data") or []
    total = payload.get("meta", {}).get("total_tweet_count")
    if total is None:
        total = sum(int(period.get("tweet_count", 0)) for period in periods)
    normalized = [
        {
            "start": period.get("start"),
            "end": period.get("end"),
            "tweet_count": int(period.get("tweet_count", 0)),
        }
        for period in periods
    ]
    return int(total or 0), normalized


def _request_count(query: str, start_time: str, end_time: str, granularity: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.x_bearer_token:
        logger.warning("Skipping X counts request because X_BEARER_TOKEN is not set.")
        return None
    session = requests.Session()
    response = session.get(
        X_COUNTS_ALL_URL,
        headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
        params={
            "query": query,
            "start_time": start_time,
            "end_time": end_time,
            "granularity": granularity,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text[:500]}
        _save_counts_raw(
            "counts_error",
            {
                "endpoint": X_COUNTS_ALL_URL,
                "status_code": response.status_code,
                "query": query,
                "start_time": start_time,
                "end_time": end_time,
                "response": payload,
            },
        )
        raise XCountsAccessError(
            "X counts request failed before paid post retrieval. "
            "This usually means the X account lacks full-archive counts access, "
            "payment setup, or the requested endpoint is unavailable. "
            f"HTTP status={response.status_code}; response={payload}"
        )
    return response.json()


def count_x_query(
    query: str,
    start_date: str,
    end_date: str,
    granularity: str = "month",
    handle: str | None = None,
) -> XCountResult:
    init_db()
    raw_payloads: list[dict[str, Any]] = []
    period_counts: list[dict[str, Any]] = []

    if granularity == "month":
        for period_start, period_end in _month_periods(start_date, end_date):
            payload = _request_count(query, period_start, period_end, "day")
            if not payload:
                continue
            raw_payloads.append(payload)
            total, _periods = parse_counts_response(payload)
            period_counts.append(
                {"start": period_start, "end": period_end, "tweet_count": total}
            )
    else:
        payload = _request_count(query, _iso_start(_parse_date(start_date)), _iso_start(_parse_date(end_date) + timedelta(days=1)), granularity)
        if payload:
            raw_payloads.append(payload)
            _, period_counts = parse_counts_response(payload)

    combined_payload = {
        "query": query,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
        "responses": raw_payloads,
    }
    _save_counts_raw(f"counts_{handle or 'query'}", combined_payload)
    total_tweet_count = sum(int(period.get("tweet_count", 0)) for period in period_counts)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO x_query_counts (
              query, handle, start_date, end_date, granularity,
              total_tweet_count, period_counts_json, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query,
                handle,
                start_date,
                end_date,
                granularity,
                total_tweet_count,
                json.dumps(period_counts, sort_keys=True),
                json.dumps(combined_payload, sort_keys=True),
            ),
        )
        conn.commit()
    return XCountResult(
        query=query,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        total_tweet_count=total_tweet_count,
        period_counts=period_counts,
    )


def count_x_creator_stockpick_posts(
    handle: str,
    start_date: str,
    end_date: str,
) -> XCountResult:
    return count_x_query(
        x_stockpick_query(handle),
        start_date,
        end_date,
        granularity="month",
        handle=handle,
    )
