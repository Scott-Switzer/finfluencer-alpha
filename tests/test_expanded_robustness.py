import csv
from pathlib import Path
from types import SimpleNamespace

import finfluencer_alpha.expanded_robustness as expanded_robustness


def _write_rows(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _clean_event_row(
    event_id: str,
    video_id: str,
    *,
    ticker: str = "NVDA",
    creator: str = "Creator A",
    title: str = "Buy Nvidia stock now",
    published_at: str = "2026-01-01T00:00:00Z",
) -> dict[str, str]:
    return {
        "event_id": event_id,
        "video_id": video_id,
        "creator": creator,
        "title": title,
        "published_at": published_at,
        "event_date_utc": published_at[:10],
        "ticker": ticker,
        "company_name": "",
        "recommendation_type": "buy",
        "direction": "positive",
        "confidence": "0.910",
        "evidence_quality": "strong",
        "source_transcript_type": "youtube:youtube_transcript_api",
        "transcript_source": "youtube",
        "provider_name": "youtube_transcript_api",
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "transcript_window_text": "I am buying Nvidia stock.",
        "context_before": "",
        "context_after": "",
        "auto_label_reason": "test fixture",
        "auto_label_evidence_quote": "I am buying Nvidia stock.",
    }


def _patch_expanded_build_dependencies(
    monkeypatch,
    tmp_path: Path,
    *,
    baseline_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
) -> None:
    baseline_clean = tmp_path / "baseline_clean_events.csv"
    baseline_results = tmp_path / "baseline_event_study_results.csv"
    baseline_main = tmp_path / "baseline_main_table.csv"
    baseline_diagnostics = tmp_path / "baseline_match_diagnostics.csv"
    market_data = tmp_path / "market_data.csv"

    _write_rows(baseline_clean, baseline_rows, expanded_robustness.CLEAN_EVENT_COLUMNS)
    _write_rows(
        baseline_results,
        [{"event_id": row["event_id"]} for row in baseline_rows],
        ["event_id"],
    )
    _write_rows(
        baseline_main,
        [{"event_count": len(baseline_rows), "matched_count": len(baseline_rows)}],
        ["event_count", "matched_count"],
    )
    _write_rows(baseline_diagnostics, [], ["event_id"])
    _write_rows(market_data, [], ["ticker"])

    monkeypatch.setattr(expanded_robustness, "DEFAULT_CLEAN_EVENTS_PATH", baseline_clean)
    monkeypatch.setattr(
        expanded_robustness,
        "DEFAULT_EVENT_STUDY_RESULTS_PATH",
        baseline_results,
    )
    monkeypatch.setattr(expanded_robustness, "DEFAULT_MAIN_TABLE_CSV_PATH", baseline_main)
    monkeypatch.setattr(
        expanded_robustness,
        "DEFAULT_MATCH_DIAGNOSTICS_CSV_PATH",
        baseline_diagnostics,
    )
    monkeypatch.setattr(
        expanded_robustness,
        "build_event_validation_sample",
        lambda **_: SimpleNamespace(row_count=0),
    )
    monkeypatch.setattr(expanded_robustness, "auto_label_event_validation", lambda **_: None)

    def fake_build_clean_auto_labeled_events(**kwargs: object) -> SimpleNamespace:
        _write_rows(
            kwargs["output_path"],
            candidate_rows,
            expanded_robustness.CLEAN_EVENT_COLUMNS,
        )
        _write_rows(
            kwargs["exclusions_output_path"],
            [],
            [*expanded_robustness.CLEAN_EVENT_COLUMNS, "clean_event_exclusion_reason"],
        )
        Path(kwargs["summary_md_path"]).write_text("fake summary", encoding="utf-8")
        return SimpleNamespace(included_rows=len(candidate_rows), excluded_rows=0)

    def fake_run_event_study(**kwargs: object) -> SimpleNamespace:
        clean_rows = _read_rows(kwargs["input_events"])
        _write_rows(
            kwargs["output_path"],
            [{"event_id": row["event_id"], "ticker": row["ticker"]} for row in clean_rows],
            ["event_id", "ticker"],
        )
        Path(kwargs["summary_md_path"]).write_text("fake event study", encoding="utf-8")
        return SimpleNamespace(events_matched=len(clean_rows))

    monkeypatch.setattr(
        expanded_robustness,
        "build_clean_auto_labeled_events",
        fake_build_clean_auto_labeled_events,
    )
    monkeypatch.setattr(expanded_robustness, "run_event_study", fake_run_event_study)
    monkeypatch.setattr(
        expanded_robustness,
        "select_market_data_source",
        lambda **_: SimpleNamespace(path=market_data),
    )
    monkeypatch.setattr(expanded_robustness, "_metrics_row", lambda **_: {})


def test_baseline_plus_zero_new_events_keeps_baseline_count(monkeypatch, tmp_path: Path) -> None:
    baseline_rows = [
        _clean_event_row("1", "video_a"),
        _clean_event_row("2", "video_b", title="Second baseline stock idea"),
    ]
    candidate_rows = [_clean_event_row("101", "video_a")]
    _patch_expanded_build_dependencies(
        monkeypatch,
        tmp_path,
        baseline_rows=baseline_rows,
        candidate_rows=candidate_rows,
    )

    result = expanded_robustness.build_expanded_robustness_outputs(
        output_dir=tmp_path / "expanded_outputs",
        input_market_data=tmp_path / "market_data.csv",
    )
    final_rows = _read_rows(result.expanded_clean_events_path)

    assert result.baseline_clean_events == 2
    assert result.expanded_clean_events == 2
    assert result.newly_added_events == 0
    assert result.baseline_only_events == 0
    assert result.baseline_events_recovered == 1
    assert len(final_rows) == 2


def test_membership_audit_captures_baseline_only_events() -> None:
    baseline_rows = [
        _clean_event_row("1", "video_a"),
        _clean_event_row("2", "video_b", title="Second baseline stock idea"),
    ]
    expanded_rows = [_clean_event_row("101", "video_a")]

    audit_rows = expanded_robustness._build_membership_audit_rows(
        baseline_rows=baseline_rows,
        expanded_rows=expanded_rows,
        baseline_source="baseline.csv",
        expanded_source="expanded.csv",
        recovered_keys=set(),
    )

    baseline_only = [row for row in audit_rows if row["membership_status"] == "baseline_only"]
    assert len(baseline_only) == 1
    assert baseline_only[0]["event_id"] == "2"
    assert baseline_only[0]["in_baseline_clean_sample"] == "true"
    assert baseline_only[0]["in_expanded_clean_sample"] == "false"


def test_expanded_comparison_does_not_silently_drop_baseline_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    baseline_rows = [
        _clean_event_row("1", "video_a"),
        _clean_event_row("2", "video_b", title="Second baseline stock idea"),
    ]
    candidate_rows = [_clean_event_row("101", "video_a")]
    _patch_expanded_build_dependencies(
        monkeypatch,
        tmp_path,
        baseline_rows=baseline_rows,
        candidate_rows=candidate_rows,
    )

    result = expanded_robustness.build_expanded_robustness_outputs(
        output_dir=tmp_path / "expanded_outputs",
        input_market_data=tmp_path / "market_data.csv",
    )
    comparison = result.expanded_comparison_path.read_text(encoding="utf-8")
    audit = result.membership_audit_md_path.read_text(encoding="utf-8")

    assert "- Baseline events dropped from final expanded sample: 0" in comparison
    assert "- Baseline events recovered into final expanded sample: 1" in comparison
    assert "- Expanded arithmetic check passed: True" in comparison
    assert "- Baseline-only rows: 0" in audit


def test_strict_filter_outputs_are_labeled_strict_robustness(tmp_path: Path) -> None:
    path = tmp_path / "methodology.md"

    expanded_robustness._write_expanded_methodology(
        path,
        baseline_membership_source="baseline.csv",
        strict_filters_applied=True,
    )
    text = path.read_text(encoding="utf-8")

    assert "# Strict Robustness Methodology Note" in text
    assert "strict robustness sample" in text
    assert "expanded robustness sample" not in text
