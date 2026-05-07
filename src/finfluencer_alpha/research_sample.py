from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .classify import classify_text, should_create_candidate
from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db
from .exports import MANUAL_VALIDATION_COLUMNS
from .ticker_extract import extract_tickers

RESEARCH_SAMPLE_COLUMNS = [
    "event_id",
    "platform",
    "source_id",
    "content_url",
    "creator_handle",
    "creator_category",
    "published_at",
    "ticker",
    "detected_direction",
    "detected_action",
    "actionability_score",
    "confidence_score",
    "confidence_label",
    "source_layer",
    "evidence_snippet",
    "current_view_count",
    "current_like_count",
    "current_comment_count",
]


def confidence_label_for_event(
    source_layer: str,
    classifier_confidence: float | None,
    actionability_score: int | None,
) -> str:
    confidence = float(classifier_confidence or 0)
    score = int(actionability_score or 0)
    if source_layer == "comment_context":
        return "exclude"
    if source_layer in {"title", "description"}:
        return "medium" if confidence >= 0.70 and score >= 3 else "low"
    if source_layer in {"transcript", "manual", "x_text"}:
        if confidence >= 0.75 and score >= 3:
            return "high"
        return "medium" if score >= 2 else "low"
    return "low"


def source_layer_for_youtube(title: str | None, description: str | None, ticker: str) -> str:
    title_text = title or ""
    title_result = classify_text(title_text)
    title_has_ticker = any(mention.ticker == ticker for mention in extract_tickers(title_text))
    title_has_ticker = title_has_ticker or bool(
        re.search(rf"(?<![A-Za-z0-9])\$?{re.escape(ticker)}(?![A-Za-z])", title_text)
    )
    if title_has_ticker and should_create_candidate(title_result, has_ticker=True):
        return "title"
    return "description"


def _trim(value: str | None, limit: int = 500) -> str:
    text = (value or "").strip()
    return text[:limit]


def _event_rows() -> list[dict[str, object]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              rc.candidate_id,
              rc.platform,
              rc.source_id,
              rc.creator_handle,
              rc.ticker,
              rc.event_time,
              rc.stance,
              rc.actionability_score,
              rc.recommendation_type,
              rc.classifier_confidence,
              COALESCE(c.category, ct.initial_category) AS creator_category,
              x.text AS post_text,
              x.url AS post_url,
              x.reply_count AS current_reply_count,
              x.repost_count AS current_repost_count,
              x.quote_count AS current_quote_count,
              x.impression_count AS current_impression_count,
              y.video_id,
              y.channel_title,
              y.title,
              y.description,
              y.url AS video_url,
              y.current_view_count,
              y.current_like_count,
              y.current_comment_count,
              MAX(tm.mention_text) AS mention_text,
              MAX(tm.confidence) AS ticker_confidence
            FROM recommendation_candidates rc
            LEFT JOIN raw_x_posts x
              ON rc.platform = 'x' AND rc.source_id = x.post_id
            LEFT JOIN raw_youtube_videos y
              ON rc.platform = 'youtube' AND rc.source_id = y.video_id
            LEFT JOIN creators c
              ON c.platform = rc.platform AND c.handle = rc.creator_handle
            LEFT JOIN creator_taxonomy ct
              ON ct.platform = rc.platform AND ct.handle_or_channel = rc.creator_handle
            LEFT JOIN ticker_mentions tm
              ON tm.platform = rc.platform
              AND tm.source_id = rc.source_id
              AND tm.ticker = rc.ticker
            GROUP BY rc.candidate_id
            ORDER BY rc.event_time DESC, rc.platform, rc.creator_handle, rc.ticker
            """
        ).fetchall()

    records: list[dict[str, object]] = []
    for row in rows:
        platform = row["platform"]
        source_layer = (
            "x_text"
            if platform == "x"
            else source_layer_for_youtube(row["title"], row["description"], row["ticker"])
        )
        label = confidence_label_for_event(
            source_layer,
            row["classifier_confidence"],
            row["actionability_score"],
        )
        event_id = f"{platform}:{row['source_id']}:{row['ticker']}"
        evidence = row["title"] if source_layer == "title" else row["mention_text"]
        if not evidence:
            evidence = row["post_text"] if platform == "x" else row["title"] or row["description"]
        records.append(
            {
                "event_id": event_id,
                "platform": platform,
                "source_id": row["source_id"],
                "content_url": row["post_url"] if platform == "x" else row["video_url"],
                "creator_handle": row["creator_handle"],
                "creator_category": row["creator_category"],
                "published_at": row["event_time"],
                "ticker": row["ticker"],
                "detected_direction": row["stance"],
                "detected_action": row["recommendation_type"],
                "actionability_score": row["actionability_score"],
                "confidence_score": row["classifier_confidence"],
                "confidence_label": label,
                "source_layer": source_layer,
                "evidence_snippet": _trim(evidence),
                "current_view_count": row["current_view_count"],
                "current_like_count": row["current_like_count"],
                "current_comment_count": row["current_comment_count"],
                "video_id": row["video_id"] if platform == "youtube" else "",
                "post_id": row["source_id"] if platform == "x" else "",
                "video_url": row["video_url"] if platform == "youtube" else "",
                "post_url": row["post_url"] if platform == "x" else "",
                "channel_title": row["channel_title"] if platform == "youtube" else "",
                "x_handle": row["creator_handle"] if platform == "x" else "",
                "title": row["title"] if platform == "youtube" else "",
                "post_text": row["post_text"] if platform == "x" else "",
                "company_name": "",
                "transcript_timestamp_start": "",
                "transcript_timestamp_end": "",
                "manual_label": "",
                "manual_direction": "",
                "manual_action": "",
                "manual_confidence": "",
                "manual_notes": "",
                "reviewer": "",
                "reviewed_at": "",
            }
        )
    return records


def export_research_sample() -> dict[str, Path]:
    init_db()
    ensure_data_dirs()
    rows = _event_rows()
    research_df = pd.DataFrame(rows, columns=RESEARCH_SAMPLE_COLUMNS)
    manual_df = pd.DataFrame(
        [
            {
                "event_id": row["event_id"],
                "platform": row["platform"],
                "video_id": row["video_id"],
                "post_id": row["post_id"],
                "video_url": row["video_url"],
                "post_url": row["post_url"],
                "channel_title": row["channel_title"],
                "x_handle": row["x_handle"],
                "creator_category": row["creator_category"],
                "published_at": row["published_at"],
                "title": row["title"],
                "post_text": row["post_text"],
                "ticker": row["ticker"],
                "company_name": row["company_name"],
                "detected_action": row["detected_action"],
                "detected_direction": row["detected_direction"],
                "confidence_score": row["confidence_score"],
                "confidence_label": row["confidence_label"],
                "source_layer": row["source_layer"],
                "evidence_snippet": row["evidence_snippet"],
                "transcript_timestamp_start": row["transcript_timestamp_start"],
                "transcript_timestamp_end": row["transcript_timestamp_end"],
                "current_view_count": row["current_view_count"],
                "current_like_count": row["current_like_count"],
                "current_comment_count": row["current_comment_count"],
                "manual_label": row["manual_label"],
                "manual_direction": row["manual_direction"],
                "manual_action": row["manual_action"],
                "manual_confidence": row["manual_confidence"],
                "manual_notes": row["manual_notes"],
                "reviewer": row["reviewer"],
                "reviewed_at": row["reviewed_at"],
            }
            for row in rows
        ],
        columns=MANUAL_VALIDATION_COLUMNS,
    )
    paths = {
        "research_candidate_events": EXPORTS_DIR / "research_candidate_events.csv",
        "manual_validation_events": EXPORTS_DIR / "manual_validation_events.csv",
    }
    research_df.to_csv(paths["research_candidate_events"], index=False)
    manual_df.to_csv(paths["manual_validation_events"], index=False)
    return paths
