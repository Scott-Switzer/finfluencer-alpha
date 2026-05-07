from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db
from .transcript_vendor import build_transcript_coverage_bias_report

CAPSTONE_SUMMARY_DIR = EXPORTS_DIR / "capstone_summary_tables"


@dataclass(frozen=True)
class CapstoneSummaryResult:
    output_dir: Path
    paths: dict[str, Path]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _scalar(conn, query: str, params: tuple[object, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] or 0)


def _metadata_universe_rows(conn) -> list[dict[str, object]]:
    total = _scalar(conn, "SELECT COUNT(*) FROM raw_youtube_videos")
    excluded = _scalar(
        conn,
        "SELECT COUNT(*) FROM raw_youtube_videos WHERE COALESCE(excluded_flag, 0) = 1",
    )
    creators = _scalar(
        conn,
        """
        SELECT COUNT(DISTINCT channel_id)
        FROM raw_youtube_videos
        WHERE COALESCE(excluded_flag, 0) = 0
        """,
    )
    rows = [
        {"section": "metadata_universe", "label": "total_raw_videos", "value": total},
        {"section": "metadata_universe", "label": "excluded_videos", "value": excluded},
        {"section": "metadata_universe", "label": "non_excluded_videos", "value": total - excluded},
        {"section": "metadata_universe", "label": "creators_represented", "value": creators},
    ]
    for row in conn.execute(
        """
        SELECT COALESCE(creator_category, 'unknown') AS category, COUNT(*) AS n
        FROM raw_youtube_videos
        WHERE COALESCE(excluded_flag, 0) = 0
        GROUP BY COALESCE(creator_category, 'unknown')
        ORDER BY n DESC, category
        """
    ).fetchall():
        rows.append(
            {
                "section": "videos_by_creator_category",
                "label": row["category"],
                "value": row["n"],
            }
        )
    return rows


def _transcript_collection_rows(conn) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    queries = [
        (
            "transcripts_by_source",
            """
            SELECT COALESCE(transcript_source, 'unknown') AS label, COUNT(*) AS n
            FROM youtube_transcripts
            WHERE status = 'available' AND COALESCE(full_text, '') != ''
            GROUP BY COALESCE(transcript_source, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
        (
            "transcripts_by_provider",
            """
            SELECT COALESCE(provider_name, 'unknown') AS label, COUNT(*) AS n
            FROM youtube_transcripts
            WHERE status = 'available' AND COALESCE(full_text, '') != ''
            GROUP BY COALESCE(provider_name, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
        (
            "transcripts_by_creator",
            """
            SELECT COALESCE(y.channel_title, 'unknown') AS label, COUNT(*) AS n
            FROM youtube_transcripts yt
            LEFT JOIN raw_youtube_videos y ON y.video_id = yt.video_id
            WHERE yt.status = 'available' AND COALESCE(yt.full_text, '') != ''
            GROUP BY COALESCE(y.channel_title, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
        (
            "transcripts_by_creator_category",
            """
            SELECT COALESCE(y.creator_category, 'unknown') AS label, COUNT(*) AS n
            FROM youtube_transcripts yt
            LEFT JOIN raw_youtube_videos y ON y.video_id = yt.video_id
            WHERE yt.status = 'available' AND COALESCE(yt.full_text, '') != ''
            GROUP BY COALESCE(y.creator_category, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
        (
            "unavailable_failed_counts",
            """
            SELECT COALESCE(status, 'unknown') AS label, COUNT(*) AS n
            FROM youtube_transcripts
            WHERE status != 'available' OR COALESCE(full_text, '') = ''
            GROUP BY COALESCE(status, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
        (
            "provenance_fields",
            """
            SELECT
              COALESCE(transcript_source, 'unknown') || ' | ' ||
              COALESCE(provider_name, 'unknown') || ' | ' ||
              COALESCE(retrieval_method, 'unknown') || ' | asr=' ||
              COALESCE(CAST(is_asr_generated AS TEXT), 'unknown') AS label,
              COUNT(*) AS n
            FROM youtube_transcripts
            GROUP BY label
            ORDER BY n DESC, label
            """,
        ),
    ]
    for section, query in queries:
        for row in conn.execute(query).fetchall():
            rows.append({"section": section, "label": row["label"], "count": row["n"]})
    return rows


def _recommendation_event_rows(conn) -> list[dict[str, object]]:
    rows = [
        {
            "section": "event_counts",
            "label": "candidate_windows",
            "count": _scalar(conn, "SELECT COUNT(*) FROM transcript_candidate_windows"),
        },
        {
            "section": "event_counts",
            "label": "accepted_recommendation_events",
            "count": _scalar(conn, "SELECT COUNT(*) FROM transcript_recommendation_events"),
        },
        {
            "section": "event_counts",
            "label": "rejected_or_excluded_windows",
            "count": _scalar(
                conn,
                """
                SELECT COUNT(*)
                FROM transcript_candidate_windows
                WHERE COALESCE(accepted_event_flag, 0) = 0
                """,
            ),
        },
    ]
    queries = [
        (
            "rejected_excluded_classifications",
            """
            SELECT COALESCE(exclusion_reason, 'not_excluded') AS label, COUNT(*) AS n
            FROM transcript_candidate_windows
            WHERE COALESCE(accepted_event_flag, 0) = 0
            GROUP BY COALESCE(exclusion_reason, 'not_excluded')
            ORDER BY n DESC, label
            """,
        ),
        (
            "accepted_events_by_ticker",
            """
            SELECT ticker AS label, COUNT(*) AS n
            FROM transcript_recommendation_events
            GROUP BY ticker
            ORDER BY n DESC, label
            """,
        ),
        (
            "accepted_events_by_creator",
            """
            SELECT COALESCE(y.channel_title, 'unknown') AS label, COUNT(*) AS n
            FROM transcript_recommendation_events tre
            LEFT JOIN raw_youtube_videos y ON y.video_id = tre.video_id
            GROUP BY COALESCE(y.channel_title, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
        (
            "accepted_events_by_direction",
            """
            SELECT COALESCE(stance, 'unknown') AS label, COUNT(*) AS n
            FROM transcript_recommendation_events
            GROUP BY COALESCE(stance, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
        (
            "accepted_events_by_confidence",
            """
            SELECT COALESCE(confidence_label, 'unknown') AS label, COUNT(*) AS n
            FROM transcript_recommendation_events
            GROUP BY COALESCE(confidence_label, 'unknown')
            ORDER BY n DESC, label
            """,
        ),
    ]
    for section, query in queries:
        for row in conn.execute(query).fetchall():
            rows.append({"section": section, "label": row["label"], "count": row["n"]})
    return rows


def _coverage_bias_rows() -> list[dict[str, object]]:
    report = build_transcript_coverage_bias_report()
    rows: list[dict[str, object]] = []
    selected_sections = {
        "creator": "covered_vs_uncovered_by_creator",
        "creator_category": "covered_vs_uncovered_by_category",
        "year": "covered_vs_uncovered_by_year",
        "title_keyword_signal": "covered_vs_uncovered_by_title_keyword_signal",
        "view_count_bucket": "covered_vs_uncovered_by_view_count_bucket",
    }
    for key, section in selected_sections.items():
        for row in report[key]:
            rows.append(
                {
                    "section": section,
                    "label": row[key],
                    "covered": row["covered"],
                    "uncovered": row["uncovered"],
                    "total": row["total"],
                    "coverage_rate": row["coverage_rate"],
                }
            )
    return rows


def _paper_methods_text(conn) -> str:
    metadata_videos = _scalar(conn, "SELECT COUNT(*) FROM raw_youtube_videos")
    excluded = _scalar(
        conn,
        "SELECT COUNT(*) FROM raw_youtube_videos WHERE COALESCE(excluded_flag, 0) = 1",
    )
    creators = _scalar(
        conn,
        """
        SELECT COUNT(DISTINCT channel_id)
        FROM raw_youtube_videos
        WHERE COALESCE(excluded_flag, 0) = 0
        """,
    )
    transcript_count = _scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM youtube_transcripts
        WHERE status = 'available' AND COALESCE(full_text, '') != ''
        """,
    )
    source_rows = conn.execute(
        """
        SELECT COALESCE(transcript_source, 'unknown') AS source, COUNT(*) AS n
        FROM youtube_transcripts
        WHERE status = 'available' AND COALESCE(full_text, '') != ''
        GROUP BY COALESCE(transcript_source, 'unknown')
        ORDER BY n DESC, source
        """
    ).fetchall()
    transcript_sources = ", ".join(f"{row['source']}={row['n']}" for row in source_rows) or "none"
    candidate_windows = _scalar(conn, "SELECT COUNT(*) FROM transcript_candidate_windows")
    accepted_events = _scalar(conn, "SELECT COUNT(*) FROM transcript_recommendation_events")
    rejected = _scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM transcript_candidate_windows
        WHERE COALESCE(accepted_event_flag, 0) = 0
        """,
    )
    return (
        "The YouTube metadata universe contains "
        f"{metadata_videos} collected videos from {creators} non-excluded creator channels. "
        f"{excluded} videos were excluded before transcript collection because of documented "
        "resolution issues. Transcript evidence is available for "
        f"{transcript_count} videos, with transcript sources recorded as {transcript_sources}. "
        "The transcript classifier generated "
        f"{candidate_windows} ticker-centered candidate windows and "
        f"{accepted_events} accepted transcript-level recommendation events; "
        f"{rejected} candidate windows were rejected or excluded by rule labels. "
        "The main limitation is transcript coverage bias: videos without available provider or "
        "native captions remain underrepresented, so event counts should be interpreted as "
        "caption-available recommendation evidence rather than complete creator activity."
    )


def export_capstone_summary(output_dir: Path | None = None) -> CapstoneSummaryResult:
    init_db()
    ensure_data_dirs()
    output_dir = output_dir or CAPSTONE_SUMMARY_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "metadata_universe_summary": output_dir / "metadata_universe_summary.csv",
        "transcript_collection_summary": output_dir / "transcript_collection_summary.csv",
        "recommendation_event_summary": output_dir / "recommendation_event_summary.csv",
        "coverage_bias_summary": output_dir / "coverage_bias_summary.csv",
        "paper_methods_numbers": output_dir / "paper_methods_numbers.txt",
    }
    with connect() as conn:
        _write_rows(
            paths["metadata_universe_summary"],
            ["section", "label", "value"],
            _metadata_universe_rows(conn),
        )
        _write_rows(
            paths["transcript_collection_summary"],
            ["section", "label", "count"],
            _transcript_collection_rows(conn),
        )
        _write_rows(
            paths["recommendation_event_summary"],
            ["section", "label", "count"],
            _recommendation_event_rows(conn),
        )
        methods_text = _paper_methods_text(conn)

    _write_rows(
        paths["coverage_bias_summary"],
        ["section", "label", "covered", "uncovered", "total", "coverage_rate"],
        _coverage_bias_rows(),
    )
    paths["paper_methods_numbers"].write_text(methods_text + "\n", encoding="utf-8")
    return CapstoneSummaryResult(output_dir=output_dir, paths=paths)
