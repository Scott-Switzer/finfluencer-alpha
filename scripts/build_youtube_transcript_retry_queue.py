#!/usr/bin/env python3
"""Build a retry-focused YouTube transcript queue after provider failures."""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from finfluencer_alpha.youtube_stock_pick_scoring import (  # noqa: E402
    score_video_stock_pick_likelihood,
)

DB_PATH = ROOT / "data" / "finfluencer_alpha.db"
OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
OUT_CSV = OUT_DIR / "71_youtube_transcript_retry_queue.csv"
OUT_MD = OUT_DIR / "71_youtube_transcript_retry_queue.md"

PERMANENT_ERROR_TYPES = {
    "transcriptnotfound",
    "transcriptsdisabled",
    "agerestricted",
    "videounavailable",
    "url_not_supported",
    "video_id_not_found",
    "disabled",
    "unavailable",
    "removed",
    "private",
    "age_restricted",
    "no_transcript",
}
RECOMMENDATION_TOKENS = {
    "stock to buy",
    "stocks to buy",
    "best stocks",
    "top stocks",
    "buy now",
    "sell now",
    "undervalued",
    "portfolio update",
    "my portfolio",
    "stock pick",
    "price target",
    "earnings analysis",
}
TICKER_HINTS = {
    "$",
    "tsla",
    "tesla",
    "nvda",
    "nvidia",
    "pltr",
    "palantir",
    "aapl",
    "apple",
    "amzn",
    "amazon",
    "msft",
    "microsoft",
    "goog",
    "googl",
    "google",
    "amd",
    "meta",
    "sofi",
}


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _truthy(v: str | None) -> bool:
    return _clean(v).lower() in {"1", "true", "yes", "on", "y"}


def _duration_seconds(raw_json: str) -> int:
    if not raw_json:
        return 0
    try:
        payload = json.loads(raw_json)
    except Exception:
        return 0
    duration = (
        payload.get("contentDetails", {}).get("duration")
        if isinstance(payload, dict)
        else ""
    )
    text = _clean(duration)
    if not text.startswith("PT"):
        return 0
    hours = minutes = seconds = 0
    num = ""
    for ch in text[2:]:
        if ch.isdigit():
            num += ch
            continue
        if ch == "H":
            hours = int(num or "0")
        elif ch == "M":
            minutes = int(num or "0")
        elif ch == "S":
            seconds = int(num or "0")
        num = ""
    return hours * 3600 + minutes * 60 + seconds


def _is_short(title: str, duration_seconds: int) -> bool:
    return "#shorts" in title.lower() or (duration_seconds > 0 and duration_seconds < 90)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(r["name"]).lower() == col.lower() for r in rows)


def build_retry_queue() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not DB_PATH.exists():
        return [], {"reason": f"missing_db:{DB_PATH}"}
    include_permanent = _truthy(os.getenv("YOUTUBE_RETRY_INCLUDE_PERMANENT_FAILURES", "0"))
    very_long_limit = int(os.getenv("YOUTUBE_RETRY_MAX_DURATION_SECONDS", str(3 * 3600)) or (3 * 3600))
    max_rows = int(os.getenv("YOUTUBE_RETRY_QUEUE_MAX_ROWS", "50000") or 50000)
    high_short_override = float(os.getenv("YOUTUBE_RETRY_SHORT_OVERRIDE_SCORE", "65") or 65)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "raw_youtube_videos"):
            return [], {"reason": "missing_table:raw_youtube_videos"}

        # latest status and failure type by video
        latest_status: dict[str, str] = {}
        latest_error_type: dict[str, str] = {}
        latest_error_message: dict[str, str] = {}
        attempt_count: Counter[str] = Counter()
        if _table_exists(conn, "youtube_transcripts"):
            has_collected = _col_exists(conn, "youtube_transcripts", "collected_at")
            ts_expr = "COALESCE(retrieved_at, collected_at, '')" if has_collected else "COALESCE(retrieved_at, '')"
            rows = conn.execute(
                """
                SELECT video_id,
                       COALESCE(status,'') AS status,
                       COALESCE(error_type,'') AS error_type,
                       COALESCE(error_message,'') AS error_message,
                       """ + ts_expr + """ AS ts
                FROM youtube_transcripts
                WHERE COALESCE(video_id,'') != ''
                ORDER BY ts DESC
                """
            ).fetchall()
            for r in rows:
                vid = _clean(r["video_id"])
                if not vid:
                    continue
                attempt_count[vid] += 1
                if vid not in latest_status:
                    latest_status[vid] = _clean(r["status"]).lower()
                    latest_error_type[vid] = _clean(r["error_type"])
                    latest_error_message[vid] = _clean(r["error_message"])

        creator_windows: Counter[str] = Counter()
        creator_accepted: Counter[str] = Counter()
        if _table_exists(conn, "transcript_candidate_windows"):
            rows = conn.execute(
                """
                SELECT rv.channel_title AS creator,
                       COALESCE(tcw.accepted_event_flag,0) AS accepted_flag
                FROM transcript_candidate_windows tcw
                LEFT JOIN raw_youtube_videos rv ON rv.video_id = tcw.video_id
                """
            ).fetchall()
            for r in rows:
                creator = _clean(r["creator"]) or "unknown"
                creator_windows[creator] += 1
                if int(r["accepted_flag"] or 0) == 1:
                    creator_accepted[creator] += 1

        rows = conn.execute(
            """
            SELECT video_id, url, channel_title, title, description, published_at, raw_json
            FROM raw_youtube_videos
            WHERE COALESCE(video_id,'') != ''
              AND COALESCE(excluded_flag,0)=0
            """
        ).fetchall()

        out: list[dict[str, Any]] = []
        excluded = Counter()
        dedupe: set[str] = set()
        for r in rows:
            vid = _clean(r["video_id"])
            if not vid or vid in dedupe:
                excluded["duplicate_video_id"] += 1
                continue
            dedupe.add(vid)
            status = latest_status.get(vid, "")
            if status == "available":
                excluded["already_successful"] += 1
                continue

            error_type = _clean(latest_error_type.get(vid, ""))
            prior_failure_type = error_type or status or "none"
            if (error_type.lower() in PERMANENT_ERROR_TYPES or status in PERMANENT_ERROR_TYPES) and not include_permanent:
                excluded["permanent_failure_excluded"] += 1
                continue

            title = _clean(r["title"])
            desc = _clean(r["description"])
            channel = _clean(r["channel_title"]) or "unknown"
            duration = _duration_seconds(_clean(r["raw_json"]))
            is_short = _is_short(title, duration)
            if duration > very_long_limit:
                excluded["very_long_excluded"] += 1
                continue

            text = f"{title.lower()} {desc.lower()}"
            ticker_hit = int(any(token in text for token in TICKER_HINTS))
            rec_hit = int(any(token in text for token in RECOMMENDATION_TOKENS))
            creator_total = int(creator_windows.get(channel, 0))
            creator_acc = int(creator_accepted.get(channel, 0))
            creator_rate = (creator_acc / creator_total) if creator_total else 0.0
            stock_pick_score = score_video_stock_pick_likelihood(
                title,
                desc,
                channel,
                duration,
                {
                    "prior_conversion_rate": creator_rate,
                    "prior_accepted_events": creator_acc,
                    "creator_type": "stock_picker" if creator_rate >= 0.05 else "unknown",
                },
            )
            retry_score = stock_pick_score
            reasons: list[str] = []
            if ticker_hit:
                retry_score += 8
                reasons.append("ticker_hit")
            if rec_hit:
                retry_score += 8
                reasons.append("recommendation_hit")
            if creator_rate > 0:
                retry_score += min(12.0, creator_rate * 20.0)
                reasons.append("creator_prior_event_rate")
            if is_short:
                if stock_pick_score >= high_short_override:
                    reasons.append("short_override_high_score")
                else:
                    retry_score -= 8
                    reasons.append("short_deprioritized")
            else:
                retry_score += 4
                reasons.append("non_short")
            if duration == 0:
                retry_score -= 2
                reasons.append("unknown_duration")

            out.append(
                {
                    "video_id": vid,
                    "url": _clean(r["url"]) or f"https://www.youtube.com/watch?v={vid}",
                    "channel_title": channel,
                    "title": title,
                    "published_at": _clean(r["published_at"]),
                    "retry_priority_score": round(retry_score, 3),
                    "retry_reason": ";".join(reasons),
                    "prior_failure_type": prior_failure_type,
                    "prior_attempt_count": int(attempt_count.get(vid, 0)),
                    "stock_pick_score": round(stock_pick_score, 3),
                    "creator_prior_event_rate": round(creator_rate, 4),
                    "duration_seconds": int(duration),
                    "is_short": int(is_short),
                    "title_description_ticker_hit": ticker_hit,
                    "recommendation_keyword_hit": rec_hit,
                }
            )

        out.sort(
            key=lambda x: (
                -float(x["retry_priority_score"]),
                -int(x["recommendation_keyword_hit"]),
                -int(x["title_description_ticker_hit"]),
                int(x["prior_attempt_count"]),
                x["video_id"],
            )
        )
        out = out[:max_rows]
        return out, {"excluded": dict(excluded), "rows": len(out), "include_permanent": include_permanent}
    finally:
        conn.close()


def write_outputs(rows: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "video_id",
        "url",
        "channel_title",
        "title",
        "published_at",
        "retry_priority_score",
        "retry_reason",
        "prior_failure_type",
        "prior_attempt_count",
        "stock_pick_score",
        "creator_prior_event_rate",
        "duration_seconds",
        "is_short",
        "title_description_ticker_hit",
        "recommendation_keyword_hit",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "# YouTube transcript retry queue",
        "",
        f"Generated UTC: `{now}`",
        f"Rows queued: `{len(rows)}`",
        f"Include permanent failures: `{stats.get('include_permanent')}`",
        "",
        "## Exclusions",
        "",
    ]
    for k, v in sorted((stats.get("excluded") or {}).items()):
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Top 40 retry rows", ""]
    for i, row in enumerate(rows[:40], start=1):
        lines.append(
            f"- `{i}` `{row['video_id']}` score={row['retry_priority_score']} "
            f"attempts={row['prior_attempt_count']} failure=`{row['prior_failure_type']}` "
            f"short={row['is_short']} duration={row['duration_seconds']} creator=`{row['channel_title']}`"
        )
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    rows, stats = build_retry_queue()
    write_outputs(rows, stats)
    print(f"WROTE_CSV={OUT_CSV.relative_to(ROOT)}")
    print(f"WROTE_MD={OUT_MD.relative_to(ROOT)}")
    print(f"QUEUE_ROWS={len(rows)}")


if __name__ == "__main__":
    main()
