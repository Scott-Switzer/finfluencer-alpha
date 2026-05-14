#!/usr/bin/env python3
"""Checkpoint 1: X-native creator + YouTube-event windows (Kaito, bounded session spend).

Run on RunPod with:
  export X_APIFY_SKIP_RAW_ITEM_SAVE=1
  export APIFY_SESSION_MAX_TOTAL_USD=1.25
  cd /workspace/FIN496CAPSTONE && PYTHONPATH=src python3 scripts/x_native_creator_checkpoint_1.py

Prints JSON summary only (no tweet bodies, no tokens).
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.chdir(ROOT)
os.environ.setdefault("X_APIFY_SKIP_RAW_ITEM_SAVE", "1")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=False)

from finfluencer_alpha.apify_key_manager import ApifyKeyManager  # noqa: E402
from finfluencer_alpha.config import PROJECT_ROOT  # noqa: E402
from finfluencer_alpha.x_youtube_pipeline import (  # noqa: E402
    _date_window_unix_bounds,
    run_single_x_apify_source,
)

ACTOR = "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest"

CHANNEL_X: list[tuple[str, str]] = [
    ("plain bagel", "ThePlainBagel"),
    ("graham", "GrahamStephan"),
    ("meet kevin", "realMeetKevin"),
    ("everything money", "EverythingMoney"),
    ("stock moe", "StockMoe"),
    ("unusual whales", "unusual_whales"),
    ("kobeissi", "KobeissiLetter"),
    ("zerohedge", "zerohedge"),
    ("wsb", "TheRoaringKitty"),
]

GLOB_PATTERNS = [
    "data/exports/research_expansion/all_clean_events.csv",
    "data/exports/validation/clean_auto_labeled_events.csv",
    "data/exports/**/clean*event*.csv",
    "data/exports/**/accepted*event*.csv",
    "data/exports/**/event_study*.csv",
    "data/exports/**/recommendation*event*.csv",
]


def resolve_x_handle(creator: str) -> str | None:
    lower = creator.lower()
    for needle, handle in CHANNEL_X:
        if needle in lower:
            return handle
    return None


def window_around(event_date: str, before: int = 3, after: int = 3) -> tuple[str, str]:
    base = datetime.strptime(event_date[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    start = (base - timedelta(days=before)).strftime("%Y-%m-%d")
    end = (base + timedelta(days=after)).strftime("%Y-%m-%d")
    return start, end


def _first_existing_csv() -> Path | None:
    for pattern in GLOB_PATTERNS:
        if "**" in pattern:
            matches = sorted(glob.glob(str(PROJECT_ROOT / pattern), recursive=True))
            for path in matches:
                p = Path(path)
                if p.is_file() and p.suffix.lower() == ".csv" and "exclusion" not in p.name.lower():
                    return p
        else:
            p = PROJECT_ROOT / pattern
            if p.is_file():
                return p
    return None


def _sqlite_db() -> Path:
    return PROJECT_ROOT / "data" / "finfluencer_alpha.db"


def _events_from_sqlite(db: Path, limit: int) -> tuple[str, list[dict[str, str]]]:
    if not db.is_file():
        return "sqlite_missing", []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "transcript_recommendation_events" not in tables or "raw_youtube_videos" not in tables:
        conn.close()
        return "sqlite_schema_incomplete", []
    sql = """
        SELECT CAST(tr.transcript_event_id AS TEXT) AS event_id,
               tr.video_id AS video_id,
               UPPER(TRIM(tr.ticker)) AS ticker,
               SUBSTR(rv.published_at, 1, 10) AS event_date_utc,
               rv.published_at AS published_at,
               rv.channel_title AS creator
        FROM transcript_recommendation_events tr
        JOIN raw_youtube_videos rv ON rv.video_id = tr.video_id
        WHERE tr.ticker IS NOT NULL
          AND TRIM(tr.ticker) != ''
          AND (tr.exclusion_reason IS NULL OR TRIM(tr.exclusion_reason) = '')
        ORDER BY rv.published_at DESC
        LIMIT ?
    """
    rows = [dict(r) for r in cur.execute(sql, (limit,))]
    conn.close()
    return "sqlite_transcript_recommendation_events", rows


def _events_from_csv(path: Path, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for i, event in enumerate(reader):
            if i >= limit:
                break
            out.append({k: (event.get(k) or "").strip() for k in event})
    return out


def discover_events(max_rows: int) -> tuple[str, list[dict[str, str]]]:
    primary = PROJECT_ROOT / "data/exports/research_expansion/all_clean_events.csv"
    if primary.is_file():
        return f"csv:{primary.relative_to(PROJECT_ROOT)}", _events_from_csv(primary, max_rows)
    fallback = _first_existing_csv()
    if fallback is not None:
        return f"csv:{fallback.relative_to(PROJECT_ROOT)}", _events_from_csv(fallback, max_rows)
    label, rows = _events_from_sqlite(_sqlite_db(), max_rows)
    if rows:
        return label, rows
    return "none", []


def main() -> None:
    manager = ApifyKeyManager.from_env()
    manager.begin_session()
    session_cap = manager.budget.session_max_total_usd

    max_charge = float(os.getenv("X_CHECKPOINT_MAX_CHARGE_PER_RUN", "0.06"))
    max_items = int(os.getenv("X_CHECKPOINT_MAX_ITEMS", "35"))
    max_rows = int(os.getenv("X_CHECKPOINT_MAX_RUNS", "18"))

    source_label, events = discover_events(max_rows * 3)
    runs: list[dict[str, object]] = []

    if not events:
        print(
            json.dumps(
                {
                    "error": "no_event_source",
                    "checked_source": source_label,
                    "session_cap_usd": session_cap,
                    "session_spend_usd": round(manager.session_spend_usd, 6),
                },
                indent=2,
            )
        )
        return

    used = 0
    for event in events:
        if used >= max_rows:
            break
        cap = session_cap or 9999.0
        if manager.session_spend_usd >= cap * 0.92:
            break
        ticker = (event.get("ticker") or "").strip().upper()
        event_date = (event.get("event_date_utc") or event.get("published_at") or "")[:10]
        creator = (event.get("creator") or "").strip()
        video_id = (event.get("video_id") or "").strip()
        event_id = (event.get("event_id") or "").strip()
        if not ticker or not re.fullmatch(r"[A-Z]{1,5}", ticker):
            continue
        if not event_date:
            continue
        handle_x = resolve_x_handle(creator)
        ds, de = window_around(event_date, 3, 3)
        since_i, until_i = _date_window_unix_bounds(ds, de)

        if handle_x:
            search_value = f"from:{handle_x} ${ticker}"
            query_type = "x-creator-authored"
        else:
            search_value = f"${ticker}"
            query_type = "ticker-only-control"

        row = run_single_x_apify_source(
            actor_id=ACTOR,
            source_type="search",
            source_value=search_value,
            limit=max_items,
            max_charge_usd=max_charge,
            manager=manager,
        )

        runs.append(
            {
                "event_id": event_id,
                "youtube_creator": creator,
                "youtube_video_id": video_id,
                "ticker": ticker,
                "event_date_utc": event_date,
                "x_handle_target": handle_x or "",
                "query_type": query_type,
                "window_start": ds,
                "window_end": de,
                "since_time": since_i,
                "until_time": until_i,
                "actor": ACTOR,
                "key_label": row.get("key_label"),
                "status": row.get("status"),
                "posts_returned": row.get("posts_returned"),
                "posts_imported": row.get("posts_imported"),
                "posts_with_cashtags": row.get("posts_with_cashtags"),
                "posts_with_created_at": row.get("posts_with_created_at"),
                "usable_finance_posts": row.get("usable_finance_posts"),
                "cost_usd": row.get("cost_usd"),
                "notes": row.get("notes"),
            }
        )
        used += 1

    out = {
        "actor": ACTOR,
        "event_source": source_label,
        "session_cap_usd": session_cap,
        "session_spend_usd": round(manager.session_spend_usd, 6),
        "key_status": manager.session_key_status_summary(),
        "runs": runs,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
