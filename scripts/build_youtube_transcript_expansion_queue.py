#!/usr/bin/env python3
"""Build prioritized queue for YouTube transcript expansion."""
from __future__ import annotations

import csv
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "finfluencer_alpha.db"
OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
OUT_CSV = OUT_DIR / "50_youtube_transcript_expansion_queue.csv"
OUT_MD = OUT_DIR / "50_youtube_transcript_expansion_queue.md"
SEED_CSV = ROOT / "data" / "seeds" / "youtube_seed_channels.csv"

DATE_START = os.getenv("YOUTUBE_QUEUE_DATE_START", "2020-01-01")
DATE_END = os.getenv("YOUTUBE_QUEUE_DATE_END", "2026-12-31")
MAX_ROWS = int(os.getenv("YOUTUBE_QUEUE_MAX_ROWS", "5000") or 5000)

PERMANENT_FAIL = {"disabled", "unavailable", "removed", "private", "age_restricted", "no_transcript"}
TRANSIENT_FAIL = {"request_blocked", "ip_blocked", "rate_limited", "error", "no_language"}
TICKER_HINTS = {
    "$", "stock", "stocks", "buy", "sell", "price target", "pt", "valuation",
    "earnings", "guidance", "bull", "bear", "long", "short",
    "tesla", "tsla", "apple", "aapl", "nvidia", "nvda", "palantir", "pltr", "sofi",
}
COMPANY_CUES = {"inc", "corp", "shares", "equity", "nasdaq", "nyse", "ticker"}
SHORT_CUE = "#shorts"


@dataclass
class QueueRow:
    video_id: str
    url: str
    channel_title: str
    creator_type: str
    published_at: str
    year_bucket: str
    title: str
    duration_seconds: int
    transcript_priority_score: float
    priority_reason: str
    prior_creator_success_rate: float
    existing_candidate_window_count: int
    title_description_ticker_hit: int
    previous_attempt_status: str


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(c["name"]).lower() == col.lower() for c in cols)


def _seed_creator_type() -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not SEED_CSV.exists():
        return mapping
    with SEED_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("channel_name") or "").strip()
            cat = (row.get("category") or "").strip()
            if name:
                mapping[name.lower()] = cat or "unknown"
    return mapping


def _text_hit(title: str, desc: str) -> int:
    text = f"{title} {desc}".lower()
    return int(any(token in text for token in TICKER_HINTS | COMPANY_CUES))


def _is_short(title: str, duration_seconds: int) -> bool:
    return SHORT_CUE in title.lower() or (duration_seconds and duration_seconds < 90)


def _year_bucket(published_at: str) -> str:
    y = (published_at or "")[:4]
    return y if y.isdigit() else "unknown"


def _safe_int(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build_queue() -> tuple[list[QueueRow], dict[str, Any]]:
    if not DB_PATH.exists():
        return [], {"reason": f"missing_db:{DB_PATH}"}

    conn = _connect()
    try:
        if not _table_exists(conn, "raw_youtube_videos"):
            return [], {"reason": "missing_table:raw_youtube_videos"}

        creator_type_map = _seed_creator_type()
        has_duration = _col_exists(conn, "raw_youtube_videos", "duration_seconds")
        has_desc = _col_exists(conn, "raw_youtube_videos", "description")
        has_url = _col_exists(conn, "raw_youtube_videos", "url")

        base_cols = [
            "video_id",
            "channel_title",
            "published_at",
            "title",
            "seed_source",
        ]
        if has_desc:
            base_cols.append("description")
        if has_duration:
            base_cols.append("duration_seconds")
        if has_url:
            base_cols.append("url")
        query = f"""
            SELECT {", ".join(base_cols)}
            FROM raw_youtube_videos
            WHERE COALESCE(excluded_flag,0)=0
              AND published_at >= ?
              AND published_at <= ?
              AND COALESCE(video_id,'') != ''
        """
        raw_rows = conn.execute(query, (DATE_START, DATE_END)).fetchall()

        # transcript success / fail history
        success_ids: set[str] = set()
        latest_status: dict[str, str] = {}
        attempt_by_video: Counter[str] = Counter()
        if _table_exists(conn, "youtube_transcripts"):
            has_collected = _col_exists(conn, "youtube_transcripts", "collected_at")
            order_expr = "COALESCE(retrieved_at, collected_at, '')" if has_collected else "COALESCE(retrieved_at, '')"
            t_rows = conn.execute(
                f"""
                SELECT video_id, status, retrieved_at
                FROM youtube_transcripts
                WHERE COALESCE(video_id,'') != ''
                    ORDER BY {order_expr} DESC
                """
            ).fetchall()
            for r in t_rows:
                vid = str(r["video_id"])
                st = str(r["status"] or "")
                attempt_by_video[vid] += 1
                if vid not in latest_status:
                    latest_status[vid] = st
                if st == "available":
                    success_ids.add(vid)

        # candidate windows and accepted-event conversion by creator
        window_count: Counter[str] = Counter()
        creator_windows: Counter[str] = Counter()
        creator_accepted: Counter[str] = Counter()
        if _table_exists(conn, "transcript_candidate_windows"):
            w_rows = conn.execute(
                """
                SELECT tcw.video_id, COALESCE(tcw.accepted_event_flag,0) AS accepted_flag, rv.channel_title
                FROM transcript_candidate_windows tcw
                LEFT JOIN raw_youtube_videos rv ON rv.video_id = tcw.video_id
                """
            ).fetchall()
            for r in w_rows:
                vid = str(r["video_id"] or "")
                creator = str(r["channel_title"] or "unknown")
                if vid:
                    window_count[vid] += 1
                creator_windows[creator] += 1
                if int(r["accepted_flag"] or 0) == 1:
                    creator_accepted[creator] += 1

        # year coverage from accepted events
        year_accepted: Counter[str] = Counter()
        if _table_exists(conn, "transcript_recommendation_events"):
            y_rows = conn.execute(
                """
                SELECT substr(COALESCE(rv.published_at,''),1,4) AS y, COUNT(*) AS n
                FROM transcript_recommendation_events tre
                LEFT JOIN raw_youtube_videos rv ON rv.video_id = tre.video_id
                GROUP BY substr(COALESCE(rv.published_at,''),1,4)
                """
            ).fetchall()
            for r in y_rows:
                y = str(r["y"] or "unknown")
                year_accepted[y] = int(r["n"] or 0)

        dedupe: set[str] = set()
        out: list[QueueRow] = []
        for r in raw_rows:
            vid = str(r["video_id"] or "").strip()
            if not vid or vid in dedupe:
                continue
            dedupe.add(vid)

            if vid in success_ids:
                continue

            st = latest_status.get(vid, "")
            if st in PERMANENT_FAIL:
                continue

            title = str(r["title"] or "")
            desc = str(r["description"] if has_desc else "" or "")
            channel = str(r["channel_title"] or "unknown")
            creator_type = creator_type_map.get(channel.lower(), "unknown")
            duration = _safe_int(r["duration_seconds"] if has_duration else 0)
            url = str(r["url"] if has_url else "" or "")
            if not url:
                url = f"https://www.youtube.com/watch?v={vid}"

            yb = _year_bucket(str(r["published_at"] or ""))
            td_hit = _text_hit(title, desc)
            cwin = int(window_count.get(vid, 0))
            ctotal = int(creator_windows.get(channel, 0))
            cacc = int(creator_accepted.get(channel, 0))
            creator_sr = (cacc / ctotal) if ctotal else 0.0
            ycov = int(year_accepted.get(yb, 0))

            score = 0.0
            reasons: list[str] = []
            # optimize accepted recommendation events per dollar
            if cwin > 0:
                score += 35
                reasons.append("candidate_window_backlog")
            if td_hit:
                score += 25
                reasons.append("ticker_or_company_title_desc_hit")
            if creator_type == "stock_picker":
                score += 20
                reasons.append("stock_picker_creator")
            if creator_sr > 0:
                score += min(15, creator_sr * 30)
                reasons.append("high_creator_conversion")
            if ycov <= 5:
                score += 12
                reasons.append("low_year_coverage")
            elif ycov <= 20:
                score += 6
                reasons.append("mid_year_coverage")
            if st in TRANSIENT_FAIL:
                score -= 5
                reasons.append("recent_transient_failure")
            if attempt_by_video.get(vid, 0) == 0:
                score += 5
                reasons.append("no_prior_paid_attempt")
            if _is_short(title, duration):
                score -= 4
                reasons.append("shorts_deprioritized")
            else:
                score += 4
                reasons.append("non_shorts_preferred")
            if duration > 0 and duration > 3600:
                score -= 4
                reasons.append("very_long_video_deprioritized")

            out.append(
                QueueRow(
                    video_id=vid,
                    url=url,
                    channel_title=channel,
                    creator_type=creator_type,
                    published_at=str(r["published_at"] or ""),
                    year_bucket=yb,
                    title=title,
                    duration_seconds=duration,
                    transcript_priority_score=round(score, 3),
                    priority_reason=";".join(reasons),
                    prior_creator_success_rate=round(creator_sr, 4),
                    existing_candidate_window_count=cwin,
                    title_description_ticker_hit=td_hit,
                    previous_attempt_status=st or "none",
                )
            )

        out.sort(
            key=lambda x: (
                -x.transcript_priority_score,
                -x.existing_candidate_window_count,
                x.previous_attempt_status not in {"none", ""},
                x.channel_title.lower(),
                x.video_id,
            )
        )
        out = out[:MAX_ROWS]
        stats = {
            "source_rows": len(raw_rows),
            "queued_rows": len(out),
            "success_skipped": len(success_ids),
            "date_start": DATE_START,
            "date_end": DATE_END,
        }
        return out, stats
    finally:
        conn.close()


def write_outputs(rows: list[QueueRow], stats: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "video_id",
        "url",
        "channel_title",
        "creator_type",
        "published_at",
        "year_bucket",
        "title",
        "duration_seconds",
        "transcript_priority_score",
        "priority_reason",
        "prior_creator_success_rate",
        "existing_candidate_window_count",
        "title_description_ticker_hit",
        "previous_attempt_status",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow(row.__dict__)

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "# YouTube transcript expansion queue",
        "",
        f"Generated (UTC): `{now}`",
        f"Rows queued: `{len(rows)}`",
        f"Source rows in date range: `{stats.get('source_rows', 0)}`",
        f"Already-successful skipped: `{stats.get('success_skipped', 0)}`",
        f"Date range: `{stats.get('date_start', '')}` to `{stats.get('date_end', '')}`",
        "",
        "## Top 30 rows",
        "",
    ]
    for i, r in enumerate(rows[:30], start=1):
        lines.append(
            f"- `{i}` `{r.video_id}` score={r.transcript_priority_score} "
            f"creator=`{r.channel_title}` type=`{r.creator_type}` year={r.year_bucket} "
            f"candidate_windows={r.existing_candidate_window_count} "
            f"ticker_hit={r.title_description_ticker_hit} prev=`{r.previous_attempt_status}`"
        )
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    rows, stats = build_queue()
    write_outputs(rows, stats)
    print(f"WROTE_CSV={_display_path(OUT_CSV)}")
    print(f"WROTE_MD={_display_path(OUT_MD)}")
    print(f"QUEUE_ROWS={len(rows)}")


if __name__ == "__main__":
    main()
