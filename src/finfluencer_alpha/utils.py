from __future__ import annotations

import csv
import json
import logging
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import RAW_X_DIR, RAW_YOUTUBE_DIR, ensure_data_dirs

LOGGER_NAME = "finfluencer_alpha"


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name or LOGGER_NAME)


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str, max_len: int = 80) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("_")[:max_len] or "payload"


def save_raw_json(platform: str, prefix: str, payload: dict[str, Any]) -> Path:
    ensure_data_dirs()
    base_dir = RAW_X_DIR if platform == "x" else RAW_YOUTUBE_DIR
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = base_dir / f"{stamp}_{slugify(prefix)}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def request_json(
    session: Any,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
    max_retries: int = 2,
) -> dict[str, Any] | None:
    logger = get_logger()
    for attempt in range(max_retries + 1):
        response = session.get(url, headers=headers, params=params, timeout=timeout)
        if response.status_code == 429 and attempt < max_retries:
            retry_after = int(response.headers.get("retry-after", "60"))
            logger.warning("Rate limited by API. Sleeping for %s seconds.", retry_after)
            time.sleep(retry_after)
            continue
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {"error": response.text[:500]}
            logger.warning("API request failed with status %s: %s", response.status_code, payload)
            return None
        return response.json()
    return None


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def configure_csv_field_size_limit() -> int:
    """Raise csv's parser field limit for large transcript text fields."""
    limit = sys.maxsize
    while limit > 0:
        try:
            csv.field_size_limit(limit)
            return limit
        except OverflowError:
            limit //= 10
    csv.field_size_limit()
    return csv.field_size_limit()
