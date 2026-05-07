from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db

TRANSCRIPT_EVENT_COLUMNS = [
    "video_id",
    "video_url",
    "channel_title",
    "published_at",
    "title",
    "ticker",
    "company_name",
    "stance",
    "detected_action",
    "actionability_score",
    "confidence_score",
    "confidence_label",
    "evidence_start_seconds",
    "evidence_end_seconds",
    "evidence_window",
    "classifier_version",
    "finbert_label",
    "finbert_positive_prob",
    "finbert_negative_prob",
    "finbert_neutral_prob",
]

TRANSCRIPT_CANDIDATE_WINDOW_COLUMNS = [
    "candidate_window_id",
    "video_id",
    "video_url",
    "channel_title",
    "published_at",
    "title",
    "ticker",
    "company_name",
    "mention_text",
    "evidence_start_seconds",
    "evidence_end_seconds",
    "evidence_window",
    "focused_action_text",
    "stance",
    "detected_action",
    "actionability_score",
    "confidence_score",
    "confidence_label",
    "accepted_event_flag",
    "transcript_event_id",
    "classifier_version",
    "exclusion_reason",
]

TRANSCRIPT_COVERAGE_COLUMNS = [
    "video_id",
    "video_url",
    "channel_title",
    "published_at",
    "title",
    "provider_name",
    "provider_version",
    "language_code",
    "is_generated",
    "status",
    "error_type",
    "segment_count",
    "full_text_sha256",
    "retrieved_at",
]

TRANSCRIPT_COVERAGE_BY_CREATOR_COLUMNS = [
    "channel_title",
    "channel_id",
    "videos_attempted",
    "transcripts_available",
    "disabled",
    "no_language",
    "unavailable",
    "request_blocked",
    "ip_blocked",
    "rate_limited",
    "error",
    "availability_rate",
]


def _write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> Path:
    if df.empty:
        df = pd.DataFrame(columns=columns)
    df.to_csv(path, index=False)
    return path


def export_transcript_events() -> dict[str, Path]:
    init_db()
    ensure_data_dirs()
    paths = {
        "transcript_recommendation_events": EXPORTS_DIR
        / "transcript_recommendation_events.csv",
        "transcript_candidate_windows": EXPORTS_DIR / "transcript_candidate_windows.csv",
        "transcript_coverage_report": EXPORTS_DIR / "transcript_coverage_report.csv",
        "transcript_coverage_by_creator": EXPORTS_DIR / "transcript_coverage_by_creator.csv",
    }
    with connect() as conn:
        event_df = pd.read_sql_query(
            """
            SELECT
              tre.video_id,
              y.url AS video_url,
              y.channel_title,
              y.published_at,
              y.title,
              tre.ticker,
              tre.company_name,
              tre.stance,
              tre.detected_action,
              tre.actionability_score,
              tre.confidence_score,
              tre.confidence_label,
              tre.evidence_start_seconds,
              tre.evidence_end_seconds,
              tre.evidence_window,
              tre.classifier_version,
              '' AS finbert_label,
              '' AS finbert_positive_prob,
              '' AS finbert_negative_prob,
              '' AS finbert_neutral_prob
            FROM transcript_recommendation_events tre
            LEFT JOIN raw_youtube_videos y
              ON y.video_id = tre.video_id
            ORDER BY y.published_at DESC, tre.video_id, tre.ticker
            """,
            conn,
        )
        window_df = pd.read_sql_query(
            """
            SELECT
              tcw.candidate_window_id,
              tcw.video_id,
              y.url AS video_url,
              y.channel_title,
              y.published_at,
              y.title,
              tcw.ticker,
              tcw.company_name,
              tcw.mention_text,
              tcw.evidence_start_seconds,
              tcw.evidence_end_seconds,
              tcw.evidence_window,
              tcw.focused_action_text,
              tcw.stance,
              tcw.detected_action,
              tcw.actionability_score,
              tcw.confidence_score,
              tcw.confidence_label,
              tcw.accepted_event_flag,
              tcw.transcript_event_id,
              tcw.classifier_version,
              tcw.exclusion_reason
            FROM transcript_candidate_windows tcw
            LEFT JOIN raw_youtube_videos y
              ON y.video_id = tcw.video_id
            ORDER BY y.published_at DESC, tcw.video_id, tcw.ticker, tcw.candidate_window_id
            """,
            conn,
        )
        coverage_df = pd.read_sql_query(
            """
            SELECT
              y.video_id,
              y.url AS video_url,
              y.channel_title,
              y.published_at,
              y.title,
              yt.provider_name,
              yt.provider_version,
              yt.language_code,
              yt.is_generated,
              yt.status,
              yt.error_type,
              yt.segment_count,
              yt.full_text_sha256,
              yt.retrieved_at
            FROM youtube_transcripts yt
            LEFT JOIN raw_youtube_videos y
              ON y.video_id = yt.video_id
            ORDER BY y.published_at DESC, yt.video_id
            """,
            conn,
        )
        creator_df = pd.read_sql_query(
            """
            SELECT
              y.channel_title,
              y.channel_id,
              COUNT(yt.video_id) AS videos_attempted,
              SUM(CASE WHEN yt.status = 'available' THEN 1 ELSE 0 END) AS transcripts_available,
              SUM(CASE WHEN yt.status = 'disabled' THEN 1 ELSE 0 END) AS disabled,
              SUM(CASE WHEN yt.status = 'no_language' THEN 1 ELSE 0 END) AS no_language,
              SUM(CASE WHEN yt.status = 'unavailable' THEN 1 ELSE 0 END) AS unavailable,
              SUM(CASE WHEN yt.status = 'request_blocked' THEN 1 ELSE 0 END) AS request_blocked,
              SUM(CASE WHEN yt.status = 'ip_blocked' THEN 1 ELSE 0 END) AS ip_blocked,
              SUM(CASE WHEN yt.status = 'rate_limited' THEN 1 ELSE 0 END) AS rate_limited,
              SUM(CASE WHEN yt.status = 'error' THEN 1 ELSE 0 END) AS error,
              ROUND(
                CAST(SUM(CASE WHEN yt.status = 'available' THEN 1 ELSE 0 END) AS REAL)
                / NULLIF(COUNT(yt.video_id), 0),
                3
              ) AS availability_rate
            FROM youtube_transcripts yt
            JOIN raw_youtube_videos y
              ON y.video_id = yt.video_id
            GROUP BY y.channel_title, y.channel_id
            ORDER BY availability_rate DESC, videos_attempted DESC, y.channel_title
            """,
            conn,
        )

    _write_csv(event_df, paths["transcript_recommendation_events"], TRANSCRIPT_EVENT_COLUMNS)
    _write_csv(window_df, paths["transcript_candidate_windows"], TRANSCRIPT_CANDIDATE_WINDOW_COLUMNS)
    _write_csv(coverage_df, paths["transcript_coverage_report"], TRANSCRIPT_COVERAGE_COLUMNS)
    _write_csv(
        creator_df,
        paths["transcript_coverage_by_creator"],
        TRANSCRIPT_COVERAGE_BY_CREATOR_COLUMNS,
    )
    return paths


TRANSCRIPT_TRAINING_WINDOW_COLUMNS = [
    "candidate_window_id",
    "video_id",
    "creator",
    "published_at",
    "ticker",
    "company_name",
    "window_start_time",
    "window_end_time",
    "evidence_text",
    "candidate_reason",
    "classifier_label",
    "recommendation_direction",
    "confidence",
    "exclusion_reason",
    "needs_manual_review",
]


def export_transcript_training_windows() -> Path:
    init_db()
    ensure_data_dirs()
    output_path = EXPORTS_DIR / "transcript_training_windows.csv"

    with connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT
              tcw.candidate_window_id,
              tcw.video_id,
              y.channel_title AS creator,
              y.published_at,
              tcw.ticker,
              tcw.company_name,
              tcw.evidence_start_seconds AS window_start_time,
              tcw.evidence_end_seconds AS window_end_time,
              tcw.evidence_window AS evidence_text,
              'transcript_rules_v2' AS candidate_reason,
              tcw.detected_action AS classifier_label,
              tcw.stance AS recommendation_direction,
              tcw.confidence_score AS confidence,
              tcw.exclusion_reason,
              CASE
                WHEN tcw.exclusion_reason IN (
                  'third_party_attribution', 'ambiguous_reference', 'retrospective_claim'
                ) THEN 1
                WHEN tcw.accepted_event_flag = 0
                  AND tcw.stance IN ('bullish', 'bearish')
                  AND tcw.actionability_score >= 2
                THEN 1
                ELSE 0
              END AS needs_manual_review
            FROM transcript_candidate_windows tcw
            LEFT JOIN raw_youtube_videos y
              ON y.video_id = tcw.video_id
            ORDER BY tcw.accepted_event_flag DESC, tcw.actionability_score DESC,
                     y.published_at DESC, tcw.ticker, tcw.candidate_window_id
            """,
            conn,
        )

    _write_csv(df, output_path, TRANSCRIPT_TRAINING_WINDOW_COLUMNS)
    return output_path
