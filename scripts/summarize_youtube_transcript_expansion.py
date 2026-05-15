#!/usr/bin/env python3
"""Summarize transcript expansion results after overnight run."""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "finfluencer_alpha.db"
OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
OUT_MD = OUT_DIR / "54_youtube_transcript_expansion_summary.md"
OUT_CSV = OUT_DIR / "54_youtube_transcript_expansion_summary.csv"
CKPT = OUT_DIR / "53_youtube_apify_overnight_checkpoint.json"


def _q1(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int((row[0] if row else 0) or 0)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        OUT_MD.write_text("# YouTube transcript expansion summary\n\nNo SQLite database found.\n", encoding="utf-8")
        with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["metric", "value"])
            w.writeheader()
            w.writerow({"metric": "error", "value": "missing_db"})
        print(f"WROTE_MD={OUT_MD.relative_to(ROOT)}")
        print(f"WROTE_CSV={OUT_CSV.relative_to(ROOT)}")
        return

    ck = {}
    if CKPT.exists():
        try:
            ck = json.loads(CKPT.read_text(encoding="utf-8"))
        except Exception:
            ck = {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ending_transcripts = _q1(
            conn,
            "SELECT COUNT(*) FROM youtube_transcripts WHERE status='available' AND COALESCE(full_text,'') != ''",
        )
        ending_accepted = _q1(conn, "SELECT COUNT(*) FROM transcript_recommendation_events")
        beginning_transcripts = int(ck.get("beginning_transcript_count") or ending_transcripts)
        beginning_accepted = int(ck.get("beginning_accepted_events") or ending_accepted)
        new_transcripts = max(0, ending_transcripts - beginning_transcripts)
        new_accepted = max(0, ending_accepted - beginning_accepted)
        conversion = (new_accepted / new_transcripts) if new_transcripts else 0.0

        by_creator = conn.execute(
            """
            SELECT rv.channel_title AS creator, COUNT(*) AS n
            FROM transcript_recommendation_events tre
            JOIN raw_youtube_videos rv ON rv.video_id = tre.video_id
            GROUP BY rv.channel_title
            ORDER BY n DESC
            LIMIT 10
            """
        ).fetchall()
        by_year = conn.execute(
            """
            SELECT substr(rv.published_at,1,4) AS y, COUNT(*) AS n
            FROM transcript_recommendation_events tre
            JOIN raw_youtube_videos rv ON rv.video_id = tre.video_id
            GROUP BY substr(rv.published_at,1,4)
            ORDER BY y
            """
        ).fetchall()
        top_tickers = conn.execute(
            """
            SELECT ticker, COUNT(*) AS n
            FROM transcript_recommendation_events
            GROUP BY ticker
            ORDER BY n DESC
            LIMIT 10
            """
        ).fetchall()
    finally:
        conn.close()

    metrics = [
        ("beginning_transcript_count", beginning_transcripts),
        ("ending_transcript_count", ending_transcripts),
        ("new_transcripts_imported", new_transcripts),
        ("beginning_accepted_recommendation_events", beginning_accepted),
        ("ending_accepted_recommendation_events", ending_accepted),
        ("new_accepted_recommendation_events", new_accepted),
        ("conversion_rate_transcript_to_accepted_event", round(conversion, 6)),
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "value"], lineterminator="\n")
        w.writeheader()
        for k, v in metrics:
            w.writerow({"metric": k, "value": v})

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "# YouTube transcript expansion summary",
        "",
        f"Generated (UTC): `{now}`",
        "",
        "## Core counts",
        "",
    ]
    for k, v in metrics:
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Coverage by creator (top 10 accepted-event counts)",
        "",
    ]
    for r in by_creator:
        lines.append(f"- `{r['creator']}`: `{r['n']}`")
    lines += [
        "",
        "## Coverage by year (accepted-event counts)",
        "",
    ]
    for r in by_year:
        lines.append(f"- `{r['y']}`: `{r['n']}`")
    lines += [
        "",
        "## Top tickers by accepted events",
        "",
    ]
    for r in top_tickers:
        lines.append(f"- `{r['ticker']}`: `{r['n']}`")

    sample_ok = "yes" if ending_accepted >= 150 else "not yet"
    bottlenecks = []
    if new_transcripts == 0:
        bottlenecks.append("transcript import throughput")
    if conversion < 0.05:
        bottlenecks.append("low transcript->accepted-event conversion")
    if not bottlenecks:
        bottlenecks.append("none obvious from aggregate metrics")
    lines += [
        "",
        "## Remaining bottlenecks",
        "",
        *(f"- {b}" for b in bottlenecks),
        "",
        f"Sample appears large enough for statistical analysis: `{sample_ok}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE_MD={OUT_MD.relative_to(ROOT)}")
    print(f"WROTE_CSV={OUT_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
