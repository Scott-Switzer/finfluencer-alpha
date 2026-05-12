from __future__ import annotations

import csv
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
DEFAULT_RESEARCH_READINESS_MD_PATH = REPORTING_DIR / "research_readiness_report.md"
DEFAULT_RESEARCH_READINESS_METRICS_CSV_PATH = REPORTING_DIR / "research_readiness_metrics.csv"
RESEARCH_READINESS_COLUMNS = ["section", "metric", "value", "readiness", "detail"]


@dataclass(frozen=True)
class ResearchReadinessResult:
    markdown_path: Path
    metrics_csv_path: Path
    overall_readiness: str
    transcript_supported_events: int
    matched_market_data_events: int


def _clean(value: object) -> str:
    return str(value or "").strip()


def _scalar(conn, query: str, params: tuple[object, ...] = ()) -> int:
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
        writer = csv.DictWriter(handle, fieldnames=RESEARCH_READINESS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _distribution_rows(conn, *, group_by: str) -> list[tuple[str, int]]:
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


def _validation_status(
    conn,
    *,
    labeled_validation_path: Path,
) -> tuple[int, int, str]:
    manual_candidate_count = _scalar(
        conn,
        "SELECT COUNT(*) FROM recommendation_candidates WHERE COALESCE(manual_validated, 0) = 1",
    )
    labeled_rows = _read_csv(labeled_validation_path)
    reviewed = sum(1 for row in labeled_rows if _clean(row.get("is_true_recommendation")))
    detail = (
        f"manual_validated_candidates={manual_candidate_count}; labeled_validation_rows={reviewed}"
    )
    return manual_candidate_count, reviewed, detail


def _matched_market_rows(
    *,
    expanded_event_study_results_path: Path,
    baseline_event_study_results_path: Path,
) -> tuple[int, str]:
    if expanded_event_study_results_path.exists():
        return len(_read_csv(expanded_event_study_results_path)), str(expanded_event_study_results_path)
    if baseline_event_study_results_path.exists():
        return len(_read_csv(baseline_event_study_results_path)), str(baseline_event_study_results_path)
    return 0, "none"


def _clean_event_rows(
    *,
    expanded_clean_events_path: Path,
    baseline_clean_events_path: Path,
) -> tuple[int, str]:
    if expanded_clean_events_path.exists():
        return len(_read_csv(expanded_clean_events_path)), str(expanded_clean_events_path)
    if baseline_clean_events_path.exists():
        return len(_read_csv(baseline_clean_events_path)), str(baseline_clean_events_path)
    return 0, "none"


def build_research_readiness_report(
    *,
    database_url: str | None = None,
    output_md_path: Path = DEFAULT_RESEARCH_READINESS_MD_PATH,
    output_metrics_csv_path: Path = DEFAULT_RESEARCH_READINESS_METRICS_CSV_PATH,
    expanded_event_study_results_path: Path = DEFAULT_EXPANDED_EVENT_STUDY_RESULTS,
    baseline_event_study_results_path: Path = DEFAULT_EVENT_STUDY_RESULTS_PATH,
    expanded_clean_events_path: Path = DEFAULT_EXPANDED_CLEAN_EVENTS,
    baseline_clean_events_path: Path = DEFAULT_CLEAN_EVENTS_PATH,
    labeled_validation_path: Path = DEFAULT_LABELED_PATH,
    audit_output_csv_path: Path = DEFAULT_AVAILABILITY_AUDIT_CSV_PATH,
    audit_output_md_path: Path = DEFAULT_AVAILABILITY_AUDIT_MD_PATH,
) -> ResearchReadinessResult:
    ensure_data_dirs()
    init_db(database_url=database_url)
    audit = build_transcript_availability_audit(
        database_url=database_url,
        output_csv_path=audit_output_csv_path,
        output_md_path=audit_output_md_path,
    )
    rows_by_scope = list(audit.rows)
    overall_coverage_row = next(row for row in rows_by_scope if row["scope"] == "overall")
    year_coverage_rows = [row for row in rows_by_scope if row["scope"] == "year"]
    creator_coverage_rows = [row for row in rows_by_scope if row["scope"] == "creator"]

    with connect(database_url=database_url) as conn:
        transcript_supported_events = _scalar(
            conn,
            "SELECT COUNT(*) FROM transcript_recommendation_events",
        )
        transcript_available = _scalar(
            conn,
            "SELECT COUNT(*) FROM youtube_transcripts WHERE status = 'available'",
        )
        raw_youtube_videos = _scalar(
            conn,
            "SELECT COUNT(*) FROM raw_youtube_videos WHERE COALESCE(excluded_flag, 0) = 0",
        )
        x_post_count = _scalar(conn, "SELECT COUNT(*) FROM raw_x_posts")
        transcript_exclusions = _scalar(conn, "SELECT COUNT(*) FROM transcript_event_exclusions")
        creator_distribution = _distribution_rows(conn, group_by="creator")
        year_distribution = _distribution_rows(conn, group_by="year")
        manual_candidate_count, labeled_reviewed_rows, validation_detail = _validation_status(
            conn,
            labeled_validation_path=labeled_validation_path,
        )

    matched_market_data_events, matched_source = _matched_market_rows(
        expanded_event_study_results_path=expanded_event_study_results_path,
        baseline_event_study_results_path=baseline_event_study_results_path,
    )
    clean_events, clean_events_source = _clean_event_rows(
        expanded_clean_events_path=expanded_clean_events_path,
        baseline_clean_events_path=baseline_clean_events_path,
    )
    market_match_rate = (matched_market_data_events / clean_events) if clean_events else 0.0
    top_creator, top_creator_events = creator_distribution[0] if creator_distribution else ("none", 0)
    creator_event_share = (
        top_creator_events / transcript_supported_events if transcript_supported_events else 0.0
    )
    undercovered_years = [
        str(row["year"])
        for row in year_coverage_rows
        if float(row["transcript_coverage_pct"]) < float(overall_coverage_row["transcript_coverage_pct"])
    ]
    low_creator_coverage = [
        str(row["creator"])
        for row in creator_coverage_rows
        if "low_coverage" in _clean(row["warning_flags"])
    ]
    manual_validation_available = manual_candidate_count > 0 or labeled_reviewed_rows > 0

    if transcript_supported_events == 0 or matched_market_data_events == 0:
        overall_readiness = "red"
    elif audit.warning_flags or creator_event_share >= 0.35 or not manual_validation_available:
        overall_readiness = "yellow"
    else:
        overall_readiness = "green"

    metrics_rows: list[dict[str, Any]] = [
        {
            "section": "sample",
            "metric": "eligible_raw_youtube_videos",
            "value": raw_youtube_videos,
            "readiness": overall_readiness,
            "detail": "non-excluded local database rows",
        },
        {
            "section": "sample",
            "metric": "available_transcripts",
            "value": transcript_available,
            "readiness": overall_readiness,
            "detail": "youtube_transcripts status=available",
        },
        {
            "section": "sample",
            "metric": "transcript_supported_events",
            "value": transcript_supported_events,
            "readiness": overall_readiness,
            "detail": "transcript_recommendation_events rows",
        },
        {
            "section": "market_match",
            "metric": "matched_market_data_events",
            "value": matched_market_data_events,
            "readiness": "yellow" if matched_market_data_events else "red",
            "detail": matched_source,
        },
        {
            "section": "market_match",
            "metric": "market_match_rate",
            "value": round(market_match_rate, 6),
            "readiness": "yellow" if market_match_rate < 1.0 else "green",
            "detail": clean_events_source,
        },
        {
            "section": "coverage",
            "metric": "overall_transcript_coverage_pct",
            "value": overall_coverage_row["transcript_coverage_pct"],
            "readiness": "yellow" if audit.warning_flags else "green",
            "detail": ";".join(audit.warning_flags) or "no_bias_flags",
        },
        {
            "section": "concentration",
            "metric": "top_creator_event_share",
            "value": round(creator_event_share, 6),
            "readiness": "yellow" if creator_event_share >= 0.35 else "green",
            "detail": f"{top_creator}:{top_creator_events}",
        },
        {
            "section": "coverage",
            "metric": "undercovered_years",
            "value": ",".join(undercovered_years),
            "readiness": "yellow" if undercovered_years else "green",
            "detail": "coverage below overall rate",
        },
        {
            "section": "coverage",
            "metric": "low_coverage_creators",
            "value": ",".join(low_creator_coverage[:10]),
            "readiness": "yellow" if low_creator_coverage else "green",
            "detail": "creator buckets with low coverage",
        },
        {
            "section": "validation",
            "metric": "manual_validation_status",
            "value": "available" if manual_validation_available else "not_available",
            "readiness": "yellow" if manual_validation_available else "red",
            "detail": validation_detail,
        },
        {
            "section": "platform",
            "metric": "x_posts_in_local_db",
            "value": x_post_count,
            "readiness": "red" if x_post_count == 0 else "yellow",
            "detail": "cross-platform conclusions remain limited",
        },
        {
            "section": "quality",
            "metric": "transcript_event_exclusions",
            "value": transcript_exclusions,
            "readiness": "yellow",
            "detail": "ticker false-positive and exclusion audit remains material",
        },
    ]
    for creator, count in creator_distribution:
        metrics_rows.append(
            {
                "section": "events_by_creator",
                "metric": creator,
                "value": count,
                "readiness": "yellow" if creator == top_creator and creator_event_share >= 0.35 else "green",
                "detail": "transcript-supported event count",
            }
        )
    for year, count in year_distribution:
        metrics_rows.append(
            {
                "section": "events_by_year",
                "metric": year,
                "value": count,
                "readiness": "yellow" if year in undercovered_years else "green",
                "detail": "transcript-supported event count",
            }
        )
    _write_metrics(output_metrics_csv_path, metrics_rows)

    green_claims = [
        "The local database supports descriptive statements about the caption-available YouTube sample.",
        f"There are {transcript_supported_events} transcript-supported recommendation events in the database.",
        f"Market-data matching exists for {matched_market_data_events} events in `{matched_source}`.",
    ]
    yellow_claims = [
        "Associational daily or robustness conclusions are usable only with explicit caveats about interim market data, transcript coverage, and automatic event labeling.",
        f"The largest creator contributes {top_creator_events} events ({creator_event_share:.1%}) when transcript-supported events are grouped by creator.",
        f"Transcript coverage is uneven enough to flag: {', '.join(audit.warning_flags) if audit.warning_flags else 'no cross-bucket warning flags'}."
    ]
    red_claims = [
        "Representative claims about all finance-influencer videos are not defensible until transcript missingness is better characterized or reduced.",
        "Causal claims that recommendations moved prices are not defensible from the current design.",
        "Cross-platform claims about X leading or lagging YouTube are not defensible while X remains undercovered locally.",
    ]
    missing_data_threats = [
        "Transcript availability bias can overweight creators and years with public caption access.",
        "Creator concentration can make aggregate findings depend on a small number of channels.",
        "Year and time-period imbalance can confound any temporal comparison.",
        "Current engagement fields are snapshots, not historical engagement at event time.",
        "YouTube publication timestamps are not exact investor-attention timestamps.",
        "Classifier outputs remain partially automated and manual validation is limited or absent when no labeled review file exists.",
        "X undercoverage blocks a credible cross-platform lead-lag conclusion.",
        "Ticker false positives and overlapping recommendations can contaminate event identity.",
        "Survivorship bias remains possible if disappeared or uncollected channels differ from the observed set.",
        "Market-data matching quality remains incomplete whenever clean events exceed matched event-study rows.",
    ]
    next_steps = [
        "Keep transcript collection bounded, evidence-driven, and benchmarked against block/error outcomes.",
        "Prioritize manual validation for high-leverage creators, undercovered years, and ticker-false-positive edge cases.",
        "Treat expanded robustness as robustness-only until market data and validation are stronger.",
        "Use Bloomberg-grade joins before final inferential claims.",
    ]
    lines = [
        "# Research Readiness Report",
        "",
        f"- Overall readiness: **{overall_readiness}**",
        f"- Available transcripts: {transcript_available}",
        f"- Transcript-supported events: {transcript_supported_events}",
        f"- Market-data matched events: {matched_market_data_events}",
        f"- Clean-event reference count: {clean_events}",
        f"- Market match rate against the selected clean-event source: {market_match_rate:.1%}",
        "",
        "## Green: Defensible Now",
        "",
        *[f"- {claim}" for claim in green_claims],
        "",
        "## Yellow: Usable With Limitations",
        "",
        *[f"- {claim}" for claim in yellow_claims],
        "",
        "## Red: Not Defensible Yet",
        "",
        *[f"- {claim}" for claim in red_claims],
        "",
        "## Event Composition",
        "",
        "### Events By Creator",
        "",
    ]
    lines.extend(f"- {creator}: {count}" for creator, count in creator_distribution[:20])
    lines.extend(["", "### Events By Year", ""])
    lines.extend(f"- {year}: {count}" for year, count in year_distribution)
    lines.extend(
        [
            "",
            "## Coverage And Validation",
            "",
            f"- Transcript coverage by the audited 2020-2023 period: {float(overall_coverage_row['transcript_coverage_pct']):.1%}",
            f"- Undercovered years: {', '.join(undercovered_years) if undercovered_years else 'none'}",
            f"- Low-coverage creators: {', '.join(low_creator_coverage[:10]) if low_creator_coverage else 'none'}",
            f"- Manual validation status: {validation_detail}",
            "",
            "## Missing-Data Threats",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in missing_data_threats)
    lines.extend(["", "## What Should Happen Before Final Paper Claims", ""])
    lines.extend(f"- {item}" for item in next_steps)
    lines.extend(
        [
            "",
            "## Research Framing",
            "",
            "- Current claims should be framed as exploratory, descriptive, and robustness-oriented.",
            "- Final causal or representative claims require stronger coverage, validation, and market-data support.",
            "",
        ]
    )
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text("\n".join(lines), encoding="utf-8")
    return ResearchReadinessResult(
        markdown_path=output_md_path,
        metrics_csv_path=output_metrics_csv_path,
        overall_readiness=overall_readiness,
        transcript_supported_events=transcript_supported_events,
        matched_market_data_events=matched_market_data_events,
    )
