from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .auto_event_labeling import auto_label_event_validation, build_clean_auto_labeled_events
from .config import EXPORTS_DIR, ensure_data_dirs
from .event_study import run_event_study, select_market_data_source
from .event_validation import build_event_validation_sample
from .reporting import (
    DEFAULT_CLEAN_EVENTS_PATH,
    DEFAULT_EVENT_STUDY_RESULTS_PATH,
    DEFAULT_MAIN_TABLE_CSV_PATH,
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


@dataclass(frozen=True)
class ExpandedRobustnessResult:
    output_dir: Path
    expanded_clean_events_path: Path
    expanded_clean_events_summary_path: Path
    expanded_event_study_results_path: Path
    expanded_event_study_summary_path: Path
    expanded_comparison_path: Path
    expanded_methodology_path: Path
    baseline_clean_events: int
    expanded_clean_events: int
    newly_added_events: int
    expanded_matched_events: int
    expanded_missing_market_data_events: int


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
) -> Path:
    lines = [
        "# Expanded Clean Events Summary",
        "",
        "This is an expanded robustness/supplemental event sample. It does not replace the "
        "validated baseline daily or intraday outputs.",
        "",
        f"- Baseline clean events: {baseline_count}",
        f"- Expanded clean events: {clean_count}",
        f"- Newly added events: {newly_added_count}",
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
    expanded_clean_events: int,
    expanded_matched_events: int,
    expanded_missing_market_data_events: int,
    expanded_metrics: dict[str, Any],
) -> Path:
    newly_added_events = max(0, expanded_clean_events - baseline_clean_events)
    lines = [
        "# Expanded Robustness Comparison to Baseline",
        "",
        "These expanded outputs are supplemental robustness results, not replacements for the "
        "validated baseline daily or intraday analyses.",
        "",
        f"- Baseline count source: `{baseline_source}`",
        f"- Baseline clean events: {baseline_clean_events}",
        f"- Expanded clean events: {expanded_clean_events}",
        f"- Newly added events: {newly_added_events}",
        f"- Baseline daily matched events: {baseline_matched_events}",
        f"- Expanded daily matched events: {expanded_matched_events}",
        f"- Expanded missing market-data events: {expanded_missing_market_data_events}",
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
        "",
    ]
    return _write_text(path, "\n".join(lines))


def _write_expanded_methodology(path: Path) -> Path:
    lines = [
        "# Expanded Robustness Methodology Note",
        "",
        "This expanded robustness run integrates newly imported transcript evidence into the "
        "existing deterministic transcript event pipeline. It is labeled as supplemental and "
        "does not replace the committed baseline daily or intraday outputs.",
        "",
        "Recommendation events are extracted from transcript windows using deterministic rules, "
        "then filtered through the same automated rules-based validation path used for the "
        "research pipeline. No paid transcript API calls, X calls, or LLM calls are part of this "
        "expanded robustness command.",
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
    baseline_clean_events, baseline_matched_events, baseline_source = _baseline_counts(
        clean_events_path=DEFAULT_CLEAN_EVENTS_PATH,
        event_study_results_path=DEFAULT_EVENT_STUDY_RESULTS_PATH,
        main_table_path=DEFAULT_MAIN_TABLE_CSV_PATH,
    )
    baseline_metrics_rows = _read_csv(DEFAULT_MAIN_TABLE_CSV_PATH)
    baseline_metrics = baseline_metrics_rows[0] if baseline_metrics_rows else {}
    expanded_metrics = _metrics_row(
        clean_events_path=clean_events,
        event_study_results_path=event_study_results,
        market_data_path=market_selection.path,
    )
    expanded_clean_events = clean_result.included_rows
    expanded_matched_events = study_result.events_matched
    expanded_missing_market_data_events = max(0, expanded_clean_events - expanded_matched_events)
    newly_added_events = max(0, expanded_clean_events - baseline_clean_events)
    _write_expanded_clean_summary(
        clean_summary,
        clean_count=expanded_clean_events,
        excluded_count=clean_result.excluded_rows,
        baseline_count=baseline_clean_events,
        newly_added_count=newly_added_events,
    )
    _write_expanded_comparison(
        comparison,
        baseline_clean_events=baseline_clean_events,
        baseline_matched_events=baseline_matched_events,
        baseline_metrics=baseline_metrics,
        baseline_source=baseline_source,
        expanded_clean_events=expanded_clean_events,
        expanded_matched_events=expanded_matched_events,
        expanded_missing_market_data_events=expanded_missing_market_data_events,
        expanded_metrics=expanded_metrics,
    )
    _write_expanded_methodology(methodology)
    return ExpandedRobustnessResult(
        output_dir=output_dir,
        expanded_clean_events_path=clean_events,
        expanded_clean_events_summary_path=clean_summary,
        expanded_event_study_results_path=event_study_results,
        expanded_event_study_summary_path=event_study_summary,
        expanded_comparison_path=comparison,
        expanded_methodology_path=methodology,
        baseline_clean_events=baseline_clean_events,
        expanded_clean_events=expanded_clean_events,
        newly_added_events=newly_added_events,
        expanded_matched_events=expanded_matched_events,
        expanded_missing_market_data_events=expanded_missing_market_data_events,
    )
