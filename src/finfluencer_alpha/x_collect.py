from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from .config import FINANCE_KEYWORDS, SEED_X_HANDLES, X_DISCOVERY_QUERIES, get_settings
from .db import connect, init_db, upsert_creator
from .ticker_extract import extract_tickers
from .utils import get_logger, request_json, save_raw_json

X_RECENT_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
X_ALL_SEARCH_URL = "https://api.x.com/2/tweets/search/all"

logger = get_logger(__name__)


def _ensure_no_retweets(query: str) -> str:
    return query if "-is:retweet" in query else f"{query} -is:retweet"


def _x_search_url() -> str:
    settings = get_settings()
    if settings.x_search_mode == "all":
        logger.info("X_SEARCH_MODE=all selected; using full-archive endpoint if the token has access.")
        return X_ALL_SEARCH_URL
    return X_RECENT_SEARCH_URL


def _insert_x_posts(conn: sqlite3.Connection, tweets: list[dict[str, Any]], users: dict[str, Any]) -> int:
    inserted = 0
    for tweet in tweets:
        metrics = tweet.get("public_metrics", {})
        author = users.get(tweet.get("author_id"), {})
        username = author.get("username")
        raw_json = json.dumps(tweet, sort_keys=True)
        conn.execute(
            """
            INSERT INTO raw_x_posts (
              post_id, creator_handle, author_id, created_at, text, lang,
              like_count, repost_count, reply_count, quote_count, impression_count,
              url, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
              creator_handle = excluded.creator_handle,
              author_id = excluded.author_id,
              created_at = excluded.created_at,
              text = excluded.text,
              lang = excluded.lang,
              like_count = excluded.like_count,
              repost_count = excluded.repost_count,
              reply_count = excluded.reply_count,
              quote_count = excluded.quote_count,
              impression_count = excluded.impression_count,
              url = excluded.url,
              raw_json = excluded.raw_json
            """,
            (
                tweet.get("id"),
                username,
                tweet.get("author_id"),
                tweet.get("created_at"),
                tweet.get("text"),
                tweet.get("lang"),
                metrics.get("like_count"),
                metrics.get("retweet_count"),
                metrics.get("reply_count"),
                metrics.get("quote_count"),
                metrics.get("impression_count"),
                f"https://x.com/{username}/status/{tweet.get('id')}" if username else None,
                raw_json,
            ),
        )
        inserted += 1
    return inserted


def search_x_posts(
    query: str,
    start_time: str | None = None,
    end_time: str | None = None,
    max_pages: int = 1,
) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.x_bearer_token:
        logger.warning("Skipping X search because X_BEARER_TOKEN is not set.")
        return []

    init_db()
    headers = {"Authorization": f"Bearer {settings.x_bearer_token}"}
    params: dict[str, Any] = {
        "query": _ensure_no_retweets(query),
        "max_results": 100,
        "tweet.fields": "created_at,author_id,lang,public_metrics,entities,referenced_tweets",
        "expansions": "author_id",
        "user.fields": "username,name,public_metrics,verified",
    }
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    session = requests.Session()
    all_pages: list[dict[str, Any]] = []
    next_token: str | None = None
    with connect() as conn:
        for page in range(max(1, max_pages)):
            if next_token:
                params["next_token"] = next_token
            payload = request_json(session, _x_search_url(), headers=headers, params=params)
            if not payload:
                if settings.x_search_mode == "all":
                    logger.warning(
                        "X full-archive search is unavailable for this token or request. "
                        "Set X_SEARCH_MODE=recent to continue with recent search."
                    )
                break
            save_raw_json("x", f"search_page_{page + 1}", payload)
            all_pages.append(payload)
            users = {user["id"]: user for user in payload.get("includes", {}).get("users", [])}
            _insert_x_posts(conn, payload.get("data", []), users)
            next_token = payload.get("meta", {}).get("next_token")
            if not next_token:
                break
        conn.commit()
    return all_pages


def discover_x_creators_from_queries(
    queries: list[str] | None = None,
    max_pages: int = 1,
) -> int:
    queries = queries or X_DISCOVERY_QUERIES
    creator_tweets: dict[str, list[str]] = defaultdict(list)
    creator_users: dict[str, dict[str, Any]] = {}

    pages: list[dict[str, Any]] = []
    for query in queries:
        pages.extend(search_x_posts(query, max_pages=max_pages))

    for payload in pages:
        users = {user["id"]: user for user in payload.get("includes", {}).get("users", [])}
        for user in users.values():
            creator_users[user["username"]] = user
        for tweet in payload.get("data", []):
            user = users.get(tweet.get("author_id"))
            if user and user.get("username"):
                creator_tweets[user["username"]].append(tweet.get("text", ""))

    with connect() as conn:
        for username, texts in creator_tweets.items():
            user = creator_users.get(username, {})
            combined = " ".join(texts)
            ticker_count = sum(len(extract_tickers(text)) for text in texts)
            finance_hits = sum(combined.lower().count(keyword) for keyword in FINANCE_KEYWORDS)
            post_count = len(texts)
            relevance_score = min(100.0, ticker_count * 8 + finance_hits * 1.5 + post_count * 2)
            metrics = user.get("public_metrics", {})
            upsert_creator(
                conn,
                {
                    "platform": "x",
                    "handle": username,
                    "display_name": user.get("name"),
                    "account_url": f"https://x.com/{username}",
                    "category": "candidate_finance_market_attention",
                    "source_method": "x_api_search",
                    "include_reason": "Matched finance/stock discovery query; pending manual filtering.",
                    "follower_count": metrics.get("followers_count"),
                    "post_count": metrics.get("tweet_count") or post_count,
                    "relevance_score": round(relevance_score, 3),
                },
            )
        conn.commit()
    return len(creator_tweets)


def collect_x_for_seed_handles(
    handles: list[str] | None = None,
    days_back: int = 7,
    max_pages: int = 1,
    strict_stock_pick: bool = False,
) -> int:
    handles = handles or SEED_X_HANDLES
    start_time = (datetime.now(UTC) - timedelta(days=days_back)).replace(microsecond=0).isoformat()
    total_pages = 0

    init_db()
    with connect() as conn:
        for handle in handles:
            upsert_creator(
                conn,
                {
                    "platform": "x",
                    "handle": handle,
                    "display_name": None,
                    "account_url": f"https://x.com/{handle}",
                    "category": "candidate_finance_market_attention",
                    "source_method": "seed_list",
                    "include_reason": "Seed finance/market-attention account pending recommendation filtering.",
                },
            )
        conn.commit()

    stock_terms = (
        '("$" OR buy OR buying OR long OR short OR sell OR watchlist OR undervalued OR '
        "overvalued OR target OR PT OR calls OR puts)"
    )
    for handle in handles:
        query = f"from:{handle} lang:en -is:retweet"
        if strict_stock_pick:
            query = f"from:{handle} {stock_terms} lang:en -is:retweet"
        total_pages += len(search_x_posts(query, start_time=start_time, max_pages=max_pages))
    return total_pages
