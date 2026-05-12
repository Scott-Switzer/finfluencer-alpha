from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db
from .event_validation import DEFAULT_LABELED_PATH
from .expanded_robustness import (
    DEFAULT_EXPANDED_CLEAN_EVENTS,
    DEFAULT_EXPANDED_EVENT_STUDY_RESULTS,
)
from .reporting import DEFAULT_CLEAN_EVENTS_PATH, DEFAULT_EVENT_STUDY_RESULTS_PATH
from .transcript_availability_audit import (
    DEFAULT_AVAILABILITY_AUDIT_CSV_PATH,
    DEFAULT_AVAILABILITY_AUDIT_MD_PATH,
    build_transcript_availability_audit,
)

REPORTING_DIR = EXPORTS_DIR / "reporting"
TRANSCRIPTS_DIR = EXPORTS_DIR / "transcripts"
DEFAULT_DATA_DECISION_MD_PATH = REPORTING_DIR / "data_decision_report.md"
DEFAULT_DATA_DECISION_METRICS_CSV_PATH = REPORTING_DIR / "data_decision_metrics.csv"
DEFAULT_BROWSER_RECOVERY_AUDIT_CSV_PATH = (
    TRANSCRIPTS_DIR / "browser_transcript_recovery_audit.csv"
)
DEFAULT_SLOW_QUEUE_PATH = TRANSCRIPTS_DIR / "slow_youtube_transcript_queue.csv"
DATA_DECISION_COLUMNS = [
    "section",
    "metric",
    "value",
    "detail",
    "recommendation_category",
]


@dataclass(frozen=True)
class DataDecisionReportResult:
    markdown_path: Path
    metrics_csv_path: Path
    available_transcripts: int
    transcript_supported_events: int
    matched_market_data_events: int
    minimum_recommended_manual_validation_sample_size: int
    preferred_next_investment: str


def _clean(value: object) -> str:
    return str(value or "").strip()


def _scalar(conn: object, query: str, params: tuple[object, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] or 0)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_metrics(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=DATA_DECISION_COLUMNS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _distribution_rows(conn: object, *, group_by: str) -> list[tuple[str, int]]:
    if group_by == "creator":
        query = """
            SELECT COALESCE(rv.channel_title, rv.channel_id, 'unknown') AS label, COUNT(*) AS n
            FROM transcript_recommendation_events tre
            LEFT JOIN raw_youtube_videos rv ON rv.video_id = tre.video_id
            GROUP BY COALESCE(rv.channel_title, rv.channel_id, 'unknown')
            ORDER BY n DESC, label
        """
    elif group_by == "year":
        query = """
            SELECT SUBSTR(COALESCE(rv.published_at, ''), 1, 4) AS label, COUNT(*) AS n
            FROM transcript_recommendation_events tre
            LEFT JOIN raw_youtube_videos rv ON rv.video_id = tre.video_id
            GROUP BY SUBSTR(COALESCE(rv.published_at, ''), 1, 4)
            ORDER BY label
        """
    else:
        raise ValueError(f"Unsupported distribution grouping: {group_by}")
    return [(_clean(row["label"]) or "unknown", int(row["n"] or 0)) for row in conn.execute(query)]


def _row_count(path: Path) -> int:
    return len(_read_csv(path))


def _matched_market_rows(
    *,
    expanded_event_study_results_path: Path,
    baseline_event_study_results_path: Path,
) -> tuple[int, str]:
    if expanded_event_study_results_path.exists():
        return _row_count(expanded_event_study_results_path), str(expanded_event_study_results_path)
    if baseline_event_study_results_path.exists():
        return _row_count(baseline_event_study_results_path), str(baseline_event_study_results_path)
    return 0, "none"


def _clean_event_rows(
    *,
    expanded_clean_events_path: Path,
    baseline_clean_events_path: Path,
) -> tuple[int, str]:
    if expanded_clean_events_path.exists():
        return _row_count(expanded_clean_events_path), str(expanded_clean_events_path)
    if baseline_clean_events_path.exists():
        return _row_count(baseline_clean_events_path), str(baseline_clean_events_path)
    return 0, "none"


def _browser_audit_stats(path: Path) -> dict[str, float | int]:
    rows = _read_csv(path)
    audited = len(rows)
    visible = sum(1 for row in rows if _clean(row.get("transcript_visible")).lower() == "yes")
    recovered = sum(1 for row in rows if _clean(row.get("transcript_recovered")).lower() == "yes")
    success_rate = (visible / audited) if audited else 0.0
    return {
        "audited": audited,
        "visible": visible,
        "recovered": recovered,
        "success_rate": round(success_rate, 6),
    }


def _minimum_validation_sample_size(event_count: int) -> int:
    if event_count <= 0:
        return 0
    return min(event_count, max(50, math.ceil(event_count * 0.10)))


def _coverage_shortfall(total_videos: int, available_transcripts: int, target_rate: float = 0.75) -> int:
    target = math.ceil(total_videos * target_rate)
    return max(0, target - available_transcripts)


def _top_coverage_gaps(rows: list[dict[str, Any]], *, scope: str, label: str) -> list[tuple[str, float, int]]:
    scoped = [row for row in rows if row["scope"] == scope]
    return sorted(
        [
            (
                _clean(row[label]) or "unknown",
                float(row["transcript_coverage_pct"]),
                int(row["total_raw_youtube_videos"]) - int(row["available_transcripts"]),
            )
            for row in scoped
            if int(row["total_raw_youtube_videos"]) > 0
        ],
        key=lambda item: (item[1], -item[2], item[0]),
    )


def build_data_decision_report(
    *,
    database_url: str | None = None,
    output_md_path: Path = DEFAULT_DATA_DECISION_MD_PATH,
    output_metrics_csv_path: Path = DEFAULT_DATA_DECISION_METRICS_CSV_PATH,
    browser_audit_csv_path: Path = DEFAULT_BROWSER_RECOVERY_AUDIT_CSV_PATH,
    slow_queue_path: Path = DEFAULT_SLOW_QUEUE_PATH,
    expanded_event_study_results_path: Path = DEFAULT_EXPANDED_EVENT_STUDY_RESULTS,
    baseline_event_study_results_path: Path = DEFAULT_EVENT_STUDY_RESULTS_PATH,
    expanded_clean_events_path: Path = DEFAULT_EXPANDED_CLEAN_EVENTS,
    baseline_clean_events_path: Path = DEFAULT_CLEAN_EVENTS_PATH,
    labeled_validation_path: Path = DEFAULT_LABELED_PATH,
    audit_output_csv_path: Path = DEFAULT_AVAILABILITY_AUDIT_CSV_PATH,
    audit_output_md_path: Path = DEFAULT_AVAILABILITY_AUDIT_MD_PATH,
) -> DataDecisionReportResult:
    ensure_data_dirs()
    init_db(database_url=database_url)
    audit = build_transcript_availability_audit(
        database_url=database_url,
        output_csv_path=audit_output_csv_path,
        output_md_path=audit_output_md_path,
    )
    audit_rows = list(audit.rows)
    overall = next(row for row in audit_rows if row["scope"] == "overall")
    browser_stats = _browser_audit_stats(browser_audit_csv_path)
    pending_videos = _row_count(slow_queue_path)
    labeled_rows = _read_csv(labeled_validation_path)
    validation_rows_available = sum(
        1 for row in labeled_rows if _clean(row.get("is_true_recommendation"))
    )

    with connect(database_url=database_url) as conn:
        transcript_supported_events = _scalar(
            conn,
            "SELECT COUNT(*) FROM transcript_recommendation_events",
        )
        available_transcripts = _scalar(
            conn,
            "SELECT COUNT(*) FROM youtube_transcripts WHERE status = 'available'",
        )
        total_eligible_videos = _scalar(
            conn,
            "SELECT COUNT(*) FROM raw_youtube_videos WHERE COALESCE(excluded_flag, 0) = 0",
        )
        manual_validated_candidates = _scalar(
            conn,
            "SELECT COUNT(*) FROM recommendation_candidates WHERE COALESCE(manual_validated, 0) = 1",
        )
        x_posts_available = _scalar(conn, "SELECT COUNT(*) FROM raw_x_posts")
        events_by_creator = _distribution_rows(conn, group_by="creator")
        events_by_year = _distribution_rows(conn, group_by="year")

    transcript_coverage_rate = (
        available_transcripts / total_eligible_videos if total_eligible_videos else 0.0
    )
    audit_scope_transcript_coverage_rate = float(overall["transcript_coverage_pct"])
    matched_market_data_events, matched_source = _matched_market_rows(
        expanded_event_study_results_path=expanded_event_study_results_path,
        baseline_event_study_results_path=baseline_event_study_results_path,
    )
    clean_events, clean_source = _clean_event_rows(
        expanded_clean_events_path=expanded_clean_events_path,
        baseline_clean_events_path=baseline_clean_events_path,
    )
    unmatched_clean_events = max(0, clean_events - matched_market_data_events)
    top_creator, top_creator_events = events_by_creator[0] if events_by_creator else ("none", 0)
    top_creator_event_share = (
        top_creator_events / transcript_supported_events if transcript_supported_events else 0.0
    )
    creator_hhi = (
        sum((count / transcript_supported_events) ** 2 for _, count in events_by_creator)
        if transcript_supported_events
        else 0.0
    )
    minimum_validation_sample = _minimum_validation_sample_size(transcript_supported_events)
    additional_transcripts_needed = _coverage_shortfall(
        total_eligible_videos,
        available_transcripts,
    )
    weakest_creators = _top_coverage_gaps(audit_rows, scope="creator", label="creator")[:6]
    weakest_years = _top_coverage_gaps(audit_rows, scope="year", label="year")[:4]
    validation_gap = max(0, minimum_validation_sample - validation_rows_available)

    collect_more_transcripts = additional_transcripts_needed > 0
    manually_validate_events = validation_gap > 0 or manual_validated_candidates == 0
    improve_market_data = unmatched_clean_events > 0
    add_x_data = x_posts_available == 0
    ready_for_descriptive_claims = available_transcripts > 0 and transcript_supported_events > 0
    not_ready_for_causal_claims = (
        manually_validate_events
        or improve_market_data
        or collect_more_transcripts
        or add_x_data
    )
    if manually_validate_events:
        preferred_next_investment = "manually_validate_events"
    elif collect_more_transcripts:
        preferred_next_investment = "collect_more_transcripts"
    elif improve_market_data:
        preferred_next_investment = "improve_market_data"
    elif add_x_data:
        preferred_next_investment = "add_x_data"
    else:
        preferred_next_investment = "ready_for_descriptive_claims"

    metrics_rows: list[dict[str, Any]] = [
        {
            "section": "sample",
            "metric": "total_eligible_videos",
            "value": total_eligible_videos,
            "detail": "non-excluded local database rows",
            "recommendation_category": "",
        },
        {
            "section": "sample",
            "metric": "available_transcripts",
            "value": available_transcripts,
            "detail": "youtube_transcripts status=available",
            "recommendation_category": "",
        },
        {
            "section": "sample",
            "metric": "transcript_coverage_rate",
            "value": round(transcript_coverage_rate, 6),
            "detail": "available_transcripts / total_eligible_videos",
            "recommendation_category": "",
        },
        {
            "section": "coverage",
            "metric": "audit_scope_transcript_coverage_rate_2020_2023",
            "value": round(audit_scope_transcript_coverage_rate, 6),
            "detail": "availability audit scope used for creator/year representativeness checks",
            "recommendation_category": "collect_more_transcripts",
        },
        {
            "section": "sample",
            "metric": "pending_videos",
            "value": pending_videos,
            "detail": str(slow_queue_path),
            "recommendation_category": "collect_more_transcripts",
        },
        {
            "section": "browser_recovery",
            "metric": "browser_audited_recoverable_videos",
            "value": int(browser_stats["visible"]),
            "detail": str(browser_audit_csv_path),
            "recommendation_category": "collect_more_transcripts",
        },
        {
            "section": "browser_recovery",
            "metric": "browser_recovery_success_rate",
            "value": browser_stats["success_rate"],
            "detail": (
                f"recovered={int(browser_stats['recovered'])}; "
                f"visible={int(browser_stats['visible'])}; "
                f"audited={int(browser_stats['audited'])}"
            ),
            "recommendation_category": "collect_more_transcripts",
        },
        {
            "section": "events",
            "metric": "matched_market_events",
            "value": matched_market_data_events,
            "detail": matched_source,
            "recommendation_category": "improve_market_data",
        },
        {
            "section": "events",
            "metric": "unmatched_clean_events",
            "value": unmatched_clean_events,
            "detail": clean_source,
            "recommendation_category": "improve_market_data",
        },
        {
            "section": "concentration",
            "metric": "top_creator_event_share",
            "value": round(top_creator_event_share, 6),
            "detail": f"{top_creator}:{top_creator_events}",
            "recommendation_category": "collect_more_transcripts",
        },
        {
            "section": "concentration",
            "metric": "creator_event_hhi",
            "value": round(creator_hhi, 6),
            "detail": "sum of squared creator event shares",
            "recommendation_category": "collect_more_transcripts",
        },
        {
            "section": "validation",
            "metric": "validation_rows_available",
            "value": validation_rows_available,
            "detail": str(labeled_validation_path),
            "recommendation_category": "manually_validate_events",
        },
        {
            "section": "validation",
            "metric": "minimum_recommended_manual_validation_sample_size",
            "value": minimum_validation_sample,
            "detail": "max(50, ceil(10% of transcript-supported events))",
            "recommendation_category": "manually_validate_events",
        },
        {
            "section": "platform",
            "metric": "x_posts_available",
            "value": x_posts_available,
            "detail": "raw_x_posts rows in the local database",
            "recommendation_category": "add_x_data",
        },
        {
            "section": "planning",
            "metric": "additional_transcripts_to_reach_75pct_coverage",
            "value": additional_transcripts_needed,
            "detail": "material coverage improvement threshold",
            "recommendation_category": "collect_more_transcripts",
        },
    ]
    metrics_rows.extend(
        {
            "section": "events_by_creator",
            "metric": creator,
            "value": count,
            "detail": "transcript-supported event count",
            "recommendation_category": "",
        }
        for creator, count in events_by_creator
    )
    metrics_rows.extend(
        {
            "section": "events_by_year",
            "metric": year,
            "value": count,
            "detail": "transcript-supported event count",
            "recommendation_category": "",
        }
        for year, count in events_by_year
    )
    recommendation_flags = [
        ("collect_more_transcripts", collect_more_transcripts),
        ("manually_validate_events", manually_validate_events),
        ("improve_market_data", improve_market_data),
        ("add_x_data", add_x_data),
        ("ready_for_descriptive_claims", ready_for_descriptive_claims),
        ("not_ready_for_causal_claims", not_ready_for_causal_claims),
    ]
    metrics_rows.extend(
        {
            "section": "recommendation",
            "metric": category,
            "value": int(enabled),
            "detail": "1 means currently recommended or supported",
            "recommendation_category": category,
        }
        for category, enabled in recommendation_flags
    )
    _write_metrics(output_metrics_csv_path, metrics_rows)

    weakest_creator_text = ", ".join(
        f"{creator} ({coverage:.1%} coverage, {missing} missing)"
        for creator, coverage, missing in weakest_creators
    ) or "none"
    weakest_year_text = ", ".join(
        f"{year} ({coverage:.1%} coverage, {missing} missing)"
        for year, coverage, missing in weakest_years
    ) or "none"
    recommendation_text = ", ".join(
        category for category, enabled in recommendation_flags if enabled
    )
    recoverable_candidate_label = (
        "candidate" if int(browser_stats["visible"]) == 1 else "candidates"
    )
    lines = [
        "# Data Decision Report",
        "",
        f"- Eligible videos: {total_eligible_videos}",
        f"- Available transcripts: {available_transcripts}",
        f"- Overall local transcript coverage rate: {transcript_coverage_rate:.1%}",
        f"- 2020-2023 audit-scope transcript coverage rate: {audit_scope_transcript_coverage_rate:.1%}",
        f"- Transcript-supported events: {transcript_supported_events}",
        f"- Market-data matched events: {matched_market_data_events}",
        f"- Browser-audited recoverable videos: {int(browser_stats['visible'])}",
        f"- Browser recovery success rate: {float(browser_stats['success_rate']):.1%}",
        "",
        "## 1. What conclusions can be made now?",
        "",
        "- Descriptive claims about the transcript-available YouTube sample are supportable.",
        f"- The study currently observes {transcript_supported_events} transcript-supported recommendation events and {matched_market_data_events} market-data matched events.",
        "- The browser audit can support a bounded manual recovery path when transcript buttons are publicly visible.",
        "",
        "## 2. What conclusions are not defensible?",
        "",
        "- Representative claims about all eligible videos remain weak while transcript missingness is material.",
        "- Causal claims that recommendations moved prices are not defensible before stronger validation and market-data completeness.",
        "- Cross-platform YouTube/X claims are not defensible while the local X post count remains thin or zero.",
        "",
        "## 3. Which missing videos are most important to recover?",
        "",
        "- Prioritize the queue rows concentrated in 2022-2023, especially weak-coverage creators and stock-recommendation-like titles.",
        f"- Browser-audited recoverable videos currently provide {int(browser_stats['visible'])} concrete manual recovery {recoverable_candidate_label}.",
        "",
        "## 4. Which creators most threaten representativeness?",
        "",
        f"- {weakest_creator_text}",
        f"- The top creator currently contributes {top_creator_events} events ({top_creator_event_share:.1%}); creator HHI is {creator_hhi:.3f}.",
        "",
        "## 5. Which years most threaten representativeness?",
        "",
        f"- {weakest_year_text}",
        "",
        "## 6. How many additional transcripts would materially improve the study?",
        "",
        f"- Recovering about {additional_transcripts_needed} additional transcripts would lift the full eligible local video set to 75% transcript coverage.",
        "",
        "## 7. Which is more valuable: more transcripts, manual validation, X data, or Bloomberg refinement?",
        "",
        f"- Highest next-value category: **{preferred_next_investment}**.",
        f"- Active recommendation categories: {recommendation_text}.",
        "",
        "## 8. What is the minimum next data target before finalizing the paper?",
        "",
        f"- Reach at least {minimum_validation_sample} manually reviewed recommendation events or candidate labels; {validation_rows_available} reviewed rows are currently available.",
        "",
    ]
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text("\n".join(lines), encoding="utf-8")
    return DataDecisionReportResult(
        markdown_path=output_md_path,
        metrics_csv_path=output_metrics_csv_path,
        available_transcripts=available_transcripts,
        transcript_supported_events=transcript_supported_events,
        matched_market_data_events=matched_market_data_events,
        minimum_recommended_manual_validation_sample_size=minimum_validation_sample,
        preferred_next_investment=preferred_next_investment,
    )
