from __future__ import annotations

import csv
from pathlib import Path

from finfluencer_alpha.data_decision import build_data_decision_report
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.research_readiness import build_research_readiness_report
from finfluencer_alpha.transcript_availability_audit import build_transcript_availability_audit
from finfluencer_alpha.transcript_method_benchmark import (
    _run_package_cli_batch,
    benchmark_youtube_transcript_methods,
)
from finfluencer_alpha.transcript_proxy import ProxyConfig


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _init_db(tmp_path: Path, name: str) -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    init_db(database_url=database_url)
    return database_url


def test_transcript_method_benchmark_dry_run_writes_measurement_files(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.csv"
    _write_csv(queue_path, [{"video_id": "abc123"}])

    result = benchmark_youtube_transcript_methods(
        input_path=queue_path,
        max_videos=10,
        methods=["api-single", "api-session", "package-cli-batch"],
        proxy_mode="no-proxy",
        dry_run=True,
        output_csv_path=tmp_path / "benchmark.csv",
        output_md_path=tmp_path / "benchmark.md",
    )

    rows = list(csv.DictReader(result.csv_path.open()))
    assert [row["method"] for row in rows] == [
        "api-single",
        "api-session",
        "package-cli-batch",
    ]
    assert all(row["run_mode"] == "dry_run" for row in rows)
    assert "measurement only" in result.markdown_path.read_text(encoding="utf-8")


def test_package_cli_batch_uses_parseable_json_shape(monkeypatch) -> None:
    captured_args: list[str] = []

    class FakeCompleted:
        returncode = 0
        stdout = '[[{"text": "one"}], [{"text": "two"}]]'

    def fake_run(args: list[str], **kwargs: object) -> FakeCompleted:
        del kwargs
        captured_args.extend(args)
        return FakeCompleted()

    monkeypatch.setattr(
        "finfluencer_alpha.transcript_method_benchmark.subprocess.run",
        fake_run,
    )

    row, stopped = _run_package_cli_batch(
        video_ids=["v1", "v2"],
        proxy_config=ProxyConfig(mode="no-proxy"),
        languages=["en"],
    )

    assert stopped is None
    assert row["support_status"] == "supported_but_metadata_incomplete"
    assert row["successes"] == 2
    assert captured_args.index("v1") < captured_args.index("--languages")


def test_transcript_availability_audit_summarizes_local_db_state(tmp_path: Path) -> None:
    database_url = _init_db(tmp_path, "audit.db")
    with connect(database_url=database_url) as conn:
        conn.executemany(
            """
            INSERT INTO raw_youtube_videos (video_id, channel_title, published_at, title)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("v1", "Creator A", "2020-01-01T00:00:00Z", "A"),
                ("v2", "Creator A", "2020-02-01T00:00:00Z", "B"),
                ("v3", "Creator B", "2021-01-01T00:00:00Z", "C"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            [
                ("v1", "available", "youtube_transcript_api"),
                ("v2", "disabled", "youtube_transcript_api"),
            ],
        )
        conn.execute(
            """
            INSERT INTO transcript_recommendation_events (
              video_id, ticker, confidence_score, confidence_label
            )
            VALUES (?, ?, ?, ?)
            """,
            ("v1", "NVDA", 0.9, "high"),
        )
        conn.commit()

    result = build_transcript_availability_audit(
        database_url=database_url,
        start_year=2020,
        end_year=2023,
        output_csv_path=tmp_path / "availability.csv",
        output_md_path=tmp_path / "availability.md",
    )
    rows = list(csv.DictReader(result.csv_path.open()))
    overall = next(row for row in rows if row["scope"] == "overall")
    assert overall["total_raw_youtube_videos"] == "3"
    assert overall["available_transcripts"] == "1"
    assert overall["disabled_transcripts"] == "1"
    assert overall["pending_unattempted"] == "1"
    assert overall["transcript_supported_events"] == "1"


def test_research_readiness_report_answers_core_counts(tmp_path: Path) -> None:
    database_url = _init_db(tmp_path, "readiness.db")
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, channel_title, published_at, title)
            VALUES (?, ?, ?, ?)
            """,
            ("v1", "Creator A", "2021-01-01T00:00:00Z", "Video"),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("v1", "available", "youtube_transcript_api"),
        )
        conn.execute(
            """
            INSERT INTO transcript_recommendation_events (
              video_id, ticker, confidence_score, confidence_label
            )
            VALUES (?, ?, ?, ?)
            """,
            ("v1", "AMD", 0.9, "high"),
        )
        conn.commit()

    event_study_path = tmp_path / "expanded_event_study_results.csv"
    clean_events_path = tmp_path / "expanded_clean_events.csv"
    labeled_validation_path = tmp_path / "event_validation_sample_labeled.csv"
    _write_csv(event_study_path, [{"event_id": 1, "ticker": "AMD"}])
    _write_csv(clean_events_path, [{"event_id": 1, "ticker": "AMD"}])
    _write_csv(labeled_validation_path, [{"is_true_recommendation": "yes"}])

    result = build_research_readiness_report(
        database_url=database_url,
        output_md_path=tmp_path / "research_readiness_report.md",
        output_metrics_csv_path=tmp_path / "research_readiness_metrics.csv",
        expanded_event_study_results_path=event_study_path,
        baseline_event_study_results_path=tmp_path / "missing_baseline_results.csv",
        expanded_clean_events_path=clean_events_path,
        baseline_clean_events_path=tmp_path / "missing_baseline_clean.csv",
        labeled_validation_path=labeled_validation_path,
        audit_output_csv_path=tmp_path / "availability.csv",
        audit_output_md_path=tmp_path / "availability.md",
    )

    report = result.markdown_path.read_text(encoding="utf-8")
    metrics = list(csv.DictReader(result.metrics_csv_path.open()))
    matched_row = next(row for row in metrics if row["metric"] == "matched_market_data_events")
    assert "Transcript-supported events: 1" in report
    assert matched_row["value"] == "1"
    assert result.matched_market_data_events == 1


def test_data_decision_report_summarizes_missingness_and_recommendations(tmp_path: Path) -> None:
    database_url = _init_db(tmp_path, "decision.db")
    with connect(database_url=database_url) as conn:
        conn.executemany(
            """
            INSERT INTO raw_youtube_videos (video_id, channel_title, published_at, title)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("v1", "Creator A", "2022-01-01T00:00:00Z", "Stocks"),
                ("v2", "Creator B", "2023-01-01T00:00:00Z", "Stocks"),
            ],
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, status, provider_name)
            VALUES (?, ?, ?)
            """,
            ("v1", "available", "youtube_transcript_api"),
        )
        conn.execute(
            """
            INSERT INTO transcript_recommendation_events (
              video_id, ticker, confidence_score, confidence_label
            )
            VALUES (?, ?, ?, ?)
            """,
            ("v1", "NVDA", 0.9, "high"),
        )
        conn.commit()

    queue_path = tmp_path / "slow_queue.csv"
    browser_audit_path = tmp_path / "browser_audit.csv"
    event_study_path = tmp_path / "expanded_event_study_results.csv"
    clean_events_path = tmp_path / "expanded_clean_events.csv"
    labeled_validation_path = tmp_path / "event_validation_sample_labeled.csv"
    _write_csv(queue_path, [{"video_id": "v2"}])
    _write_csv(
        browser_audit_path,
        [
            {
                "video_id": "v2",
                "transcript_visible": "yes",
                "transcript_recovered": "yes",
            }
        ],
    )
    _write_csv(event_study_path, [{"event_id": 1, "ticker": "NVDA"}])
    _write_csv(clean_events_path, [{"event_id": 1, "ticker": "NVDA"}])
    _write_csv(labeled_validation_path, [])

    result = build_data_decision_report(
        database_url=database_url,
        output_md_path=tmp_path / "data_decision_report.md",
        output_metrics_csv_path=tmp_path / "data_decision_metrics.csv",
        browser_audit_csv_path=browser_audit_path,
        slow_queue_path=queue_path,
        expanded_event_study_results_path=event_study_path,
        baseline_event_study_results_path=tmp_path / "missing_baseline_results.csv",
        expanded_clean_events_path=clean_events_path,
        baseline_clean_events_path=tmp_path / "missing_baseline_clean.csv",
        labeled_validation_path=labeled_validation_path,
        audit_output_csv_path=tmp_path / "availability.csv",
        audit_output_md_path=tmp_path / "availability.md",
    )

    report = result.markdown_path.read_text(encoding="utf-8")
    metrics = list(csv.DictReader(result.metrics_csv_path.open()))
    eligible_videos = next(row for row in metrics if row["metric"] == "total_eligible_videos")
    available_transcripts = next(
        row for row in metrics if row["metric"] == "available_transcripts"
    )
    transcript_coverage = next(
        row for row in metrics if row["metric"] == "transcript_coverage_rate"
    )
    recoverable = next(
        row for row in metrics if row["metric"] == "browser_audited_recoverable_videos"
    )
    manual_validation = next(
        row for row in metrics if row["metric"] == "manually_validate_events"
    )
    assert "What conclusions can be made now?" in report
    assert eligible_videos["value"] == "2"
    assert available_transcripts["value"] == "1"
    assert transcript_coverage["value"] == "0.5"
    assert recoverable["value"] == "1"
    assert manual_validation["value"] == "1"
    assert result.preferred_next_investment == "manually_validate_events"
