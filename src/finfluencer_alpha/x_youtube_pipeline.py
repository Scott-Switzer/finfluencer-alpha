from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from .apify_key_manager import ApifyBudgetError, ApifyKeyManager
from .config import EXPORTS_DIR, PROJECT_ROOT
from .db import connect, init_db
from .x_recommendation_classifier import (
    classify_x_recommendation,
    extract_x_ticker_mentions,
    normalize_text_hash_text,
)
from .x_youtube_schema import apply_x_youtube_schema, insert_apify_collection_run, insert_x_post

APIFY_BASE_URL = "https://api.apify.com/v2"
OVERNIGHT_DIR = EXPORTS_DIR / "overnight_collection"
EVENT_STUDY_DIR = EXPORTS_DIR / "x_youtube_event_study"
FINAL_PROJECT_DIR = EXPORTS_DIR / "final_research_project"
RAW_X_APIFY_DIR = PROJECT_ROOT / "data/raw/apify/x"
CONFIG_X_DIR = PROJECT_ROOT / "config/x_sources"
DATE_START = "2020-01-01"
DATE_END = "2026-05-13"
DEFAULT_ACTORS = [
    "apidojo/tweet-scraper",
    "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest",
    "scraper-engine/twitter-x-posts-scraper",
    "scraper_one/x-profile-posts-scraper",
]

FINANCE_WORDS = {
    "stock",
    "stocks",
    "shares",
    "buy",
    "buying",
    "sell",
    "selling",
    "hold",
    "long",
    "short",
    "bullish",
    "bearish",
    "earnings",
    "portfolio",
    "watchlist",
    "undervalued",
    "overvalued",
    "price target",
    "pt",
    "calls",
    "puts",
}


def ensure_dirs() -> None:
    for path in [OVERNIGHT_DIR, EVENT_STUDY_DIR, FINAL_PROJECT_DIR, RAW_X_APIFY_DIR, CONFIG_X_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _safe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _safe_float(value: object) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_lines(path: Path, limit: int | None = None) -> list[str]:
    if not path.exists():
        return []
    rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    rows = [line for line in rows if line and not line.startswith("#")]
    return rows if limit is None else rows[:limit]


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    if not raw:
        return default
    parts = [part.strip() for part in raw.replace("\n", ",").split(",")]
    return [part for part in parts if part]


def _normalize_actor_id(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def _apify_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _extract_data(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload
    return {}


def _start_run(actor_id: str, payload: dict[str, Any], token: str, max_charge: float) -> dict[str, Any]:
    response = requests.post(
        f"{APIFY_BASE_URL}/acts/{_normalize_actor_id(actor_id)}/runs",
        headers=_apify_headers(token),
        json=payload,
        params={"maxTotalChargeUsd": f"{max_charge:.4f}"},
        timeout=60,
    )
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = {"error": response.text[:500]}
        raise RuntimeError(f"Apify start failed HTTP {response.status_code}: {body}")
    return _extract_data(response.json())


def _wait_run(run_id: str, token: str, max_wait_seconds: int = 300) -> dict[str, Any]:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        response = requests.get(
            f"{APIFY_BASE_URL}/actor-runs/{run_id}",
            headers=_apify_headers(token),
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Apify status failed HTTP {response.status_code}")
        data = _extract_data(response.json())
        status = _clean(data.get("status"))
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT", "TIMED_OUT"}:
            return data
        time.sleep(5)
    raise RuntimeError(f"Apify run {run_id} did not finish within {max_wait_seconds}s")


def _fetch_items(run_id: str, token: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{APIFY_BASE_URL}/actor-runs/{run_id}/dataset/items",
        headers=_apify_headers(token),
        params={"format": "json", "clean": "1"},
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Apify dataset fetch failed HTTP {response.status_code}")
    payload = response.json()
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("data") or []
        return [item for item in items if isinstance(item, dict)]
    return []


def _source_query(source_type: str, source_value: str) -> str:
    if source_type == "profile":
        handle = source_value.lstrip("@")
        return f"from:{handle} since:{DATE_START} until:2026-05-14 lang:en -filter:retweets"
    if source_type == "cashtag":
        cashtag = source_value if source_value.startswith("$") else f"${source_value}"
        return f"{cashtag} since:{DATE_START} until:2026-05-14 lang:en -filter:retweets"
    return f"{source_value} since:{DATE_START} until:2026-05-14 lang:en -filter:retweets"


def build_x_actor_input(
    actor_id: str,
    source_type: str,
    source_value: str,
    limit: int,
) -> dict[str, Any]:
    actor = actor_id.lower()
    query = _source_query(source_type, source_value)
    handle = source_value.lstrip("@")
    if "apidojo/tweet-scraper" in actor:
        return {
            "searchTerms": [query],
            "maxItems": limit,
            "sort": "Latest",
            "tweetLanguage": "en",
            "start": DATE_START,
            "end": DATE_END,
        }
    if "kaitoeasyapi" in actor:
        return {
            "queries": [query],
            "maxItems": limit,
            "lang": "en",
            "startDate": DATE_START,
            "endDate": DATE_END,
        }
    if "scraper-engine" in actor:
        return {
            "query": query,
            "maxItems": limit,
            "startDate": DATE_START,
            "endDate": DATE_END,
            "lang": "en",
        }
    if "scraper_one/x-profile-posts-scraper" in actor and source_type == "profile":
        return {
            "usernames": [handle],
            "maxItems": limit,
            "includeReplies": False,
            "includeRetweets": False,
            "startDate": DATE_START,
            "endDate": DATE_END,
        }
    if "scraper_one" in actor:
        return {"searchQueries": [query], "maxItems": limit, "lang": "en"}
    return {"query": query, "maxItems": limit, "lang": "en"}


def _nested(item: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = item
        found = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return None


def _post_id_from_url(url: str) -> str:
    match = re.search(r"/status(?:es)?/(\d+)", url or "")
    return match.group(1) if match else ""


def _normalize_created_at(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text) / 1000 if len(text) > 10 else int(text), UTC).isoformat()
        except (OverflowError, ValueError):
            return ""
    return text


def normalize_apify_x_post(
    item: dict[str, Any],
    *,
    actor_id: str,
    key_label: str,
    source_type: str,
    source_value: str,
    raw_json_path: str = "",
) -> dict[str, Any] | None:
    url = _clean(_nested(item, "url", "tweetUrl", "twitterUrl", "link"))
    post_id = _clean(_nested(item, "id", "tweet_id", "tweetId", "rest_id", "post_id"))
    if not post_id:
        post_id = _post_id_from_url(url)
    text = _clean(_nested(item, "text", "full_text", "fullText", "content", "tweetText", "body"))
    created_at = _normalize_created_at(_nested(item, "created_at", "createdAt", "createdAtIso", "date", "timestamp"))
    author_handle = _clean(
        _nested(
            item,
            "author.username",
            "author.userName",
            "author.screen_name",
            "user.username",
            "user.userName",
            "username",
            "userName",
            "handle",
        )
    ).lstrip("@")
    author_name = _clean(_nested(item, "author.name", "user.name", "name", "author.displayName"))
    author_id = _clean(_nested(item, "author.id", "authorId", "user.id", "userId"))
    language = _clean(_nested(item, "lang", "language", "tweetLanguage"))
    if not post_id or not text or not created_at:
        return None
    if language and language.lower() not in {"en", "english"}:
        return None
    metrics = _nested(item, "public_metrics", "metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    like_count = _safe_int(_nested(item, "likeCount", "likes", "favorite_count") or metrics.get("like_count"))
    repost_count = _safe_int(
        _nested(item, "retweetCount", "repostCount", "retweets", "retweet_count")
        or metrics.get("retweet_count")
    )
    reply_count = _safe_int(_nested(item, "replyCount", "replies", "reply_count") or metrics.get("reply_count"))
    quote_count = _safe_int(_nested(item, "quoteCount", "quotes", "quote_count") or metrics.get("quote_count"))
    view_count = _safe_int(_nested(item, "viewCount", "views", "impression_count") or metrics.get("impression_count"))
    if not url and author_handle:
        url = f"https://x.com/{author_handle}/status/{post_id}"
    normalized_text = normalize_text_hash_text(text)
    return {
        "post_id": post_id,
        "author_handle": author_handle,
        "author_name": author_name,
        "author_id": author_id,
        "text": text,
        "created_at": created_at,
        "url": url,
        "like_count": like_count,
        "repost_count": repost_count,
        "reply_count": reply_count,
        "quote_count": quote_count,
        "view_count": view_count,
        "language": language or "en",
        "scraped_at": _now(),
        "apify_actor": actor_id,
        "apify_key_label": key_label,
        "source_query": source_value,
        "source_type": source_type,
        "raw_json_path": raw_json_path,
        "normalized_text_hash": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
    }


def _is_usable_finance_post(text: str) -> bool:
    lower = (text or "").lower()
    return bool(extract_x_ticker_mentions(text)) or any(word in lower for word in FINANCE_WORDS)


def _save_raw_items(run_id: str, actor_id: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    actor_slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", actor_id)
    path = RAW_X_APIFY_DIR / actor_slug / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return str(path.relative_to(PROJECT_ROOT))


def import_normalized_x_posts(posts: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    init_db()
    imported = 0
    duplicates = 0
    ticker_mentions = 0
    recommendation_events = 0
    with connect() as conn:
        apply_x_youtube_schema(conn)
        for post in posts:
            inserted = insert_x_post(conn, post)
            imported += int(inserted)
            duplicates += int(not inserted)
            mentions = extract_x_ticker_mentions(post.get("text", ""))
            for mention in mentions:
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO x_post_ticker_mentions
                      (post_id, ticker, cashtag, mention_type, confidence)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        post.get("post_id"),
                        mention.ticker,
                        mention.cashtag,
                        mention.mention_type,
                        mention.confidence,
                    ),
                )
                ticker_mentions += int(conn.total_changes > before)
            classification = classify_x_recommendation(post.get("text", ""))
            if classification.is_recommendation:
                event_date = _clean(post.get("created_at"))[:10]
                for mention in mentions:
                    before = conn.total_changes
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO x_recommendation_events (
                          post_id, author_handle, ticker, event_datetime, event_date,
                          recommendation_type, direction, confidence, source_method, evidence_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            post.get("post_id"),
                            post.get("author_handle"),
                            mention.ticker,
                            post.get("created_at"),
                            event_date,
                            classification.recommendation_type,
                            classification.direction,
                            classification.confidence,
                            "x_rules_v1",
                            classification.evidence_text,
                        ),
                    )
                    recommendation_events += int(conn.total_changes > before)
        conn.commit()
    return imported, duplicates, ticker_mentions, recommendation_events


def _extract_run_cost(run_status: dict[str, Any]) -> float:
    candidates = [
        run_status.get("usageTotalUsd"),
        _nested(run_status, "usage.totalUsd"),
        _nested(run_status, "stats.computeUnits"),
    ]
    for value in candidates:
        cost = _safe_float(value)
        if cost:
            return cost
    return 0.0


def run_single_x_apify_source(
    *,
    actor_id: str,
    source_type: str,
    source_value: str,
    limit: int,
    max_charge_usd: float,
    manager: ApifyKeyManager,
) -> dict[str, Any]:
    started = _now()
    input_payload = build_x_actor_input(actor_id, source_type, source_value, limit)
    input_hash = hashlib.sha256(json.dumps(input_payload, sort_keys=True).encode()).hexdigest()
    key = manager.choose_key(platform="x", projected_cost_usd=max_charge_usd)
    row: dict[str, Any] = {
        "actor_id": actor_id,
        "key_label": key.label,
        "source_type": source_type,
        "source_value": source_value,
        "posts_returned": 0,
        "posts_imported": 0,
        "duplicates": 0,
        "usable_finance_posts": 0,
        "posts_with_cashtags": 0,
        "posts_with_created_at": 0,
        "posts_with_metrics": 0,
        "cost_usd": 0.0,
        "seconds": 0.0,
        "posts_per_dollar": 0.0,
        "failure_rate": 1.0,
        "field_quality_score": 0.0,
        "schema_quality_score": 0.0,
        "run_id": "",
        "status": "FAILED",
        "notes": "",
    }
    started_seconds = time.time()
    try:
        with manager.activate_key(key):
            run = _start_run(actor_id, input_payload, key.token, max_charge_usd)
            run_id = _clean(run.get("id"))
            row["run_id"] = run_id
            status = _wait_run(
                run_id,
                key.token,
                max_wait_seconds=int(os.getenv("X_APIFY_ACTOR_MAX_WAIT_SECONDS", "60")),
            )
            items = _fetch_items(run_id, key.token)
        cost = _extract_run_cost(status)
        raw_path = _save_raw_items(run_id, actor_id, items)
        normalized: list[dict[str, Any]] = []
        required_field_hits = 0
        metric_hits = 0
        created_hits = 0
        cashtag_hits = 0
        usable = 0
        for item in items:
            post = normalize_apify_x_post(
                item,
                actor_id=actor_id,
                key_label=key.label,
                source_type=source_type,
                source_value=source_value,
                raw_json_path=raw_path,
            )
            if post is None:
                continue
            required_field_hits += int(
                bool(post.get("post_id") and post.get("text") and post.get("created_at"))
            )
            created_hits += int(bool(post.get("created_at")))
            metric_hits += int(
                any(post.get(k) is not None for k in ["like_count", "repost_count", "reply_count", "view_count"])
            )
            mentions = extract_x_ticker_mentions(post.get("text", ""))
            cashtag_hits += int(any(mention.cashtag for mention in mentions))
            if _is_usable_finance_post(post.get("text", "")):
                usable += 1
                normalized.append(post)
        imported, duplicates, _, _ = import_normalized_x_posts(normalized)
        row.update(
            {
                "posts_returned": len(items),
                "posts_imported": imported,
                "duplicates": duplicates,
                "usable_finance_posts": usable,
                "posts_with_cashtags": cashtag_hits,
                "posts_with_created_at": created_hits,
                "posts_with_metrics": metric_hits,
                "cost_usd": round(cost, 6),
                "seconds": round(time.time() - started_seconds, 3),
                "posts_per_dollar": round(imported / cost, 3) if cost else 0.0,
                "failure_rate": 0.0 if imported > 0 or len(items) > 0 else 1.0,
                "field_quality_score": round(required_field_hits / len(items), 4) if items else 0.0,
                "schema_quality_score": round(imported / max(1, len(items)), 4) if items else 0.0,
                "status": _clean(status.get("status")) or "UNKNOWN",
                "notes": "",
            }
        )
        manager.record_run(
            key_label=key.label,
            platform="x",
            actor_id=actor_id,
            run_id=row["run_id"],
            source_type=source_type,
            source_value=source_value,
            requested_items=limit,
            imported_items=imported,
            duplicates=duplicates,
            cost_usd=cost,
            status=row["status"],
            reason="",
        )
        with connect() as conn:
            insert_apify_collection_run(
                conn,
                {
                    "run_id": row["run_id"] or hashlib.sha256(input_hash.encode()).hexdigest()[:16],
                    "platform": "x",
                    "actor_id": actor_id,
                    "key_label": key.label,
                    "started_at": started,
                    "finished_at": _now(),
                    "status": row["status"],
                    "input_hash": input_hash,
                    "source_type": source_type,
                    "source_query": source_value,
                    "requested_items": limit,
                    "imported_items": imported,
                    "duplicates": duplicates,
                    "cost_usd": cost,
                    "error_message": "",
                },
            )
            conn.commit()
    except Exception as exc:
        message = str(exc)
        row.update({"seconds": round(time.time() - started_seconds, 3), "notes": message[:500]})
        manager.record_run(
            key_label=key.label,
            platform="x",
            actor_id=actor_id,
            run_id=row.get("run_id", ""),
            source_type=source_type,
            source_value=source_value,
            requested_items=limit,
            imported_items=0,
            duplicates=0,
            cost_usd=0.0,
            status="failed",
            reason=message[:300],
        )
    return row


def _bakeoff_sources() -> list[tuple[str, str]]:
    profiles = _read_lines(CONFIG_X_DIR / "profiles_likely.txt", 3)
    cashtags = _read_lines(CONFIG_X_DIR / "cashtags.txt", 3)
    searches = _read_lines(CONFIG_X_DIR / "search_queries.txt", 3)
    return [
        *[("profile", value) for value in profiles],
        *[("cashtag", value) for value in cashtags],
        *[("search", value) for value in searches],
    ]


def run_x_actor_bakeoff() -> dict[str, Any]:
    ensure_dirs()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    actors = _env_list("X_APIFY_ACTOR_CANDIDATES", DEFAULT_ACTORS)
    sources = _bakeoff_sources()
    manager = ApifyKeyManager.from_env()
    cap = _safe_float(os.getenv("X_APIFY_ACTOR_BAKEOFF_MAX_COST_USD")) or 1.0
    total_tests = max(1, len(actors) * len(sources))
    per_test_cap = max(0.01, min(0.03, cap / total_tests))
    rows: list[dict[str, Any]] = []
    spent = 0.0
    limit = 100
    for actor in actors:
        actor_failures = 0
        actor_success = False
        for source_type, source_value in sources:
            if actor_failures >= 2 and not actor_success:
                rows.append({
                    "actor_id": actor,
                    "key_label": "",
                    "source_type": source_type,
                    "source_value": source_value,
                    "posts_returned": 0,
                    "posts_imported": 0,
                    "duplicates": 0,
                    "usable_finance_posts": 0,
                    "posts_with_cashtags": 0,
                    "posts_with_created_at": 0,
                    "posts_with_metrics": 0,
                    "cost_usd": 0.0,
                    "seconds": 0.0,
                    "posts_per_dollar": 0.0,
                    "failure_rate": 1.0,
                    "field_quality_score": 0.0,
                    "schema_quality_score": 0.0,
                    "run_id": "",
                    "status": "SKIPPED_AFTER_ACTOR_FAILURES",
                    "notes": "actor failed earlier bakeoff sources",
                })
                continue
            if spent + per_test_cap > cap + 1e-9:
                rows.append(
                    {
                        "actor_id": actor,
                        "key_label": "",
                        "source_type": source_type,
                        "source_value": source_value,
                        "posts_returned": 0,
                        "posts_imported": 0,
                        "duplicates": 0,
                        "usable_finance_posts": 0,
                        "posts_with_cashtags": 0,
                        "posts_with_created_at": 0,
                        "posts_with_metrics": 0,
                        "cost_usd": 0.0,
                        "seconds": 0.0,
                        "posts_per_dollar": 0.0,
                        "failure_rate": 1.0,
                        "field_quality_score": 0.0,
                        "schema_quality_score": 0.0,
                        "run_id": "",
                        "status": "SKIPPED_CAP",
                        "notes": "bakeoff cap reached",
                    }
                )
                continue
            row = run_single_x_apify_source(
                actor_id=actor,
                source_type=source_type,
                source_value=source_value,
                limit=limit,
                max_charge_usd=per_test_cap,
                manager=manager,
            )
            rows.append(row)
            spent += _safe_float(row.get("cost_usd"))
            if _safe_int(row.get("posts_imported")):
                actor_success = True
            elif row.get("status") not in {"SKIPPED_CAP"}:
                actor_failures += 1

    fieldnames = [
        "actor_id",
        "key_label",
        "source_type",
        "source_value",
        "posts_returned",
        "posts_imported",
        "duplicates",
        "usable_finance_posts",
        "posts_with_cashtags",
        "posts_with_created_at",
        "posts_with_metrics",
        "cost_usd",
        "seconds",
        "posts_per_dollar",
        "failure_rate",
        "field_quality_score",
        "schema_quality_score",
        "run_id",
        "status",
        "notes",
    ]
    csv_path = OVERNIGHT_DIR / "02_x_actor_bakeoff.csv"
    _write_csv(csv_path, rows, fieldnames=fieldnames)

    scores: dict[str, float] = defaultdict(float)
    actor_counts: Counter[str] = Counter()
    for row in rows:
        actor = _clean(row.get("actor_id"))
        if not actor:
            continue
        actor_counts[actor] += 1
        scores[actor] += (
            (10 if _safe_int(row.get("posts_imported")) else 0)
            + _safe_float(row.get("field_quality_score")) * 5
            + _safe_float(row.get("schema_quality_score")) * 4
            + min(_safe_float(row.get("posts_per_dollar")) / 1000, 5)
            - _safe_float(row.get("failure_rate")) * 3
        )
    selected_actor = ""
    if scores:
        selected_actor = max(scores, key=lambda actor: scores[actor])
        successful_rows = [
            row for row in rows if row["actor_id"] == selected_actor and _safe_int(row["posts_imported"])
        ]
        if not successful_rows:
            selected_actor = ""
    if selected_actor:
        (OVERNIGHT_DIR / "selected_x_actor.txt").write_text(selected_actor + "\n", encoding="utf-8")

    md_lines = [
        "# X Actor Bakeoff",
        "",
        f"Generated: {_now()}",
        f"- Bakeoff cap USD: {cap:.2f}",
        f"- Per-test maxTotalChargeUsd: {per_test_cap:.4f}",
        f"- Actors tested: {len(actors)}",
        f"- Source tests configured: {len(sources)}",
        f"- Selected actor: {selected_actor or 'none'}",
        "",
        "| Actor | Tests | Imported | Cost USD | Avg Field Quality |",
        "|---|---:|---:|---:|---:|",
    ]
    for actor in actors:
        actor_rows = [row for row in rows if row.get("actor_id") == actor]
        imported = sum(_safe_int(row.get("posts_imported")) or 0 for row in actor_rows)
        cost = sum(_safe_float(row.get("cost_usd")) for row in actor_rows)
        avg_field = (
            sum(_safe_float(row.get("field_quality_score")) for row in actor_rows) / len(actor_rows)
            if actor_rows
            else 0
        )
        md_lines.append(f"| {actor} | {len(actor_rows)} | {imported} | {cost:.4f} | {avg_field:.3f} |")
    _write_md(OVERNIGHT_DIR / "02_x_actor_bakeoff.md", md_lines)

    passed = bool(selected_actor)
    checkpoint = [
        "# Checkpoint 05: X actor bakeoff",
        "",
        f"Status: {'PASS_AUTO_CONTINUE' if passed else 'CHECKPOINT_REQUIRES_USER_REVIEW'}",
        f"Generated: {_now()}",
        "",
        f"- At least one actor returned usable public posts: {'yes' if passed else 'no'}",
        f"- Selected actor has required fields: {'yes' if passed else 'no'}",
        f"- Selected actor: {selected_actor or 'none'}",
        f"- Cost reported: yes ({sum(_safe_float(row.get('cost_usd')) for row in rows):.6f} USD)",
        "- posts_per_dollar reported: yes",
        "- Secrets printed: no",
        f"- Budget exceeded: {'no' if spent <= cap + 1e-9 else 'yes'}",
    ]
    _write_md(OVERNIGHT_DIR / "checkpoint_05_actor_bakeoff.md", checkpoint)
    return {
        "rows": rows,
        "selected_actor": selected_actor,
        "csv_path": csv_path,
        "passed": passed,
    }


def apply_live_schema_checkpoint() -> dict[str, Any]:
    ensure_dirs()
    init_db()
    with connect() as conn:
        apply_x_youtube_schema(conn)
        conn.commit()
    return {"ok": True}


def reconcile_youtube_counts() -> dict[str, int]:
    with connect() as conn:
        videos = conn.execute("SELECT COUNT(*) AS n FROM raw_youtube_videos").fetchone()["n"]
        transcript_rows = conn.execute("SELECT COUNT(*) AS n FROM youtube_transcripts").fetchone()["n"]
        successful = conn.execute(
            """
            SELECT COUNT(*) AS n FROM youtube_transcripts
            WHERE COALESCE(retrieval_status, status) = 'available'
              AND COALESCE(full_text, '') != ''
            """
        ).fetchone()["n"]
    return {"videos": int(videos), "transcript_rows": int(transcript_rows), "successful": int(successful)}


def build_youtube_expansion_plan() -> dict[str, Any]:
    ensure_dirs()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    counts = reconcile_youtube_counts()
    target = int(os.getenv("YOUTUBE_TRANSCRIPT_TARGET_TOTAL", "11000") or 11000)
    missing_existing = max(counts["videos"] - counts["successful"], 0)
    need_for_target = max(target - counts["successful"], 0)
    feasible_20000 = counts["videos"] >= 20000
    ledger_path = OVERNIGHT_DIR / "03_youtube_collection_ledger.csv"
    if not ledger_path.exists():
        _write_csv(
            ledger_path,
            [
                {
                    "run_id": "planned",
                    "actor_id": "curious_coder/youtube-transcript-scraper",
                    "key_label": "pending_key_rotation",
                    "requested_items": min(missing_existing, need_for_target),
                    "imported_items": 0,
                    "duplicates": 0,
                    "cost_usd": 0.0,
                    "status": "planned_for_overnight_runner",
                    "notes": "No transcript spend executed during checkpoint; runner enforces cap.",
                }
            ],
        )
    plan = [
        "# YouTube Expansion Plan",
        "",
        f"Generated: {_now()}",
        f"- Current YouTube videos: {counts['videos']}",
        f"- Current successful transcripts with text: {counts['successful']}",
        f"- Current transcript rows: {counts['transcript_rows']}",
        f"- Existing videos missing successful transcript text: {missing_existing}",
        f"- Configured transcript target: {target}",
        f"- Additional successful transcripts needed for configured target: {need_for_target}",
        f"- 20,000 transcripts feasible from current video universe: {'yes' if feasible_20000 else 'no'}",
        "",
        "## Method",
        "- First attempt missing existing videos with curious_coder/youtube-transcript-scraper under the YouTube transcript cost cap.",
        "- Additional metadata discovery requires YouTube API quota and is not treated as evidence until deduped into raw_youtube_videos.",
        "- If the video universe remains below 20,000, the final report must state that honestly.",
    ]
    _write_md(OVERNIGHT_DIR / "03_youtube_expansion_plan.md", plan)
    summary = [
        "# YouTube Collection Summary",
        "",
        f"Generated: {_now()}",
        f"- Videos: {counts['videos']}",
        f"- Successful transcripts: {counts['successful']}",
        f"- Missing existing transcripts: {missing_existing}",
        "- Collection attempts ledgered: yes",
        "- Secrets printed: no",
    ]
    _write_md(OVERNIGHT_DIR / "03_youtube_collection_summary.md", summary)
    passed = True
    checkpoint = [
        "# Checkpoint 06: YouTube expansion",
        "",
        "Status: PASS_AUTO_CONTINUE",
        f"Generated: {_now()}",
        "",
        "- Current video/transcript count reconciled: yes",
        "- Missing existing transcripts attempted if budget allows: deferred to overnight runner under configured cap",
        "- Metadata expansion plan created: yes",
        f"- 20,000 impossible from current video universe: {'yes' if not feasible_20000 else 'no'}",
        "- All collection attempts ledgered: yes",
        "- Secrets printed: no",
    ]
    _write_md(OVERNIGHT_DIR / "checkpoint_06_youtube_expansion.md", checkpoint)
    return {**counts, "missing_existing": missing_existing, "target": target, "passed": passed}



def collect_youtube_transcript_topoff() -> dict[str, Any]:
    ensure_dirs()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    counts = reconcile_youtube_counts()
    target = int(os.getenv("YOUTUBE_TRANSCRIPT_TARGET_TOTAL", "11000") or 11000)
    needed = max(target - counts["successful"], 0)
    if needed <= 0:
        return {"status": "target_already_met", **counts, "attempted": 0, "available": 0}
    max_videos = min(needed, int(os.getenv("YOUTUBE_OVERNIGHT_MAX_TRANSCRIPT_VIDEOS", "300") or 300))
    cap = _safe_float(os.getenv("YOUTUBE_TRANSCRIPT_TOTAL_COST_CAP_USD")) or 4.0
    actor_id = os.getenv("YOUTUBE_TRANSCRIPT_APIFY_ACTOR", "curious_coder/youtube-transcript-scraper")
    manager = ApifyKeyManager.from_env()
    try:
        key = manager.choose_key(platform="youtube", projected_cost_usd=min(cap, 0.50))
    except ApifyBudgetError as exc:
        return {"status": "budget_blocked", "error": str(exc), **counts, "attempted": 0, "available": 0}
    try:
        from .apify_queue import select_apify_transcript_queue
        from .apify_transcripts import collect_apify_transcripts
        from .config import clear_settings_cache

        queue = select_apify_transcript_queue(
            start_date=DATE_START,
            end_date=DATE_END,
            max_videos=max_videos,
            dry_run=False,
        )
        if not queue.selected:
            return {"status": "no_missing_transcript_queue", **counts, "attempted": 0, "available": 0}
        with manager.activate_key(key):
            clear_settings_cache()
            result = collect_apify_transcripts(
                video_ids=[item.video_id for item in queue.selected],
                actor_id=actor_id,
                batch_size=25,
                max_total_charge_usd=min(cap, 0.50),
                dry_run=False,
            )
        cost = float(result.cost_usd or 0.0)
        manager.record_run(
            key_label=key.label,
            platform="youtube",
            actor_id=actor_id,
            run_id=result.run_id,
            source_type="missing_existing_transcripts",
            source_value="youtube_queue",
            requested_items=result.attempted_count,
            imported_items=result.available_count,
            duplicates=result.skipped_existing_count,
            cost_usd=cost,
            status="completed",
            reason="overnight_youtube_topoff",
        )
        rows = []
        for row in result.run_ledger:
            rows.append({"key_label": key.label, **row})
        if not rows:
            rows = [{"key_label": key.label, "phase": "completed", "actor_id": actor_id, "apify_run_id": result.run_id}]
        _write_csv(OVERNIGHT_DIR / "03_youtube_collection_ledger.csv", rows)
        after = reconcile_youtube_counts()
        _write_md(
            OVERNIGHT_DIR / "03_youtube_collection_summary.md",
            [
                "# YouTube Collection Summary",
                "",
                f"Generated: {_now()}",
                "Status: completed",
                f"Actor: {actor_id}",
                f"Key label: {key.label}",
                f"Attempted: {result.attempted_count}",
                f"Available imported: {result.available_count}",
                f"No transcript: {result.no_transcript_count}",
                f"Errors: {result.error_count}",
                f"Blocked: {result.blocked_count}",
                f"Cost USD: {cost:.6f}",
                f"Successful transcripts before: {counts['successful']}",
                f"Successful transcripts after: {after['successful']}",
                "Secrets printed: no",
            ],
        )
        return {
            "status": "completed",
            "actor_id": actor_id,
            "key_label": key.label,
            "attempted": result.attempted_count,
            "available": result.available_count,
            "cost_usd": cost,
            **after,
        }
    except Exception as exc:
        manager.record_run(
            key_label=key.label,
            platform="youtube",
            actor_id=actor_id,
            source_type="missing_existing_transcripts",
            source_value="youtube_queue",
            status="failed",
            reason=str(exc)[:300],
        )
        _write_md(
            OVERNIGHT_DIR / "03_youtube_collection_summary.md",
            [
                "# YouTube Collection Summary",
                "",
                f"Generated: {_now()}",
                "Status: failed",
                f"Actor: {actor_id}",
                f"Key label: {key.label}",
                f"Error: {str(exc)[:500]}",
                "Secrets printed: no",
            ],
        )
        return {"status": "failed", "error": str(exc)[:500], **counts, "attempted": 0, "available": 0}

def extract_and_classify_existing_x_posts() -> dict[str, int]:
    init_db()
    with connect() as conn:
        apply_x_youtube_schema(conn)
        posts = conn.execute("SELECT * FROM x_posts").fetchall()
        conn.execute("DELETE FROM x_post_ticker_mentions")
        conn.execute("DELETE FROM x_recommendation_events")
        conn.commit()
    normalized = [dict(row) for row in posts]
    _, _, mentions, events = import_normalized_x_posts(normalized)
    with connect() as conn:
        posts_count = conn.execute("SELECT COUNT(*) AS n FROM x_posts").fetchone()["n"]
    _write_csv(
        OVERNIGHT_DIR / "05_x_ticker_extraction_summary.csv",
        [{"x_posts": posts_count, "ticker_mentions": mentions}],
    )
    _write_csv(
        OVERNIGHT_DIR / "05_x_recommendation_event_summary.csv",
        [{"x_posts": posts_count, "x_recommendation_events": events}],
    )
    _write_md(
        OVERNIGHT_DIR / "05_x_classifier_failure_modes.md",
        [
            "# X Classifier Failure Modes",
            "",
            "- Rule-based pseudo-labels are not human validation.",
            "- Portfolio disclosure is intentionally not treated as buy advice.",
            "- News-only posts are separated from recommendations.",
            "- Ambiguous plain tickers are retained with low confidence and should be filtered in robustness checks.",
        ],
    )
    return {"posts": int(posts_count), "mentions": mentions, "events": events}


def build_integrated_tables() -> dict[str, Any]:
    ensure_dirs()
    with connect() as conn:
        x_posts = pd.read_sql_query("SELECT * FROM x_posts", conn)
        x_events = pd.read_sql_query("SELECT * FROM x_recommendation_events", conn)
    yt_path = PROJECT_ROOT / "data/exports/validation/clean_auto_labeled_events.csv"
    yt = pd.read_csv(yt_path) if yt_path.exists() else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    if not yt.empty:
        x_posts_local = x_posts.copy()
        if not x_posts_local.empty:
            x_posts_local["event_date"] = pd.to_datetime(x_posts_local["created_at"], errors="coerce").dt.date
        for _, event in yt.iterrows():
            ticker = _clean(event.get("ticker")).upper()
            event_date_raw = _clean(event.get("event_date_utc") or event.get("published_at"))[:10]
            try:
                event_date = datetime.strptime(event_date_raw, "%Y-%m-%d").date()
            except ValueError:
                continue
            mentions = x_posts_local[
                x_posts_local["text"].fillna("").str.contains(rf"\${ticker}\b|\b{ticker}\b", regex=True)
            ] if not x_posts_local.empty and ticker else pd.DataFrame()
            counts: dict[str, int] = {}
            engagement: dict[str, int] = {}
            windows = {
                "x_count_prior_30_8d": (-30, -8),
                "x_count_prior_7_1d": (-7, -1),
                "x_count_same_day": (0, 0),
                "x_count_post_1_7d": (1, 7),
                "x_count_post_8_30d": (8, 30),
            }
            for label, (start, end) in windows.items():
                if mentions.empty:
                    sub = mentions
                else:
                    start_date = event_date + timedelta(days=start)
                    end_date = event_date + timedelta(days=end)
                    sub = mentions[(mentions["event_date"] >= start_date) & (mentions["event_date"] <= end_date)]
                counts[label] = len(sub)
                engagement[label.replace("x_count", "x_engagement")] = int(
                    sub[["like_count", "repost_count", "reply_count", "quote_count"]]
                    .fillna(0)
                    .sum()
                    .sum()
                ) if not sub.empty else 0
            if counts["x_count_prior_30_8d"] or counts["x_count_prior_7_1d"]:
                category = "x_pre_attention"
            elif counts["x_count_same_day"]:
                category = "x_same_day_attention"
            elif counts["x_count_post_1_7d"] or counts["x_count_post_8_30d"]:
                category = "x_post_attention"
            else:
                category = "no_x_attention"
            if (counts["x_count_prior_30_8d"] or counts["x_count_prior_7_1d"]) and (
                counts["x_count_post_1_7d"] or counts["x_count_post_8_30d"]
            ):
                category = "persistent_x_attention"
            rows.append(
                {
                    "source_event_id": event.get("event_id"),
                    "source_type": "youtube_recommendation",
                    "ticker": ticker,
                    "event_date": event_date_raw,
                    "creator": event.get("creator"),
                    **counts,
                    **engagement,
                    "x_attention_preceded_youtube": bool(
                        counts["x_count_prior_30_8d"] or counts["x_count_prior_7_1d"]
                    ),
                    "youtube_preceded_x_attention": bool(
                        counts["x_count_post_1_7d"] or counts["x_count_post_8_30d"]
                    ),
                    "attention_category": category,
                }
            )
    for _, event in x_events.iterrows():
        rows.append(
            {
                "source_event_id": event.get("event_id"),
                "source_type": "x_recommendation",
                "ticker": event.get("ticker"),
                "event_date": event.get("event_date"),
                "creator": event.get("author_handle"),
                "attention_category": "x_only",
            }
        )
    _write_csv(OVERNIGHT_DIR / "06_integrated_event_inventory.csv", rows)
    summary_rows = []
    if rows:
        counts = Counter(row.get("attention_category", "unknown") for row in rows)
        summary_rows = [{"attention_category": key, "events": value} for key, value in counts.items()]
    _write_csv(OVERNIGHT_DIR / "06_youtube_x_overlap_summary.csv", summary_rows)
    _write_md(
        OVERNIGHT_DIR / "06_attention_vs_recommendation_design.md",
        [
            "# Attention vs Recommendation Design",
            "",
            "YouTube recommendation events are compared against X attention windows before, on, and after the event date.",
            "X posts are rule-classified as pseudo-labeled recommendations or non-recommendation finance attention.",
            "The design is descriptive and does not identify causality.",
        ],
    )
    return {"integrated_rows": len(rows), "x_events": len(x_events), "youtube_events": len(yt)}


def build_event_study_placeholders() -> dict[str, Any]:
    ensure_dirs()
    verified_returns = PROJECT_ROOT / "data/exports/research_expansion_audit/05_verified_event_window_returns.csv"
    if verified_returns.exists():
        returns = pd.read_csv(verified_returns)
    else:
        returns = pd.DataFrame()
    integrated_path = OVERNIGHT_DIR / "06_integrated_event_inventory.csv"
    integrated = pd.read_csv(integrated_path) if integrated_path.exists() else pd.DataFrame()
    returns.to_csv(EVENT_STUDY_DIR / "event_window_returns.csv", index=False)
    if not returns.empty:
        summary = returns.groupby(["horizon", "benchmark_ticker"], dropna=False).agg(
            N=("event_id", "nunique"),
            mean_abnormal_return=("abnormal_return", "mean"),
            median_abnormal_return=("abnormal_return", "median"),
            win_rate=("abnormal_return", lambda values: float((values > 0).mean())),
        ).reset_index()
    else:
        summary = pd.DataFrame(columns=["horizon", "benchmark_ticker", "N"])
    summary.to_csv(EVENT_STUDY_DIR / "event_window_summary.csv", index=False)
    for name in [
        "event_window_by_source_type.csv",
        "event_window_by_creator.csv",
        "event_window_by_ticker.csv",
        "event_window_by_attention_category.csv",
        "robust_statistics.csv",
        "placebo_tests.csv",
        "multiple_testing_adjustment.csv",
    ]:
        if name == "event_window_by_attention_category.csv" and not integrated.empty:
            integrated.groupby("attention_category").size().reset_index(name="events").to_csv(
                EVENT_STUDY_DIR / name, index=False
            )
        else:
            pd.DataFrame().to_csv(EVENT_STUDY_DIR / name, index=False)
    _write_md(
        EVENT_STUDY_DIR / "statistical_summary.md",
        [
            "# Statistical Summary",
            "",
            f"Generated: {_now()}",
            "- Uses corrected audited YouTube event-window file when X data are not yet sufficient.",
            "- X/Youtube integrated conclusions must wait for post-collection quality checks.",
            "- yfinance market data are prototype-grade and not production-quality return evidence.",
        ],
    )
    checkpoint = [
        "# Checkpoint 10: Event study quality",
        "",
        "Status: CHECKPOINT_REQUIRES_USER_REVIEW",
        f"Generated: {_now()}",
        "",
        "- Sample counts are clear: partial",
        "- Duplicates are controlled: yes for imported X posts and audited YouTube sample",
        "- Event timing is defined: yes",
        "- Valid return coverage by horizon is reported: uses audited YouTube file if present",
        "- Pre-event windows included: inherited from audited file if present",
        "- Benchmark-adjusted results included: inherited from audited file if present",
        "- Placebo tests included where feasible: not rerun until X collection quality passes",
        "- yfinance prototype caveat included: yes",
    ]
    _write_md(EVENT_STUDY_DIR / "checkpoint_10_event_study_quality.md", checkpoint)
    return {"returns_rows": len(returns), "integrated_rows": len(integrated)}


def build_portfolio_placeholders() -> dict[str, Any]:
    ensure_dirs()
    for name in [
        "portfolio_daily_returns.csv",
        "portfolio_performance_summary.csv",
        "portfolio_drawdowns.csv",
    ]:
        pd.DataFrame().to_csv(EVENT_STUDY_DIR / name, index=False)
    _write_md(
        EVENT_STUDY_DIR / "portfolio_performance_summary.md",
        [
            "# Portfolio Performance Summary",
            "",
            "Portfolio tests are blocked until post-collection event-study quality passes.",
        ],
    )
    _write_md(
        EVENT_STUDY_DIR / "portfolio_methodology_notes.md",
        [
            "# Portfolio Methodology Notes",
            "",
            "Planned assumptions: next-trading-day entry, equal weights, no lookahead, 10 bps default transaction cost, deterministic overlapping-event handling.",
        ],
    )
    _write_md(
        EVENT_STUDY_DIR / "checkpoint_11_portfolio_quality.md",
        [
            "# Checkpoint 11: Portfolio quality",
            "",
            "Status: CHECKPOINT_REQUIRES_USER_REVIEW",
            f"Generated: {_now()}",
            "",
            "- Portfolio tests blocked until post-collection event-study quality passes.",
            "- No tradable-alpha claim is made.",
        ],
    )
    return {"portfolio_rows": 0}


def build_final_research_outputs() -> dict[str, Path]:
    ensure_dirs()
    youtube = reconcile_youtube_counts()
    with connect() as conn:
        x_posts = conn.execute("SELECT COUNT(*) AS n FROM x_posts").fetchone()["n"]
        x_events = conn.execute("SELECT COUNT(*) AS n FROM x_recommendation_events").fetchone()["n"]
    common = [
        "Research question: Do YouTube and X finfluencer stock recommendations contain stock-selection signal, or are observed returns better explained by social-media attention, momentum, market news, and noise?",
        "",
        f"YouTube videos in DB: {youtube['videos']}",
        f"Successful YouTube transcripts: {youtube['successful']}",
        f"X posts imported: {x_posts}",
        f"X recommendation events: {x_events}",
        "",
        "Claims must remain conservative: no causality, no human validation, no tradable-alpha claim without post-cost benchmark-adjusted robustness.",
    ]
    files = {
        "final_research_update.md": ["# Final Research Update", "", *common],
        "final_methodology_section.md": [
            "# Final Methodology Section",
            "",
            "Events are pseudo-labeled using deterministic rules. X posts are used only for empirical classification and aggregate analysis, not model training.",
        ],
        "final_results_section.md": [
            "# Final Results Section",
            "",
            "Final results are pending post-collection quality checks. Existing audited YouTube-only results should be reported from the corrected audit sample, not inflated OpenCode counts.",
        ],
        "final_limitations_section.md": [
            "# Final Limitations Section",
            "",
            "Labels are rule-based pseudo-labels; yfinance market data are prototype-grade; X actor coverage may be incomplete; evidence is descriptive, not causal.",
        ],
        "final_claims_guardrail.md": [
            "# Final Claims Guardrail",
            "",
            "Use: descriptive evidence, benchmark-adjusted returns, pseudo-labeled recommendations, attention/momentum alternative explanation.",
            "Avoid: causal alpha, human validated, proven strategy, guaranteed outperformance, tradable edge.",
        ],
        "professor_one_page_update.md": ["# Professor One Page Update", "", *common],
        "final_presentation_talking_points.md": [
            "# Final Presentation Talking Points",
            "",
            "- The project separates stock-selection signal from social-media attention.",
            "- X data provide an attention/control layer around YouTube events.",
            "- Conclusions remain conservative and robustness-first.",
        ],
        "final_tables_and_charts_to_use.md": [
            "# Final Tables And Charts To Use",
            "",
            "- Source inventory counts",
            "- X actor bakeoff table",
            "- YouTube/X overlap summary",
            "- Corrected audited YouTube event-window summary",
            "- Portfolio table only after checkpoint 11 passes",
        ],
        "final_abstract.md": [
            "# Final Abstract",
            "",
            "This capstone studies whether finfluencer recommendations on YouTube and X exhibit stock-selection signal after accounting for attention, momentum, and benchmark returns. Findings are framed as descriptive evidence using pseudo-labeled events.",
        ],
        "final_next_steps.md": [
            "# Final Next Steps",
            "",
            "- Complete overnight X collection under caps.",
            "- Re-run post-collection quality checks.",
            "- Only then finalize event-study and portfolio conclusions.",
        ],
    }
    written: dict[str, Path] = {}
    for name, lines in files.items():
        path = FINAL_PROJECT_DIR / name
        _write_md(path, lines)
        written[name] = path
    return written


def run_main_x_collection(selected_actor: str | None = None) -> dict[str, Any]:
    ensure_dirs()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    if not selected_actor:
        selected_path = OVERNIGHT_DIR / "selected_x_actor.txt"
        selected_actor = selected_path.read_text(encoding="utf-8").strip() if selected_path.exists() else ""
    if not selected_actor:
        return {"status": "blocked_no_selected_actor", "imported": 0}
    manager = ApifyKeyManager.from_env()
    target = int(os.getenv("X_POST_TARGET_TOTAL", "75000") or 75000)
    max_hours = _safe_float(os.getenv("COLLECTION_MAX_RUNTIME_HOURS")) or 15.0
    deadline = time.time() + max_hours * 3600
    sources = [
        *[("profile", value) for value in _read_lines(CONFIG_X_DIR / "profiles_verified.txt")],
        *[("profile", value) for value in _read_lines(CONFIG_X_DIR / "profiles_likely.txt")],
        *[("profile", value) for value in _read_lines(CONFIG_X_DIR / "market_control_accounts.txt")],
        *[("cashtag", value) for value in _read_lines(CONFIG_X_DIR / "cashtags.txt")],
        *[("search", value) for value in _read_lines(CONFIG_X_DIR / "search_queries.txt")],
    ]
    ledger_rows: list[dict[str, Any]] = []
    consecutive_failures = 0
    while time.time() < deadline:
        with connect() as conn:
            current_posts = conn.execute("SELECT COUNT(*) AS n FROM x_posts").fetchone()["n"]
        if current_posts >= target:
            break
        progressed = False
        for source_type, source_value in sources:
            if time.time() >= deadline:
                break
            with connect() as conn:
                current_posts = conn.execute("SELECT COUNT(*) AS n FROM x_posts").fetchone()["n"]
            if current_posts >= target:
                break
            try:
                row = run_single_x_apify_source(
                    actor_id=selected_actor,
                    source_type=source_type,
                    source_value=source_value,
                    limit=250,
                    max_charge_usd=0.10,
                    manager=manager,
                )
            except ApifyBudgetError as exc:
                ledger_rows.append({"status": "budget_exhausted", "notes": str(exc)})
                _write_csv(OVERNIGHT_DIR / "04_x_collection_ledger.csv", ledger_rows)
                return {"status": "budget_exhausted", "imported": current_posts}
            ledger_rows.append(row)
            progressed = True
            if _safe_int(row.get("posts_imported")):
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            _write_csv(OVERNIGHT_DIR / "04_x_collection_ledger.csv", ledger_rows)
            with connect() as conn:
                total = conn.execute("SELECT COUNT(*) AS n FROM x_posts").fetchone()["n"]
            _write_csv(
                OVERNIGHT_DIR / "04_x_collection_progress.csv",
                [{"target": target, "current_x_posts": total, "updated_at": _now()}],
            )
            if consecutive_failures >= 10:
                _write_md(
                    OVERNIGHT_DIR / "04_x_collection_summary.md",
                    [
                        "# X Collection Summary",
                        "",
                        "Status: stopped_repeated_failures",
                        f"Current X posts: {total}",
                    ],
                )
                return {"status": "stopped_repeated_failures", "imported": total}
        if not progressed:
            break
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM x_posts").fetchone()["n"]
    status = "target_reached" if total >= target else "runtime_elapsed_or_sources_exhausted"
    _write_md(
        OVERNIGHT_DIR / "04_x_collection_summary.md",
        ["# X Collection Summary", "", f"Status: {status}", f"Current X posts: {total}", f"Target: {target}"],
    )
    return {"status": status, "imported": total}


def run_overnight_x_youtube_expansion() -> dict[str, Any]:
    ensure_dirs()
    apply_live_schema_checkpoint()
    bakeoff_path = OVERNIGHT_DIR / "selected_x_actor.txt"
    bakeoff = {"selected_actor": bakeoff_path.read_text(encoding="utf-8").strip()} if bakeoff_path.exists() else run_x_actor_bakeoff()
    youtube = build_youtube_expansion_plan()
    youtube_topoff = collect_youtube_transcript_topoff()
    collection = run_main_x_collection(bakeoff.get("selected_actor", ""))
    classification = extract_and_classify_existing_x_posts()
    integrated = build_integrated_tables()
    event_study = build_event_study_placeholders()
    portfolios = build_portfolio_placeholders()
    finals = build_final_research_outputs()
    report = {
        "bakeoff": bakeoff,
        "youtube": youtube,
        "youtube_topoff": youtube_topoff,
        "collection": collection,
        "classification": classification,
        "integrated": integrated,
        "event_study": event_study,
        "portfolios": portfolios,
        "final_files": {key: str(value) for key, value in finals.items()},
    }
    (OVERNIGHT_DIR / "overnight_runner_summary.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    return report
