from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from finfluencer_alpha.auto_event_labeling import (
    AUDIT_COLUMNS,
    CLEAN_EVENT_COLUMNS,
    auto_label_event_validation,
    build_clean_auto_labeled_events,
    label_event_with_rules,
)
from finfluencer_alpha.event_validation import EVENT_VALIDATION_SAMPLE_COLUMNS


def _sample_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in EVENT_VALIDATION_SAMPLE_COLUMNS}
    row.update(
        {
            "event_id": "1",
            "candidate_window_id": "10",
            "video_id": "video1",
            "creator": "Creator A",
            "title": "Portfolio update",
            "published_at": "2026-01-01T15:00:00Z",
            "video_url": "https://www.youtube.com/watch?v=video1",
            "ticker": "NVDA",
            "company_name": "Nvidia",
            "detected_signal": "bullish_recommendation",
            "detected_direction": "bullish",
            "detected_action": "bullish_recommendation",
            "transcript_window_text": "I am buying NVDA stock because demand is accelerating.",
            "context_before": "Here is my portfolio update.",
            "context_after": "This is my highest conviction AI position.",
            "source_transcript_type": "external_provider:TranscriptAPI.com",
            "transcript_source": "external_provider",
            "provider_name": "TranscriptAPI.com",
            "year": "2026",
        }
    )
    row.update(overrides)
    return row


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(EVENT_VALIDATION_SAMPLE_COLUMNS)
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def test_rule_labels_explicit_buy_as_yes() -> None:
    decision = label_event_with_rules(_sample_row())

    assert decision.is_true_recommendation == "yes"
    assert decision.recommendation_type == "buy"
    assert decision.direction == "positive"
    assert decision.auto_label_confidence >= 0.75
    assert not decision.auto_label_needs_review


def test_rule_labels_third_party_news_only_mention_as_no() -> None:
    decision = label_event_with_rules(
        _sample_row(
            transcript_window_text="Warren Buffett bought NVDA according to news reports.",
            context_before="The segment discusses what major investors did this quarter.",
            context_after="The creator does not say they are buying it.",
        )
    )

    assert decision.is_true_recommendation == "no"
    assert decision.recommendation_type == "false_positive"
    assert "third_party" in decision.auto_label_reason


def test_rule_labels_insufficient_context_as_unclear_review_needed() -> None:
    decision = label_event_with_rules(
        _sample_row(
            transcript_window_text="NVDA maybe.",
            context_before="",
            context_after="",
        )
    )

    assert decision.is_true_recommendation == "unclear"
    assert decision.auto_label_needs_review
    assert decision.evidence_quality == "weak"


def test_auto_label_output_required_columns(tmp_path: Path) -> None:
    input_path = tmp_path / "event_validation_sample.csv"
    output_path = tmp_path / "event_validation_sample_auto_labeled.csv"
    review_path = tmp_path / "event_validation_review_needed.csv"
    summary_md = tmp_path / "auto_labeling_summary.md"
    summary_csv = tmp_path / "auto_labeling_summary.csv"
    _write_rows(input_path, [_sample_row()])

    result = auto_label_event_validation(
        input_path=input_path,
        output_path=output_path,
        review_output_path=review_path,
        summary_md_path=summary_md,
        summary_csv_path=summary_csv,
        method="rules",
    )
    df = pd.read_csv(result.output_path)

    for column in [*EVENT_VALIDATION_SAMPLE_COLUMNS, *AUDIT_COLUMNS]:
        assert column in df.columns
    assert result.total_rows == 1


def test_dry_run_writes_no_outputs(tmp_path: Path) -> None:
    input_path = tmp_path / "event_validation_sample.csv"
    output_path = tmp_path / "event_validation_sample_auto_labeled.csv"
    review_path = tmp_path / "event_validation_review_needed.csv"
    summary_md = tmp_path / "auto_labeling_summary.md"
    summary_csv = tmp_path / "auto_labeling_summary.csv"
    _write_rows(input_path, [_sample_row()])

    result = auto_label_event_validation(
        input_path=input_path,
        output_path=output_path,
        review_output_path=review_path,
        summary_md_path=summary_md,
        summary_csv_path=summary_csv,
        dry_run=True,
        limit=1,
    )

    assert result.dry_run
    assert not output_path.exists()
    assert not review_path.exists()
    assert not summary_md.exists()
    assert not summary_csv.exists()


def test_no_external_api_call_without_confirm_llm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    input_path = tmp_path / "event_validation_sample.csv"
    output_path = tmp_path / "auto.csv"
    _write_rows(
        input_path,
        [
            _sample_row(
                transcript_window_text="NVDA was mentioned in passing.",
                context_before="",
                context_after="No direct view is given.",
            )
        ],
    )

    def fail_if_called(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("external API should not be called without confirmation")

    monkeypatch.setattr("finfluencer_alpha.auto_event_labeling._call_openai_label", fail_if_called)
    result = auto_label_event_validation(
        input_path=input_path,
        output_path=output_path,
        review_output_path=tmp_path / "review.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        method="llm",
        confirm_llm_run=False,
    )
    df = pd.read_csv(result.output_path)

    assert result.rows_labeled_unclear == 1
    assert df.loc[0, "auto_label_method"] == "llm_unconfirmed"


def test_missing_openai_api_key_fails_when_confirm_llm_used(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "event_validation_sample.csv"
    _write_rows(input_path, [_sample_row(transcript_window_text="NVDA was mentioned.")])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        auto_label_event_validation(
            input_path=input_path,
            output_path=tmp_path / "auto.csv",
            review_output_path=tmp_path / "review.csv",
            summary_md_path=tmp_path / "summary.md",
            summary_csv_path=tmp_path / "summary.csv",
            method="llm",
            confirm_llm_run=True,
        )


def test_review_queue_creation(tmp_path: Path) -> None:
    input_path = tmp_path / "event_validation_sample.csv"
    review_path = tmp_path / "review.csv"
    _write_rows(
        input_path,
        [
            _sample_row(
                transcript_window_text="NVDA maybe.",
                context_before="",
                context_after="",
            )
        ],
    )

    auto_label_event_validation(
        input_path=input_path,
        output_path=tmp_path / "auto.csv",
        review_output_path=review_path,
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        method="rules",
    )
    review_df = pd.read_csv(review_path)

    assert len(review_df) == 1
    assert review_df.loc[0, "is_true_recommendation"] == "unclear"


def test_summary_creation(tmp_path: Path) -> None:
    input_path = tmp_path / "event_validation_sample.csv"
    summary_md = tmp_path / "summary.md"
    summary_csv = tmp_path / "summary.csv"
    _write_rows(input_path, [_sample_row()])

    auto_label_event_validation(
        input_path=input_path,
        output_path=tmp_path / "auto.csv",
        review_output_path=tmp_path / "review.csv",
        summary_md_path=summary_md,
        summary_csv_path=summary_csv,
        method="rules",
    )

    assert summary_md.exists()
    assert summary_csv.exists()
    assert "model-assisted" in summary_md.read_text(encoding="utf-8")


def test_clean_event_dataset_filters_no_unclear_and_weak_evidence(tmp_path: Path) -> None:
    auto_path = tmp_path / "auto.csv"
    rows = [
        {
            **_sample_row(event_id="1", ticker="AAA"),
            "is_true_recommendation": "yes",
            "recommendation_type": "buy",
            "direction": "positive",
            "evidence_quality": "strong",
            "auto_label_confidence": "0.91",
            "auto_label_needs_review": "false",
            "auto_label_reason": "explicit buy",
            "auto_label_evidence_quote": "I am buying AAA.",
        },
        {
            **_sample_row(event_id="2", ticker="BBB"),
            "is_true_recommendation": "yes",
            "recommendation_type": "buy",
            "direction": "positive",
            "evidence_quality": "weak",
            "auto_label_confidence": "0.91",
            "auto_label_needs_review": "false",
        },
        {
            **_sample_row(event_id="3", ticker="CCC"),
            "is_true_recommendation": "no",
            "recommendation_type": "false_positive",
            "direction": "unclear",
            "evidence_quality": "strong",
            "auto_label_confidence": "0.95",
            "auto_label_needs_review": "false",
        },
        {
            **_sample_row(event_id="4", ticker="DDD"),
            "is_true_recommendation": "unclear",
            "recommendation_type": "unclear",
            "direction": "unclear",
            "evidence_quality": "strong",
            "auto_label_confidence": "0.35",
            "auto_label_needs_review": "true",
        },
    ]
    _write_rows(auto_path, rows)

    result = build_clean_auto_labeled_events(
        input_path=auto_path,
        events_input_path=tmp_path / "missing_events.csv",
        output_path=tmp_path / "clean.csv",
        exclusions_output_path=tmp_path / "exclusions.csv",
        summary_md_path=tmp_path / "clean_summary.md",
    )
    clean_df = pd.read_csv(result.output_path)
    exclusions_df = pd.read_csv(result.exclusions_output_path)

    assert list(clean_df.columns) == CLEAN_EVENT_COLUMNS
    assert clean_df["ticker"].tolist() == ["AAA"]
    assert result.included_rows == 1
    assert result.excluded_rows == 3
    assert "evidence_quality=weak" in ";".join(exclusions_df["clean_event_exclusion_reason"])
