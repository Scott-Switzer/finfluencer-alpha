#!/usr/bin/env python3
"""Checkpoint 1: X-native creator + YouTube-event windows (Kaito, bounded session spend).

Run on RunPod with:
  export X_APIFY_SKIP_RAW_ITEM_SAVE=1
  export APIFY_SESSION_MAX_TOTAL_USD=1.25
  cd /workspace/FIN496CAPSTONE && PYTHONPATH=src python3 scripts/x_native_creator_checkpoint_1.py

Dry-run candidate plan (no Apify):
  PYTHONPATH=src X_CHECKPOINT_DRY_RUN=1 X_CHECKPOINT_DISCOVERY_POOL_SIZE=5000 \\
    python3 scripts/x_native_creator_checkpoint_1.py

Prints JSON summary only (no tweet bodies, no tokens).
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
    summarize_apify_checkpoint_items,
)

ACTOR = "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest"

# Substring needles (YouTube channel / display title) -> canonical X handle for `from:` search.
# Do not add guessed handles; update `data/exports/overnight_collection/34_x_creator_mapping_gap_audit.md`
# when extending this list.
CHANNEL_X: list[tuple[str, str]] = [
    ("plain bagel", "ThePlainBagel"),
    ("graham", "GrahamStephan"),
    ("meet kevin", "realMeetKevin"),
    ("everything money", "EverythingMoney"),
    ("stock moe", "StockMoe"),
    ("unusual whales", "unusual_whales"),
    ("kobeissi", "KobeissiLetter"),
    ("zerohedge", "zerohedge"),
]

# Audited X-native finance panel (not tied to a specific YouTube row). Used only when
# creator-authored and conservative mention queries are unavailable. Mirrors
# `29_x_native_creator_panel_audit.md` handles marked checkpoint-friendly; excludes
# weak / meme-only accounts.
CREATOR_PANEL_HANDLES: tuple[str, ...] = (
    "GrahamStephan",
    "realMeetKevin",
    "EverythingMoney",
    "ThePlainBagel",
    "StockMoe",
    "unusual_whales",
    "KobeissiLetter",
    "zerohedge",
)

GLOB_PATTERNS = [
    "data/exports/research_expansion/all_clean_events.csv",
    "data/exports/validation/clean_auto_labeled_events.csv",
    "data/exports/**/clean*event*.csv",
    "data/exports/**/accepted*event*.csv",
    "data/exports/**/event_study*.csv",
    "data/exports/**/recommendation*event*.csv",
]

DEBUG_MD_PATH = PROJECT_ROOT / "data/exports/overnight_collection/35_x_checkpoint_zero_import_debug.md"

_DIAGNOSTIC_FIXTURE_ITEMS: list[dict[str, Any]] = [
    {},
    {"text": "", "id": "1", "created_at": "2024-01-02T12:00:00Z", "lang": "en"},
    {"text": "Hello", "id": "", "created_at": "2024-01-02T12:00:00Z", "lang": "en"},
    {"text": "Hello", "id": "9", "lang": "en"},
    {"text": "Hello", "id": "10", "created_at": "not-a-date", "lang": "en"},
    {"text": "こんにちは", "id": "11", "created_at": "2024-01-02T12:00:00Z", "lang": "ja"},
    {
        "text": "Random weather today",
        "id": "12",
        "created_at": "2024-01-02T12:00:00Z",
        "lang": "en",
    },
    {
        "text": "Buying $NVDA here",
        "id": "13",
        "created_at": "2024-01-02T12:00:00Z",
        "lang": "en",
    },
    {
        "type": "mock_tweet",
        "id": -1,
        "text": "Pricing placeholder (not a real tweet).",
        "lang": "en",
    },
]


def _truthy_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def discovery_pool_size() -> int:
    """Rows to read from CSV / SQLite before filtering. <= 0 means read entire CSV (no row cap)."""
    raw = os.getenv("X_CHECKPOINT_DISCOVERY_POOL_SIZE", "5000").strip()
    if not raw:
        return 5000
    return int(raw)


def resolve_x_handle(creator: str) -> str | None:
    lower = creator.lower()
    for needle, handle in CHANNEL_X:
        if needle in lower:
            return handle
    return None


_CREDENTIAL_TAIL = re.compile(
    r"\b(cfa|cpa|c\.p\.a\.|ph\.?d\.?|md|mba)\b\.?$",
    re.IGNORECASE,
)


def mention_phrase_for_search(creator: str) -> str | None:
    """Build a short quoted-phrase candidate for X search; None if too ambiguous."""
    raw = (creator or "").strip()
    if not raw:
        return None
    base = raw.split(",")[0].strip()
    base = _CREDENTIAL_TAIL.sub("", base).strip()
    if not base:
        return None
    if any(ch in base for ch in "<>\"\\"):
        return None
    tokens = base.split()
    if len(tokens) < 2:
        return None
    tokens = tokens[:4]
    phrase = " ".join(tokens)
    if len(phrase) < 4:
        return None
    return phrase


def creator_mention_search(creator: str, ticker: str) -> str | None:
    phrase = mention_phrase_for_search(creator)
    if not phrase:
        return None
    escaped = phrase.replace('"', "")
    if not escaped.strip():
        return None
    return f'"{escaped}" ${ticker}'


def panel_handle_for_event(event_id: str, creator: str, ticker: str) -> str:
    seed = (event_id or "") + "|" + creator + "|" + ticker
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:12], 16) % len(CREATOR_PANEL_HANDLES)
    return CREATOR_PANEL_HANDLES[idx]


def choose_checkpoint_query(
    creator: str,
    ticker: str,
    *,
    event_id: str,
    mention_enabled: bool,
    panel_enabled: bool,
) -> tuple[str, str, str]:
    """Return (search_value, query_type, x_handle_target_for_audit).

    Priority:
      1) x-creator-authored — mapped YouTube -> X handle
      2) x-creator-mentioned — quoted display phrase + cashtag (diagnostic)
      3) x-creator-panel — audited panel handle + cashtag (not the YouTube author)
      4) ticker-only-control — cashtag-only labeled control
    """
    handle = resolve_x_handle(creator)
    if handle:
        return f"from:{handle} ${ticker}", "x-creator-authored", handle

    if mention_enabled:
        mention = creator_mention_search(creator, ticker)
        if mention:
            return mention, "x-creator-mentioned", ""

    if panel_enabled:
        panel_h = panel_handle_for_event(event_id, creator, ticker)
        return f"from:{panel_h} ${ticker}", "x-creator-panel", panel_h

    return f"${ticker}", "ticker-only-control", ""


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
    cap = max(1, min(limit, 2_000_000))
    rows = [dict(r) for r in cur.execute(sql, (cap,))]
    conn.close()
    return "sqlite_transcript_recommendation_events", rows


def _events_from_csv(path: Path, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    unlimited = limit <= 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for i, event in enumerate(reader):
            if not unlimited and i >= limit:
                break
            out.append({k: (event.get(k) or "").strip() for k in event})
    return out


def discover_events(pool_size: int) -> tuple[str, list[dict[str, str]]]:
    """Load up to *pool_size* rows (or entire CSV when pool_size <= 0) from the preferred source."""
    primary = PROJECT_ROOT / "data/exports/research_expansion/all_clean_events.csv"
    if primary.is_file():
        limit = pool_size if pool_size > 0 else 0
        return f"csv:{primary.relative_to(PROJECT_ROOT)}", _events_from_csv(primary, limit)
    fallback = _first_existing_csv()
    if fallback is not None:
        limit = pool_size if pool_size > 0 else 0
        return f"csv:{fallback.relative_to(PROJECT_ROOT)}", _events_from_csv(fallback, limit)
    sqlite_limit = pool_size if pool_size > 0 else 500_000
    label, rows = _events_from_sqlite(_sqlite_db(), sqlite_limit)
    if rows:
        return label, rows
    return "none", []


def _event_sort_key(event: dict[str, str]) -> tuple[int, str]:
    creator = (event.get("creator") or "").strip()
    mapped = 0 if resolve_x_handle(creator) else 1
    date_key = (event.get("event_date_utc") or event.get("published_at") or "")[:10]
    eid = (event.get("event_id") or "").strip()
    return mapped, f"{date_key}|{eid}"


def prioritize_checkpoint_events(events: list[dict[str, str]]) -> list[dict[str, str]]:
    """Prefer rows with a CHANNEL_X mapping so capped runs exercise `from:` queries first."""
    return sorted(events, key=_event_sort_key)


def event_row_valid(event: dict[str, str]) -> bool:
    ticker = (event.get("ticker") or "").strip().upper()
    event_date = (event.get("event_date_utc") or event.get("published_at") or "")[:10]
    if not ticker or not re.fullmatch(r"[A-Z]{1,5}", ticker):
        return False
    if not event_date:
        return False
    return True


def select_checkpoint_candidates(
    events: list[dict[str, str]],
    *,
    max_runs: int,
    require_mapped_for_pool: bool,
    mention_enabled: bool,
    panel_enabled: bool,
) -> list[dict[str, Any]]:
    """Filter, prioritize, then take up to *max_runs* eligible events with planned queries."""
    valid = [e for e in events if event_row_valid(e)]
    if require_mapped_for_pool:
        valid = [e for e in valid if resolve_x_handle((e.get("creator") or "").strip())]
    ordered = prioritize_checkpoint_events(valid)
    chosen: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for event in ordered:
        if len(chosen) >= max_runs:
            break
        creator = (event.get("creator") or "").strip()
        ticker = (event.get("ticker") or "").strip().upper()
        event_id = (event.get("event_id") or "").strip()
        event_date = (event.get("event_date_utc") or event.get("published_at") or "")[:10]
        ds, de = window_around(event_date, 3, 3)
        search_value, query_type, x_handle_target = choose_checkpoint_query(
            creator,
            ticker,
            event_id=event_id,
            mention_enabled=mention_enabled,
            panel_enabled=panel_enabled,
        )
        dedupe_key = (search_value, ds, de)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        chosen.append(event)

    out: list[dict[str, Any]] = []
    for event in chosen:
        creator = (event.get("creator") or "").strip()
        ticker = (event.get("ticker") or "").strip().upper()
        event_id = (event.get("event_id") or "").strip()
        event_date = (event.get("event_date_utc") or event.get("published_at") or "")[:10]
        ds, de = window_around(event_date, 3, 3)
        since_i, until_i = _date_window_unix_bounds(ds, de)
        search_value, query_type, x_handle_target = choose_checkpoint_query(
            creator,
            ticker,
            event_id=event_id,
            mention_enabled=mention_enabled,
            panel_enabled=panel_enabled,
        )
        out.append(
            {
                "event_id": event_id,
                "youtube_creator": creator,
                "youtube_video_id": (event.get("video_id") or "").strip(),
                "ticker": ticker,
                "event_date_utc": event_date,
                "window_start": ds,
                "window_end": de,
                "since_time": since_i,
                "until_time": until_i,
                "x_handle_target": x_handle_target,
                "query_type": query_type,
                "search_value": search_value,
            }
        )
    return out


def build_dry_run_report(
    source_label: str,
    events: list[dict[str, str]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    valid = [e for e in events if event_row_valid(e)]
    mapped_valid = sum(1 for e in valid if resolve_x_handle((e.get("creator") or "").strip()))
    qt = Counter(c["query_type"] for c in candidates)
    authored_selected = sum(1 for c in candidates if c["query_type"] == "x-creator-authored")
    creators = list({c["youtube_creator"] for c in candidates})
    tickers = list({c["ticker"] for c in candidates})
    preview = candidates[:20]
    return {
        "dry_run": True,
        "event_source": source_label,
        "total_event_rows_loaded": len(events),
        "discovery_pool_size_effective": len(events),
        "valid_event_rows": len(valid),
        "mapped_event_count_in_valid": mapped_valid,
        "unmapped_event_count_in_valid": len(valid) - mapped_valid,
        "final_selected_run_count": len(candidates),
        "selected_distinct_creators": creators,
        "selected_distinct_tickers": tickers,
        "query_type_counts": dict(qt),
        "x_creator_authored_candidates_in_valid_pool": mapped_valid,
        "x_creator_authored_in_selected_runs": authored_selected,
        "top_20_selected_candidates": preview,
    }


def render_zero_import_debug_markdown(
    *,
    dry_run_report: dict[str, Any] | None,
    fixture_summary: dict[str, Any],
) -> str:
    lines = [
        "# X checkpoint zero-import and normalization diagnostics",
        "",
        "Generated for engineering audit (no secrets, no raw tweet bodies).",
        "",
        "## Executive summary",
        "",
        "- The **2026-05-14** capped smoke run (**255** returned, **0** imported) was **not** a data success: it exposed (1) **candidate truncation** when only the CSV head was considered before sorting, and (2) a **normalization / finance gate** path where items can return from Apify yet never reach `import_normalized_x_posts`.",
        "- **RunPod follow-up (`9c78f0d` / `19c853b`):** candidate selection is **fixed** (e.g. **18** `x-creator-authored` runs in dry-run), but a **0.50 USD** capped paid batch still showed **270 returned / 0 imported** with **zero** `posts_with_cashtags` / `posts_with_created_at` counter movement.",
        "- **Root cause (replay):** Apify dataset rows for those runs were **`type: mock_tweet`** placeholders (e.g. pricing / quota messaging, **`id: -1`**, no parseable tweet timestamps) — **not real X payloads**. Normalization correctly drops them; **field-alias tweaks alone cannot import mocks.** Hold **paid** Apify until datasets contain real tweets (billing / product / quota on the Kaito actor side).",
        "- **No larger X spend** is justified until **dry-run** stays healthy **and** a **dataset replay** shows at least one row that **`normalize_apify_x_post`** can turn into a real post with cashtag + `created_at` in-window.",
        "- **Search-plan dedupe:** identical **`(search_value, window_start, window_end)`** combinations are skipped so capped runs are not wasted on duplicate Apify calls.",
        "",
        "## Pipeline reminder (`run_single_x_apify_source`)",
        "",
        "1. `normalize_apify_x_post` must return a dict (post id, text, parseable `created_at`, English, etc.). Placeholder **`type: mock_tweet`** rows are rejected early.",
        "2. Only posts passing `_is_usable_finance_post` (explicit tickers / finance vocabulary) are appended to the `normalized` list.",
        "3. `import_normalized_x_posts` runs on that list; strict cashtag seeding can drop recommendation rows even when posts insert.",
        "",
        "## Fixture batch (offline)",
        "",
        "Synthetic items exercised `diagnose_apify_x_item_quality` / `summarize_apify_checkpoint_items` without Apify:",
        "",
        "```json",
        json.dumps(fixture_summary, indent=2),
        "```",
        "",
    ]
    if dry_run_report is not None:
        lines.extend(
            [
                "## Latest dry-run candidate plan",
                "",
                "```json",
                json.dumps(dry_run_report, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def write_zero_import_audit_file(
    *,
    dry_run_report: dict[str, Any] | None,
    fixture_summary: dict[str, Any],
) -> None:
    DEBUG_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEBUG_MD_PATH.write_text(
        render_zero_import_debug_markdown(dry_run_report=dry_run_report, fixture_summary=fixture_summary),
        encoding="utf-8",
    )


def fixture_diagnostic_summary() -> dict[str, Any]:
    since, until = _date_window_unix_bounds("2024-01-01", "2024-01-10")
    return summarize_apify_checkpoint_items(
        _DIAGNOSTIC_FIXTURE_ITEMS,
        expected_ticker="NVDA",
        window_start_unix=since,
        window_end_unix=until,
    )


def main() -> None:
    pool_size = discovery_pool_size()
    max_charge = float(os.getenv("X_CHECKPOINT_MAX_CHARGE_PER_RUN", "0.06"))
    max_items = int(os.getenv("X_CHECKPOINT_MAX_ITEMS", "35"))
    max_rows = int(os.getenv("X_CHECKPOINT_MAX_RUNS", "18"))

    mention_enabled = not _truthy_env("X_CHECKPOINT_DISABLE_MENTION", default=False)
    panel_enabled = not _truthy_env("X_CHECKPOINT_DISABLE_PANEL", default=False)
    require_mapped = _truthy_env("X_CHECKPOINT_REQUIRE_MAPPED_FOR_AUTHORED", default=False)

    source_label, events = discover_events(pool_size)
    candidates = select_checkpoint_candidates(
        events,
        max_runs=max_rows,
        require_mapped_for_pool=require_mapped,
        mention_enabled=mention_enabled,
        panel_enabled=panel_enabled,
    )

    fixture_summary = fixture_diagnostic_summary()

    if _truthy_env("X_CHECKPOINT_DRY_RUN", default=False):
        report = build_dry_run_report(source_label, events, candidates)
        report["mention_tier_enabled"] = mention_enabled
        report["panel_tier_enabled"] = panel_enabled
        report["require_mapped_for_pool"] = require_mapped
        if _truthy_env("X_CHECKPOINT_WRITE_DEBUG_MD", default=True):
            write_zero_import_audit_file(dry_run_report=report, fixture_summary=fixture_summary)
        print(json.dumps(report, indent=2))
        return

    manager = ApifyKeyManager.from_env()
    manager.begin_session()
    session_cap = manager.budget.session_max_total_usd

    runs: list[dict[str, object]] = []

    if not candidates:
        print(
            json.dumps(
                {
                    "error": "no_candidates",
                    "checked_source": source_label,
                    "session_cap_usd": session_cap,
                    "session_spend_usd": round(manager.session_spend_usd, 6),
                    "total_event_rows_loaded": len(events),
                },
                indent=2,
            )
        )
        return

    for row in candidates:
        cap = session_cap or 9999.0
        if manager.session_spend_usd >= cap * 0.92:
            break
        apify_row = run_single_x_apify_source(
            actor_id=ACTOR,
            source_type="search",
            source_value=row["search_value"],
            limit=max_items,
            max_charge_usd=max_charge,
            manager=manager,
            date_start=row["window_start"],
            date_end=row["window_end"],
        )
        runs.append(
            {
                **row,
                "actor": ACTOR,
                "key_label": apify_row.get("key_label"),
                "status": apify_row.get("status"),
                "posts_returned": apify_row.get("posts_returned"),
                "posts_imported": apify_row.get("posts_imported"),
                "posts_with_cashtags": apify_row.get("posts_with_cashtags"),
                "posts_with_created_at": apify_row.get("posts_with_created_at"),
                "usable_finance_posts": apify_row.get("usable_finance_posts"),
                "cost_usd": apify_row.get("cost_usd"),
                "notes": apify_row.get("notes"),
            }
        )

    out = {
        "actor": ACTOR,
        "event_source": source_label,
        "discovery_pool_size_requested": pool_size,
        "total_event_rows_loaded": len(events),
        "session_cap_usd": session_cap,
        "session_spend_usd": round(manager.session_spend_usd, 6),
        "mention_tier_enabled": mention_enabled,
        "panel_tier_enabled": panel_enabled,
        "require_mapped_for_pool": require_mapped,
        "key_status": manager.session_key_status_summary(),
        "runs": runs,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
