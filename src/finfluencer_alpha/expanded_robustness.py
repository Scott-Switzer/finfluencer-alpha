from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .auto_event_labeling import (
    CLEAN_EVENT_COLUMNS,
    auto_label_event_validation,
    build_clean_auto_labeled_events,
)
from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect
from .event_study import run_event_study, select_market_data_source
from .event_validation import build_event_validation_sample
from .reporting import (
    DEFAULT_CLEAN_EVENTS_PATH,
    DEFAULT_EVENT_STUDY_RESULTS_PATH,
    DEFAULT_MAIN_TABLE_CSV_PATH,
    DEFAULT_MATCH_DIAGNOSTICS_CSV_PATH,
    _build_main_metrics,
    _enriched_event_rows,
    _event_lookup,
    _market_rows_by_ticker,
)
from .utils import configure_csv_field_size_limit

EXPANDED_ROBUSTNESS_DIR = EXPORTS_DIR / "expanded_robustness"
DEFAULT_EXPANDED_VALIDATION_INPUT = EXPANDED_ROBUSTNESS_DIR / "expanded_event_validation_input.csv"
DEFAULT_EXPANDED_VALIDATION_README = EXPANDED_ROBUSTNESS_DIR / "expanded_event_validation_README.md"
DEFAULT_EXPANDED_AUTO_LABELED = EXPANDED_ROBUSTNESS_DIR / "expanded_auto_labeled_events.csv"
DEFAULT_EXPANDED_REVIEW_NEEDED = EXPANDED_ROBUSTNESS_DIR / "expanded_review_needed_events.csv"
DEFAULT_EXPANDED_AUTO_SUMMARY_CSV = EXPANDED_ROBUSTNESS_DIR / "expanded_auto_labeling_summary.csv"
DEFAULT_EXPANDED_AUTO_SUMMARY_MD = EXPANDED_ROBUSTNESS_DIR / "expanded_auto_labeling_summary.md"
DEFAULT_EXPANDED_CLEAN_EVENTS = EXPANDED_ROBUSTNESS_DIR / "expanded_clean_events.csv"
DEFAULT_EXPANDED_CLEAN_EXCLUSIONS = EXPANDED_ROBUSTNESS_DIR / "expanded_clean_event_exclusions.csv"
DEFAULT_EXPANDED_CLEAN_SUMMARY = EXPANDED_ROBUSTNESS_DIR / "expanded_clean_events_summary.md"
DEFAULT_EXPANDED_EVENT_STUDY_RESULTS = (
    EXPANDED_ROBUSTNESS_DIR / "expanded_event_study_results.csv"
)
DEFAULT_EXPANDED_EVENT_STUDY_SUMMARY = (
    EXPANDED_ROBUSTNESS_DIR / "expanded_event_study_summary.md"
)
DEFAULT_EXPANDED_COMPARISON = EXPANDED_ROBUSTNESS_DIR / "expanded_comparison_to_baseline.md"
DEFAULT_EXPANDED_METHODOLOGY = EXPANDED_ROBUSTNESS_DIR / "expanded_methodology_note.md"
DEFAULT_BASELINE_EXPANDED_AUDIT_CSV = (
    EXPANDED_ROBUSTNESS_DIR / "baseline_vs_expanded_event_membership_audit.csv"
)
DEFAULT_BASELINE_EXPANDED_AUDIT_MD = (
    EXPANDED_ROBUSTNESS_DIR / "baseline_vs_expanded_event_membership_audit.md"
)

BASELINE_RECOVERY_REASON = (
    "absent_from_current_database_event_validation_sample; "
    "retained_from_committed_baseline_clean_membership"
)

MEMBERSHIP_AUDIT_COLUMNS = [
    "event_id",
    "baseline_event_id",
    "expanded_event_id",
    "video_id",
    "ticker",
    "creator",
    "title",
    "event_date",
    "upload_date",
    "recommendation_type",
    "direction",
    "in_baseline_clean_sample",
    "in_expanded_clean_sample",
    "membership_status",
    "exclusion_reason",
    "source_file_or_table",
]


@dataclass(frozen=True)
class ExpandedRobustnessResult:
    output_dir: Path
    expanded_clean_events_path: Path
    expanded_clean_events_summary_path: Path
    expanded_event_study_results_path: Path
    expanded_event_study_summary_path: Path
    expanded_comparison_path: Path
    expanded_methodology_path: Path
    membership_audit_csv_path: Path
    membership_audit_md_path: Path
    baseline_clean_events: int
    expanded_clean_events: int
    newly_added_events: int
    baseline_only_events: int
    expanded_only_events: int
    baseline_events_recovered: int
    expanded_matched_events: int
    expanded_missing_market_data_events: int


@dataclass(frozen=True)
class BaselineCleanSample:
    rows: list[dict[str, Any]]
    source: str
    source_note: str


@dataclass(frozen=True)
class MembershipAuditResult:
    csv_path: Path
    md_path: Path
    baseline_rows: int
    expanded_rows: int
    baseline_and_expanded: int
    baseline_only: int
    expanded_only: int
    recovered_baseline_events: int


def _clean(value: object) -> str:
    return str(value or "").strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _event_date_text(row: dict[str, Any]) -> str:
    for key in ("event_date_utc", "event_date_weekday_adjusted", "published_at"):
        text = _clean(row.get(key))
        if len(text) >= 10:
            return text[:10]
    return ""


def _event_id_sort_value(row: dict[str, Any]) -> tuple[int, str]:
    event_id = _clean(row.get("event_id"))
    return (int(event_id), event_id) if event_id.isdigit() else (10**9, event_id)


def _identity_base(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _clean(row.get("video_id")),
        _clean(row.get("ticker")).upper(),
        _clean(row.get("creator")),
        _clean(row.get("title")),
        _clean(row.get("published_at")),
    )


def _indexed_membership_rows(rows: list[dict[str, Any]]) -> dict[tuple[str, ...], dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_identity_base(row)].append(row)

    indexed: dict[tuple[str, ...], dict[str, Any]] = {}
    for base_key, base_rows in grouped.items():
        for occurrence, row in enumerate(sorted(base_rows, key=_event_id_sort_value), start=1):
            indexed[(*base_key, str(occurrence))] = row
    return indexed


def _unique_reference_rows_by_identity(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_identity_base(row)].append(row)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def _video_id_lookup_for_baseline_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], str]:
    lookup: dict[tuple[str, str, str], str] = {}
    missing_video_rows = [
        row
        for row in rows
        if not _clean(row.get("video_id"))
        and _clean(row.get("creator"))
        and _clean(row.get("title"))
        and _clean(row.get("published_at"))
    ]
    if not missing_video_rows:
        return lookup
    try:
        with connect() as conn:
            for row in missing_video_rows:
                key = (
                    _clean(row.get("creator")),
                    _clean(row.get("title")),
                    _clean(row.get("published_at")),
                )
                if key in lookup:
                    continue
                matches = conn.execute(
                    """
                    SELECT video_id
                    FROM raw_youtube_videos
                    WHERE channel_title = ?
                      AND title = ?
                      AND published_at = ?
                    """,
                    key,
                ).fetchall()
                if len(matches) == 1:
                    lookup[key] = _clean(matches[0]["video_id"])
    except (sqlite3.Error, RuntimeError):
        return lookup
    return lookup


def _baseline_clean_projection_from_diagnostics(
    diagnostic_row: dict[str, str],
    *,
    video_id: str,
    event_study_row: dict[str, str],
    reference_row: dict[str, Any],
    baseline_source: str,
) -> dict[str, Any]:
    recommendation_type = _clean(event_study_row.get("recommendation_type")) or _clean(
        reference_row.get("recommendation_type")
    )
    direction = _clean(event_study_row.get("direction")) or _clean(reference_row.get("direction"))
    confidence = _clean(event_study_row.get("confidence")) or _clean(reference_row.get("confidence"))
    if confidence:
        try:
            confidence = f"{float(confidence):.3f}"
        except ValueError:
            pass
    video_url = _clean(reference_row.get("video_url"))
    if not video_url and video_id:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
    auto_label_reason = _clean(reference_row.get("auto_label_reason"))
    if not auto_label_reason:
        auto_label_reason = f"baseline clean event recovered from {baseline_source}"
    return {
        "event_id": _clean(diagnostic_row.get("event_id")),
        "video_id": video_id,
        "creator": _clean(diagnostic_row.get("creator")),
        "title": _clean(diagnostic_row.get("title")),
        "published_at": _clean(diagnostic_row.get("published_at")),
        "event_date_utc": _event_date_text(diagnostic_row),
        "ticker": _clean(diagnostic_row.get("ticker")).upper(),
        "company_name": _clean(reference_row.get("company_name")),
        "recommendation_type": recommendation_type,
        "direction": direction,
        "confidence": confidence,
        "evidence_quality": _clean(reference_row.get("evidence_quality")) or "baseline_clean_sample",
        "source_transcript_type": _clean(reference_row.get("source_transcript_type"))
        or "baseline_artifact",
        "transcript_source": _clean(reference_row.get("transcript_source")) or "baseline_artifact",
        "provider_name": _clean(reference_row.get("provider_name")),
        "video_url": video_url,
        "transcript_window_text": _clean(reference_row.get("transcript_window_text")),
        "context_before": _clean(reference_row.get("context_before")),
        "context_after": _clean(reference_row.get("context_after")),
        "auto_label_reason": auto_label_reason,
        "auto_label_evidence_quote": _clean(reference_row.get("auto_label_evidence_quote")),
    }


def _load_baseline_clean_sample(
    *,
    clean_events_path: Path,
    match_diagnostics_path: Path,
    event_study_results_path: Path,
    expanded_reference_rows: list[dict[str, Any]],
    expected_baseline_count: int | None = None,
) -> BaselineCleanSample:
    if clean_events_path.exists():
        return BaselineCleanSample(
            rows=_read_csv(clean_events_path),
            source=str(clean_events_path),
            source_note="baseline clean events CSV",
        )

    diagnostic_rows = _read_csv(match_diagnostics_path)
    if not diagnostic_rows:
        return BaselineCleanSample(
            rows=[],
            source=str(clean_events_path),
            source_note="baseline clean events CSV and match diagnostics were unavailable",
        )
    if expected_baseline_count is not None and len(diagnostic_rows) != expected_baseline_count:
        return BaselineCleanSample(
            rows=[],
            source=str(match_diagnostics_path),
            source_note=(
                "match diagnostics were not used because their row count "
                f"({len(diagnostic_rows)}) does not match the baseline count "
                f"({expected_baseline_count})"
            ),
        )

    video_lookup = _video_id_lookup_for_baseline_rows(diagnostic_rows)
    event_study_by_id = {
        _clean(row.get("event_id")): row
        for row in _read_csv(event_study_results_path)
        if _clean(row.get("event_id"))
    }
    reference_by_identity = _unique_reference_rows_by_identity(expanded_reference_rows)
    rows: list[dict[str, Any]] = []
    for diagnostic_row in diagnostic_rows:
        creator_title_date = (
            _clean(diagnostic_row.get("creator")),
            _clean(diagnostic_row.get("title")),
            _clean(diagnostic_row.get("published_at")),
        )
        video_id = _clean(diagnostic_row.get("video_id")) or video_lookup.get(creator_title_date, "")
        diagnostic_with_video = {**diagnostic_row, "video_id": video_id}
        reference_row = reference_by_identity.get(_identity_base(diagnostic_with_video), {})
        event_study_row = event_study_by_id.get(_clean(diagnostic_row.get("event_id")), {})
        rows.append(
            _baseline_clean_projection_from_diagnostics(
                diagnostic_with_video,
                video_id=video_id,
                event_study_row=event_study_row,
                reference_row=reference_row,
                baseline_source=str(match_diagnostics_path),
            )
        )

    return BaselineCleanSample(
        rows=rows,
        source=str(match_diagnostics_path),
        source_note=(
            "baseline clean membership recovered from event-study match diagnostics because "
            f"{clean_events_path} is not present"
        ),
    )


def _merge_baseline_into_expanded_rows(
    *,
    baseline_rows: list[dict[str, Any]],
    expanded_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[tuple[str, ...]]]:
    baseline_index = _indexed_membership_rows(baseline_rows)
    expanded_index = _indexed_membership_rows(expanded_rows)
    recovered_keys = set(baseline_index) - set(expanded_index)
    if not recovered_keys:
        return expanded_rows, set()

    final_rows = list(expanded_rows)
    for key in sorted(recovered_keys):
        row = dict(baseline_index[key])
        reason = _clean(row.get("auto_label_reason"))
        row["auto_label_reason"] = (
            f"{reason}; {BASELINE_RECOVERY_REASON}" if reason else BASELINE_RECOVERY_REASON
        )
        final_rows.append(row)
    return final_rows, recovered_keys


def _sample_label(*, strict_filters_applied: bool) -> str:
    return "strict robustness sample" if strict_filters_applied else "expanded robustness sample"


def _sample_label_with_article(*, strict_filters_applied: bool) -> str:
    article = "a" if strict_filters_applied else "an"
    return f"{article} {_sample_label(strict_filters_applied=strict_filters_applied)}"


def _build_membership_audit_rows(
    *,
    baseline_rows: list[dict[str, Any]],
    expanded_rows: list[dict[str, Any]],
    baseline_source: str,
    expanded_source: str,
    recovered_keys: set[tuple[str, ...]],
) -> list[dict[str, Any]]:
    baseline_index = _indexed_membership_rows(baseline_rows)
    expanded_index = _indexed_membership_rows(expanded_rows)
    audit_rows: list[dict[str, Any]] = []
    for key in sorted(
        set(baseline_index) | set(expanded_index),
        key=lambda value: (value[4], value[1], value[0], value[-1]),
        reverse=True,
    ):
        baseline_row = baseline_index.get(key, {})
        expanded_row = expanded_index.get(key, {})
        row = baseline_row or expanded_row
        in_baseline = bool(baseline_row)
        in_expanded = bool(expanded_row)
        if in_baseline and in_expanded:
            membership_status = "baseline_and_expanded"
            exclusion_reason = BASELINE_RECOVERY_REASON if key in recovered_keys else ""
            source = f"baseline: {baseline_source}; expanded: {expanded_source}"
        elif in_baseline:
            membership_status = "baseline_only"
            exclusion_reason = "baseline event missing from final expanded clean sample"
            source = f"baseline: {baseline_source}"
        else:
            membership_status = "expanded_only"
            exclusion_reason = "new accepted clean event not present in baseline clean sample"
            source = f"expanded: {expanded_source}"
        baseline_event_id = _clean(baseline_row.get("event_id"))
        expanded_event_id = _clean(expanded_row.get("event_id"))
        audit_rows.append(
            {
                "event_id": baseline_event_id or expanded_event_id,
                "baseline_event_id": baseline_event_id,
                "expanded_event_id": expanded_event_id,
                "video_id": _clean(row.get("video_id")),
                "ticker": _clean(row.get("ticker")).upper(),
                "creator": _clean(row.get("creator")),
                "title": _clean(row.get("title")),
                "event_date": _event_date_text(row),
                "upload_date": _clean(row.get("published_at"))[:10],
                "recommendation_type": _clean(row.get("recommendation_type")),
                "direction": _clean(row.get("direction")),
                "in_baseline_clean_sample": str(in_baseline).lower(),
                "in_expanded_clean_sample": str(in_expanded).lower(),
                "membership_status": membership_status,
                "exclusion_reason": exclusion_reason,
                "source_file_or_table": source,
            }
        )
    return audit_rows


def _write_membership_audit(
    *,
    csv_path: Path,
    md_path: Path,
    audit_rows: list[dict[str, Any]],
    baseline_source: str,
    baseline_source_note: str,
    expanded_source: str,
    strict_candidate_count: int,
    recovered_count: int,
) -> MembershipAuditResult:
    _write_csv(csv_path, audit_rows, MEMBERSHIP_AUDIT_COLUMNS)
    baseline_count = sum(1 for row in audit_rows if row["in_baseline_clean_sample"] == "true")
    expanded_count = sum(1 for row in audit_rows if row["in_expanded_clean_sample"] == "true")
    both_count = sum(1 for row in audit_rows if row["membership_status"] == "baseline_and_expanded")
    baseline_only_count = sum(1 for row in audit_rows if row["membership_status"] == "baseline_only")
    expanded_only_count = sum(1 for row in audit_rows if row["membership_status"] == "expanded_only")

    lines = [
        "# Baseline vs Expanded Event Membership Audit",
        "",
        f"- Baseline clean sample rows: {baseline_count}",
        f"- Expanded clean sample rows: {expanded_count}",
        f"- Baseline and expanded rows: {both_count}",
        f"- Baseline-only rows: {baseline_only_count}",
        f"- Expanded-only rows: {expanded_only_count}",
        f"- Pre-union expanded candidate clean rows: {strict_candidate_count}",
        f"- Baseline events recovered into final expanded sample: {recovered_count}",
        f"- Baseline membership source: `{baseline_source}`",
        f"- Baseline source note: {baseline_source_note}",
        f"- Expanded clean sample source: `{expanded_source}`",
        "",
    ]
    recovered_rows = [row for row in audit_rows if row["exclusion_reason"] == BASELINE_RECOVERY_REASON]
    if recovered_rows:
        lines.extend(
            [
                "## Recovered Baseline Rows",
                "",
                "| baseline_event_id | expanded_event_id | video_id | ticker | creator | upload_date | reason |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in recovered_rows:
            lines.append(
                "| {baseline_event_id} | {expanded_event_id} | {video_id} | {ticker} | "
                "{creator} | {upload_date} | {exclusion_reason} |".format(**row)
            )
        lines.append("")
    baseline_only_rows = [row for row in audit_rows if row["membership_status"] == "baseline_only"]
    if baseline_only_rows:
        lines.extend(
            [
                "## Baseline-Only Rows",
                "",
                "| event_id | video_id | ticker | creator | upload_date | exclusion_reason |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in baseline_only_rows:
            lines.append(
                "| {event_id} | {video_id} | {ticker} | {creator} | {upload_date} | "
                "{exclusion_reason} |".format(**row)
            )
        lines.append("")
    expanded_only_rows = [row for row in audit_rows if row["membership_status"] == "expanded_only"]
    if expanded_only_rows:
        lines.extend(
            [
                "## Expanded-Only Rows",
                "",
                "| event_id | video_id | ticker | creator | upload_date | exclusion_reason |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in expanded_only_rows:
            lines.append(
                "| {event_id} | {video_id} | {ticker} | {creator} | {upload_date} | "
                "{exclusion_reason} |".format(**row)
            )
        lines.append("")
    _write_text(md_path, "\n".join(lines))
    return MembershipAuditResult(
        csv_path=csv_path,
        md_path=md_path,
        baseline_rows=baseline_count,
        expanded_rows=expanded_count,
        baseline_and_expanded=both_count,
        baseline_only=baseline_only_count,
        expanded_only=expanded_only_count,
        recovered_baseline_events=recovered_count,
    )


def _baseline_counts(
    *,
    clean_events_path: Path,
    event_study_results_path: Path,
    main_table_path: Path,
) -> tuple[int, int, str]:
    clean_rows = _read_csv(clean_events_path)
    result_rows = _read_csv(event_study_results_path)
    if clean_rows:
        return len(clean_rows), len(result_rows), str(clean_events_path)
    main_rows = _read_csv(main_table_path)
    if main_rows:
        row = main_rows[0]
        return (
            int(float(row.get("event_count") or 0)),
            int(float(row.get("matched_count") or len(result_rows))),
            str(main_table_path),
        )
    return len(result_rows), len(result_rows), str(event_study_results_path)


def _metrics_row(
    *,
    clean_events_path: Path,
    event_study_results_path: Path,
    market_data_path: Path,
) -> dict[str, Any]:
    clean_rows = _read_csv(clean_events_path)
    result_rows = _read_csv(event_study_results_path)
    market_rows = _read_csv(market_data_path)
    clean_by_event = _event_lookup(clean_rows)
    market_by_ticker = _market_rows_by_ticker(market_rows)
    enriched = _enriched_event_rows(
        result_rows,
        clean_rows_by_event_id=clean_by_event,
        market_rows_by_ticker=market_by_ticker,
    )
    row, _notes = _build_main_metrics(event_count=len(clean_rows), matched_rows=enriched)
    return row


def _metric_line(label: str, row: dict[str, Any], key: str) -> str:
    return f"- {label}: {row.get(key, '')}"


def _write_expanded_clean_summary(
    path: Path,
    *,
    clean_count: int,
    excluded_count: int,
    baseline_count: int,
    newly_added_count: int,
    strict_candidate_count: int,
    baseline_only_count: int,
    recovered_baseline_count: int,
    baseline_membership_source: str,
    strict_filters_applied: bool = False,
) -> Path:
    sample_label = _sample_label_with_article(strict_filters_applied=strict_filters_applied)
    expansion_check = (
        "Yes" if clean_count == baseline_count + newly_added_count - baseline_only_count else "No"
    )
    title = "# Strict Robustness Clean Events Summary" if strict_filters_applied else "# Expanded Clean Events Summary"
    lines = [
        title,
        "",
        f"This is {sample_label}. It does not replace the "
        "validated baseline daily or intraday outputs.",
        "",
        f"- Baseline membership source: `{baseline_membership_source}`",
        f"- Baseline clean events: {baseline_count}",
        f"- Expanded clean events: {clean_count}",
        f"- Newly added clean events: {newly_added_count}",
        f"- Baseline events dropped from final expanded sample: {baseline_only_count}",
        f"- Baseline events recovered into final expanded sample: {recovered_baseline_count}",
        f"- Expanded clean events equal baseline + new clean events - documented drops: {expansion_check}",
        f"- Pre-union expanded candidate clean events: {strict_candidate_count}",
        f"- Expanded excluded/review-filtered rows: {excluded_count}",
        "",
    ]
    return _write_text(path, "\n".join(lines))


def _write_expanded_comparison(
    path: Path,
    *,
    baseline_clean_events: int,
    baseline_matched_events: int,
    baseline_metrics: dict[str, Any],
    baseline_source: str,
    baseline_membership_source: str,
    expanded_clean_events: int,
    expanded_matched_events: int,
    expanded_missing_market_data_events: int,
    expanded_metrics: dict[str, Any],
    newly_added_events: int,
    baseline_only_events: int,
    expanded_only_events: int,
    recovered_baseline_events: int,
    strict_candidate_clean_events: int,
    membership_audit_path: Path,
    strict_filters_applied: bool = False,
) -> Path:
    sample_label = _sample_label_with_article(strict_filters_applied=strict_filters_applied)
    expected_expanded_events = baseline_clean_events + newly_added_events - baseline_only_events
    arithmetic_matches = expanded_clean_events == expected_expanded_events
    comparable = baseline_only_events == 0
    if strict_filters_applied:
        recommended_use = "strict robustness test"
    elif newly_added_events:
        recommended_use = "expanded robustness result"
    else:
        recommended_use = "baseline-preserving diagnostic; no substantive expansion was added"
    title = (
        "# Strict Robustness Comparison to Baseline"
        if strict_filters_applied
        else "# Expanded Robustness Comparison to Baseline"
    )
    lines = [
        title,
        "",
        f"These outputs are {sample_label}, not replacements for the "
        "validated baseline daily or intraday analyses.",
        "",
        f"- Baseline count source: `{baseline_source}`",
        f"- Baseline membership source: `{baseline_membership_source}`",
        f"- Membership audit: `{membership_audit_path}`",
        f"- Baseline clean events: {baseline_clean_events}",
        f"- Expanded clean events: {expanded_clean_events}",
        f"- Newly added clean events: {newly_added_events}",
        f"- Expanded-only clean events: {expanded_only_events}",
        f"- Baseline events dropped from final expanded sample: {baseline_only_events}",
        f"- Baseline events recovered into final expanded sample: {recovered_baseline_events}",
        f"- Pre-union expanded candidate clean events: {strict_candidate_clean_events}",
        f"- Expected expanded clean events from baseline + new - drops: {expected_expanded_events}",
        f"- Expanded arithmetic check passed: {arithmetic_matches}",
        f"- Baseline daily matched events: {baseline_matched_events}",
        f"- Expanded daily matched events: {expanded_matched_events}",
        f"- Expanded missing market-data events: {expanded_missing_market_data_events}",
        f"- Event-study result comparable to baseline result: {comparable}",
        f"- Recommended use: {recommended_use}",
        "",
        "## Baseline Daily Metrics",
        "",
        _metric_line("1D abnormal return", baseline_metrics, "mean_abnormal_return_1d"),
        _metric_line("5D abnormal return", baseline_metrics, "mean_abnormal_return_5d"),
        _metric_line("20D abnormal return", baseline_metrics, "mean_abnormal_return_20d"),
        _metric_line("5D CAR", baseline_metrics, "mean_car_5d"),
        _metric_line("20D CAR", baseline_metrics, "mean_car_20d"),
        _metric_line("1D abnormal return t-stat", baseline_metrics, "t_stat_abnormal_return_1d"),
        _metric_line("1D abnormal return p-value", baseline_metrics, "p_value_abnormal_return_1d"),
        _metric_line("5D abnormal return t-stat", baseline_metrics, "t_stat_abnormal_return_5d"),
        _metric_line("5D abnormal return p-value", baseline_metrics, "p_value_abnormal_return_5d"),
        _metric_line("20D abnormal return t-stat", baseline_metrics, "t_stat_abnormal_return_20d"),
        _metric_line("20D abnormal return p-value", baseline_metrics, "p_value_abnormal_return_20d"),
        _metric_line("5D CAR t-stat", baseline_metrics, "t_stat_car_5d"),
        _metric_line("5D CAR p-value", baseline_metrics, "p_value_car_5d"),
        _metric_line("20D CAR t-stat", baseline_metrics, "t_stat_car_20d"),
        _metric_line("20D CAR p-value", baseline_metrics, "p_value_car_20d"),
        "",
        "## Expanded Daily Metrics",
        "",
        _metric_line("1D abnormal return", expanded_metrics, "mean_abnormal_return_1d"),
        _metric_line("5D abnormal return", expanded_metrics, "mean_abnormal_return_5d"),
        _metric_line("20D abnormal return", expanded_metrics, "mean_abnormal_return_20d"),
        _metric_line("5D CAR", expanded_metrics, "mean_car_5d"),
        _metric_line("20D CAR", expanded_metrics, "mean_car_20d"),
        _metric_line("1D abnormal return t-stat", expanded_metrics, "t_stat_abnormal_return_1d"),
        _metric_line("1D abnormal return p-value", expanded_metrics, "p_value_abnormal_return_1d"),
        _metric_line("5D abnormal return t-stat", expanded_metrics, "t_stat_abnormal_return_5d"),
        _metric_line("5D abnormal return p-value", expanded_metrics, "p_value_abnormal_return_5d"),
        _metric_line("20D abnormal return t-stat", expanded_metrics, "t_stat_abnormal_return_20d"),
        _metric_line("20D abnormal return p-value", expanded_metrics, "p_value_abnormal_return_20d"),
        _metric_line("5D CAR t-stat", expanded_metrics, "t_stat_car_5d"),
        _metric_line("5D CAR p-value", expanded_metrics, "p_value_car_5d"),
        _metric_line("20D CAR t-stat", expanded_metrics, "t_stat_car_20d"),
        _metric_line("20D CAR p-value", expanded_metrics, "p_value_car_20d"),
        "",
        "## Guardrails",
        "",
        "- Expanded results are associational, not causal.",
        "- Market data remains the interim yfinance/Yahoo prototype.",
        "- Bloomberg replacement remains planned for final inference.",
        "- Baseline daily and intraday outputs remain the validated primary results.",
        "- Baseline events are not removed unless the output is explicitly labeled as a strict robustness sample.",
        "",
    ]
    return _write_text(path, "\n".join(lines))


def _write_expanded_methodology(
    path: Path,
    *,
    baseline_membership_source: str,
    strict_filters_applied: bool = False,
) -> Path:
    sample_label = _sample_label_with_article(strict_filters_applied=strict_filters_applied)
    title = (
        "# Strict Robustness Methodology Note"
        if strict_filters_applied
        else "# Expanded Robustness Methodology Note"
    )
    lines = [
        title,
        "",
        f"This run produces {sample_label}. It integrates newly imported transcript evidence "
        "into the existing deterministic transcript event pipeline and does not replace the "
        "committed baseline daily or intraday outputs.",
        "",
        "Recommendation events are extracted from transcript windows using deterministic rules, "
        "then filtered through the same automated rules-based validation path used for the "
        "research pipeline. No paid transcript API calls, X calls, or LLM calls are part of this "
        "command.",
        "",
        "Sample construction is baseline-preserving: the final clean sample is the committed "
        "baseline clean membership plus newly accepted clean events from "
        "new transcripts, minus only explicitly documented invalidations. If the baseline clean "
        "CSV is unavailable, baseline membership is recovered from the committed event-study "
        f"match diagnostics: `{baseline_membership_source}`.",
        "",
        "If stricter filters are intentionally applied to baseline events, the output must be "
        "labeled as a strict robustness sample rather than an expanded sample.",
        "",
        "The daily event-study join uses interim yfinance/Yahoo market data and benchmark-adjusted "
        "returns. Bloomberg data replacement remains planned before final inference.",
        "",
        "The results are associational and should not be interpreted as causal evidence that "
        "creator recommendations moved prices.",
        "",
    ]
    return _write_text(path, "\n".join(lines))


def build_expanded_robustness_outputs(
    *,
    output_dir: Path = EXPANDED_ROBUSTNESS_DIR,
    input_market_data: Path | None = None,
    market_data_source: str = "auto",
    min_confidence: float = 0.75,
) -> ExpandedRobustnessResult:
    ensure_data_dirs()
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_input = output_dir / DEFAULT_EXPANDED_VALIDATION_INPUT.name
    validation_readme = output_dir / DEFAULT_EXPANDED_VALIDATION_README.name
    auto_labeled = output_dir / DEFAULT_EXPANDED_AUTO_LABELED.name
    review_needed = output_dir / DEFAULT_EXPANDED_REVIEW_NEEDED.name
    auto_summary_csv = output_dir / DEFAULT_EXPANDED_AUTO_SUMMARY_CSV.name
    auto_summary_md = output_dir / DEFAULT_EXPANDED_AUTO_SUMMARY_MD.name
    clean_events = output_dir / DEFAULT_EXPANDED_CLEAN_EVENTS.name
    clean_exclusions = output_dir / DEFAULT_EXPANDED_CLEAN_EXCLUSIONS.name
    clean_summary = output_dir / DEFAULT_EXPANDED_CLEAN_SUMMARY.name
    event_study_results = output_dir / DEFAULT_EXPANDED_EVENT_STUDY_RESULTS.name
    event_study_summary = output_dir / DEFAULT_EXPANDED_EVENT_STUDY_SUMMARY.name
    comparison = output_dir / DEFAULT_EXPANDED_COMPARISON.name
    methodology = output_dir / DEFAULT_EXPANDED_METHODOLOGY.name
    membership_audit_csv = output_dir / DEFAULT_BASELINE_EXPANDED_AUDIT_CSV.name
    membership_audit_md = output_dir / DEFAULT_BASELINE_EXPANDED_AUDIT_MD.name

    build_event_validation_sample(
        sample_size=1_000_000,
        output_path=validation_input,
        readme_path=validation_readme,
    )
    auto_label_event_validation(
        input_path=validation_input,
        output_path=auto_labeled,
        review_output_path=review_needed,
        summary_md_path=auto_summary_md,
        summary_csv_path=auto_summary_csv,
        method="rules",
        min_auto_confidence=min_confidence,
        confirm_llm_run=False,
        force=True,
    )
    clean_result = build_clean_auto_labeled_events(
        input_path=auto_labeled,
        events_input_path=Path("__expanded_no_external_event_merge__.csv"),
        output_path=clean_events,
        exclusions_output_path=clean_exclusions,
        summary_md_path=clean_summary,
        min_confidence=min_confidence,
    )
    strict_candidate_clean_rows = _read_csv(clean_events)
    baseline_clean_events, baseline_matched_events, baseline_source = _baseline_counts(
        clean_events_path=DEFAULT_CLEAN_EVENTS_PATH,
        event_study_results_path=DEFAULT_EVENT_STUDY_RESULTS_PATH,
        main_table_path=DEFAULT_MAIN_TABLE_CSV_PATH,
    )
    baseline_sample = _load_baseline_clean_sample(
        clean_events_path=DEFAULT_CLEAN_EVENTS_PATH,
        match_diagnostics_path=DEFAULT_MATCH_DIAGNOSTICS_CSV_PATH,
        event_study_results_path=DEFAULT_EVENT_STUDY_RESULTS_PATH,
        expanded_reference_rows=strict_candidate_clean_rows,
        expected_baseline_count=baseline_clean_events,
    )
    final_clean_rows, recovered_keys = _merge_baseline_into_expanded_rows(
        baseline_rows=baseline_sample.rows,
        expanded_rows=strict_candidate_clean_rows,
    )
    _write_csv(clean_events, final_clean_rows, CLEAN_EVENT_COLUMNS)
    audit_rows = _build_membership_audit_rows(
        baseline_rows=baseline_sample.rows,
        expanded_rows=final_clean_rows,
        baseline_source=baseline_sample.source,
        expanded_source=str(clean_events),
        recovered_keys=recovered_keys,
    )
    audit_result = _write_membership_audit(
        csv_path=membership_audit_csv,
        md_path=membership_audit_md,
        audit_rows=audit_rows,
        baseline_source=baseline_sample.source,
        baseline_source_note=baseline_sample.source_note,
        expanded_source=str(clean_events),
        strict_candidate_count=len(strict_candidate_clean_rows),
        recovered_count=len(recovered_keys),
    )
    study_result = run_event_study(
        input_events=clean_events,
        input_market_data=input_market_data,
        market_data_source=market_data_source,
        output_path=event_study_results,
        summary_md_path=event_study_summary,
    )
    market_selection = select_market_data_source(
        input_market_data=input_market_data,
        market_data_source=market_data_source,
    )
    baseline_metrics_rows = _read_csv(DEFAULT_MAIN_TABLE_CSV_PATH)
    baseline_metrics = baseline_metrics_rows[0] if baseline_metrics_rows else {}
    expanded_metrics = _metrics_row(
        clean_events_path=clean_events,
        event_study_results_path=event_study_results,
        market_data_path=market_selection.path,
    )
    expanded_clean_events = len(final_clean_rows)
    expanded_matched_events = study_result.events_matched
    expanded_missing_market_data_events = max(0, expanded_clean_events - expanded_matched_events)
    newly_added_events = audit_result.expanded_only
    _write_expanded_clean_summary(
        clean_summary,
        clean_count=expanded_clean_events,
        excluded_count=clean_result.excluded_rows,
        baseline_count=baseline_clean_events,
        newly_added_count=newly_added_events,
        strict_candidate_count=len(strict_candidate_clean_rows),
        baseline_only_count=audit_result.baseline_only,
        recovered_baseline_count=audit_result.recovered_baseline_events,
        baseline_membership_source=baseline_sample.source,
    )
    _write_expanded_comparison(
        comparison,
        baseline_clean_events=baseline_clean_events,
        baseline_matched_events=baseline_matched_events,
        baseline_metrics=baseline_metrics,
        baseline_source=baseline_source,
        baseline_membership_source=baseline_sample.source,
        expanded_clean_events=expanded_clean_events,
        expanded_matched_events=expanded_matched_events,
        expanded_missing_market_data_events=expanded_missing_market_data_events,
        expanded_metrics=expanded_metrics,
        newly_added_events=newly_added_events,
        baseline_only_events=audit_result.baseline_only,
        expanded_only_events=audit_result.expanded_only,
        recovered_baseline_events=audit_result.recovered_baseline_events,
        strict_candidate_clean_events=len(strict_candidate_clean_rows),
        membership_audit_path=membership_audit_md,
    )
    _write_expanded_methodology(
        methodology,
        baseline_membership_source=baseline_sample.source,
    )
    return ExpandedRobustnessResult(
        output_dir=output_dir,
        expanded_clean_events_path=clean_events,
        expanded_clean_events_summary_path=clean_summary,
        expanded_event_study_results_path=event_study_results,
        expanded_event_study_summary_path=event_study_summary,
        expanded_comparison_path=comparison,
        expanded_methodology_path=methodology,
        membership_audit_csv_path=membership_audit_csv,
        membership_audit_md_path=membership_audit_md,
        baseline_clean_events=baseline_clean_events,
        expanded_clean_events=expanded_clean_events,
        newly_added_events=newly_added_events,
        baseline_only_events=audit_result.baseline_only,
        expanded_only_events=audit_result.expanded_only,
        baseline_events_recovered=audit_result.recovered_baseline_events,
        expanded_matched_events=expanded_matched_events,
        expanded_missing_market_data_events=expanded_missing_market_data_events,
    )
