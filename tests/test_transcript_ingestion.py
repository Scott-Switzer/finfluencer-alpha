import csv
import hashlib
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.expanded_robustness import build_expanded_robustness_outputs
from finfluencer_alpha.transcript_classify import extract_events_from_new_transcripts
from finfluencer_alpha.transcript_ingestion import (
    build_expanded_transcript_coverage_report,
    build_transcript_provenance_report,
    import_manual_transcripts_with_summary,
    plan_next_paid_transcript_batch,
)
from finfluencer_alpha.yfinance_market_data import YFINANCE_MARKET_DATA_COLUMNS
from finfluencer_alpha.youtube_transcripts import (
    TranscriptFetchResult,
    TranscriptSegment,
    store_transcript_result,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "ingestion.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _insert_video(
    database_url: str,
    video_id: str,
    *,
    creator: str = "Creator A",
    published_at: str = "2026-01-01T00:00:00Z",
    title: str = "Stocks to Buy Now",
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                f"channel_{creator}",
                creator,
                published_at,
                title,
                f"https://www.youtube.com/watch?v={video_id}",
            ),
        )
        conn.commit()


def _store_transcript(
    database_url: str,
    video_id: str,
    *,
    source: str = "youtube",
    text: str = "covered transcript text",
    provider: str = "youtube_transcript_api",
) -> None:
    with connect(database_url) as conn:
        store_transcript_result(
            conn,
            TranscriptFetchResult(
                video_id=video_id,
                provider_name=provider,
                provider_version="test",
                status="available",
                transcript_source=source,
                retrieval_method="test_import",
                retrieval_status="available",
                full_text=text,
                full_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                segments=[TranscriptSegment(video_id, 0, 0.0, None, text)],
                collected_at="2026-05-12T00:00:00Z",
                character_count=len(text),
                word_count=len(text.split()),
            ),
        )
        conn.commit()


def _write_manual_csv(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "video_id",
        "transcript_text",
        "transcript_source",
        "collected_at",
        "collector_notes",
    ]
    path.write_text(
        ",".join(columns)
        + "\n"
        + "\n".join(",".join(row.get(column, "") for column in columns) for row in rows)
        + "\n",
        encoding="utf-8",
    )


def _write_csv_rows(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _long_transcript() -> str:
    return "I am buying Nvidia stock because revenue growth and valuation look attractive. " * 8


def _transcript_event_count(database_url: str) -> int:
    with connect(database_url) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM transcript_recommendation_events").fetchone()
    return int(row["count"])


def _write_market_data_csv(path: Path) -> None:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(26):
        rows.append(
            {
                "original_ticker": "NVDA",
                "ticker": "NVDA",
                "date": (start + timedelta(days=offset)).isoformat(),
                "adjusted_close": 100 + offset,
                "volume": 1_000_000 + offset,
                "benchmark_ticker": "SPY",
                "benchmark_adjusted_close": 100 + (offset * 0.5),
                "market_cap": "",
                "sector": "",
                "industry": "",
                "beta": "",
                "average_dollar_volume": "",
                "data_source": "yfinance_yahoo_prototype",
                "downloaded_at_utc": "2026-05-12T00:00:00Z",
            }
        )
    _write_csv_rows(path, rows, YFINANCE_MARKET_DATA_COLUMNS)


def test_next_paid_batch_selection_is_deterministic(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "deterministic.db")
    _insert_video(database_url, "video_b", published_at="2026-01-01T00:00:00Z")
    _insert_video(database_url, "video_a", published_at="2026-01-01T00:00:00Z")
    _insert_video(database_url, "video_c", published_at="2025-12-31T00:00:00Z")

    result = plan_next_paid_transcript_batch(
        credit_budget=3,
        csv_path=tmp_path / "batch.csv",
        md_path=tmp_path / "batch.md",
    )
    df = pd.read_csv(result.csv_path)

    assert result.selected_count == 3
    assert list(df["video_id"]) == ["video_a", "video_b", "video_c"]
    assert list(df["selected_order"]) == [1, 2, 3]


def test_next_paid_batch_respects_credit_budget(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "budget.db")
    for index in range(5):
        _insert_video(database_url, f"video_{index}", published_at=f"2026-01-0{index + 1}T00:00:00Z")

    result = plan_next_paid_transcript_batch(
        credit_budget=2,
        csv_path=tmp_path / "batch.csv",
        md_path=tmp_path / "batch.md",
    )
    df = pd.read_csv(result.csv_path)

    assert result.selected_count == 2
    assert int(df["estimated_credit_cost"].sum()) == 2


def test_planning_mode_makes_no_provider_call(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "no_provider.db")
    _insert_video(database_url, "video_a")

    import finfluencer_alpha.provider_transcripts as provider_transcripts

    def fail_provider_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("planning mode should not call transcript providers")

    monkeypatch.setattr(provider_transcripts, "collect_provider_transcripts", fail_provider_call)

    result = plan_next_paid_transcript_batch(
        credit_budget=1,
        csv_path=tmp_path / "batch.csv",
        md_path=tmp_path / "batch.md",
    )

    assert result.selected_count == 1


def test_manual_import_rejects_unknown_video_id(monkeypatch, tmp_path: Path) -> None:
    _use_temp_db(monkeypatch, tmp_path, "manual_missing_id.db")
    csv_path = tmp_path / "manual.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "missing_video",
                "transcript_text": _long_transcript(),
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            }
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    summary = pd.read_csv(result.summary_csv_path)

    assert result.rejected_count == 1
    assert summary.loc[0, "status"] == "rejected_unknown_video_id"


def test_manual_import_rejects_empty_transcript(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "manual_empty.db")
    _insert_video(database_url, "video_a")
    csv_path = tmp_path / "manual.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "video_a",
                "transcript_text": "",
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            }
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    summary = pd.read_csv(result.summary_csv_path)

    assert result.rejected_count == 1
    assert summary.loc[0, "status"] == "rejected_empty_transcript"


def test_manual_import_detects_duplicate_checksum(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "manual_duplicate.db")
    _insert_video(database_url, "video_a")
    _insert_video(database_url, "video_b")
    csv_path = tmp_path / "manual.csv"
    transcript = _long_transcript()
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "video_a",
                "transcript_text": transcript,
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            },
            {
                "video_id": "video_b",
                "transcript_text": transcript,
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            },
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    summary = pd.read_csv(result.summary_csv_path)

    assert result.duplicate_checksum_count == 2
    assert set(summary["status"]) == {"rejected_duplicate_checksum"}


def test_manual_import_does_not_overwrite_by_default(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "manual_existing.db")
    _insert_video(database_url, "video_a")
    _store_transcript(database_url, "video_a", text="existing transcript")
    csv_path = tmp_path / "manual.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "video_id": "video_a",
                "transcript_text": _long_transcript(),
                "transcript_source": "manual_youtube_ui",
                "collected_at": "2026-05-12T00:00:00Z",
                "collector_notes": "public transcript panel",
            }
        ],
    )

    result = import_manual_transcripts_with_summary(
        input_path=csv_path,
        dry_run=False,
        confirm_import=True,
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )

    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT full_text FROM youtube_transcripts WHERE video_id = 'video_a'"
        ).fetchone()
    assert result.imported_count == 0
    assert result.skipped_existing_count == 1
    assert row["full_text"] == "existing transcript"


def test_provenance_report_builds_from_fixtures(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "provenance.db")
    _insert_video(database_url, "video_paid", creator="Creator A", published_at="2026-01-01T00:00:00Z")
    _insert_video(database_url, "video_native", creator="Creator B", published_at="2025-01-01T00:00:00Z")
    _insert_video(database_url, "video_manual", creator="Creator B", published_at="2025-02-01T00:00:00Z")
    _insert_video(database_url, "video_missing", creator="Creator C", published_at="2024-01-01T00:00:00Z")
    _store_transcript(
        database_url,
        "video_paid",
        source="paid_provider",
        provider="TranscriptAPI.com",
        text=_long_transcript(),
    )
    _store_transcript(database_url, "video_native", source="youtube", text=_long_transcript())
    _store_transcript(
        database_url,
        "video_manual",
        source="manual_youtube_ui",
        provider="manual_youtube_ui",
        text=_long_transcript() + " extra",
    )

    result = build_transcript_provenance_report(
        csv_path=tmp_path / "provenance.csv",
        md_path=tmp_path / "provenance.md",
        methodology_note_path=tmp_path / "methodology.md",
        planned_batch_path=tmp_path / "missing_planned_batch.csv",
        expanded_coverage_csv_path=tmp_path / "expanded_coverage.csv",
        expanded_coverage_md_path=tmp_path / "expanded_coverage.md",
    )
    summary = pd.read_csv(result.csv_path)

    assert result.total_videos == 4
    assert result.videos_with_transcripts == 3
    assert result.videos_missing_transcripts == 1
    assert "paid_provider_transcript_count" in set(summary["label"])
    assert result.md_path.exists()
    assert result.methodology_note_path.exists()


def test_provenance_recommends_downstream_work_after_paid_batch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "provenance_paid_done.db")
    _insert_video(database_url, "video_paid", published_at="2026-01-01T00:00:00Z")
    _insert_video(database_url, "video_missing", published_at="2026-01-02T00:00:00Z")
    _store_transcript(
        database_url,
        "video_paid",
        source="paid_provider",
        provider="TranscriptAPI.com",
        text=_long_transcript(),
    )
    planned_batch_path = tmp_path / "next_paid_transcript_batch_61.csv"
    planned_batch_path.write_text("video_id\nvideo_paid\n", encoding="utf-8")

    result = build_transcript_provenance_report(
        csv_path=tmp_path / "provenance.csv",
        md_path=tmp_path / "provenance.md",
        methodology_note_path=tmp_path / "methodology.md",
        planned_batch_path=planned_batch_path,
        expanded_coverage_csv_path=tmp_path / "expanded_coverage.csv",
        expanded_coverage_md_path=tmp_path / "expanded_coverage.md",
    )

    text = result.md_path.read_text(encoding="utf-8")
    assert "Paid-provider batch has already been run" in text
    assert "downstream event extraction/classification" in text
    assert "Run the planned 61-video paid provider batch" not in text


def test_new_transcript_event_extraction_does_not_duplicate_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "incremental_no_dupes.db")
    _insert_video(database_url, "video_paid", title="Buy Nvidia stock now")
    _store_transcript(
        database_url,
        "video_paid",
        source="paid_provider",
        provider="TranscriptAPI.com",
        text=_long_transcript(),
    )

    first = extract_events_from_new_transcripts(
        summary_csv_path=tmp_path / "first.csv",
        summary_md_path=tmp_path / "first.md",
    )
    first_event_count = _transcript_event_count(database_url)
    second = extract_events_from_new_transcripts(
        summary_csv_path=tmp_path / "second.csv",
        summary_md_path=tmp_path / "second.md",
    )

    assert first.transcripts_scanned == 1
    assert first.new_events_found == 1
    assert first_event_count == 1
    assert second.transcripts_scanned == 0
    assert second.new_events_found == 0
    assert _transcript_event_count(database_url) == first_event_count


def test_short_transcripts_do_not_break_incremental_extraction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "short_incremental.db")
    _insert_video(database_url, "video_short")
    _store_transcript(
        database_url,
        "video_short",
        source="paid_provider",
        provider="TranscriptAPI.com",
        text="Buy NVDA.",
    )

    result = extract_events_from_new_transcripts(
        summary_csv_path=tmp_path / "summary.csv",
        summary_md_path=tmp_path / "summary.md",
    )

    assert result.transcripts_scanned == 1
    assert result.summary_md_path.exists()


def test_failed_provider_rows_do_not_break_expanded_coverage_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "coverage_failures.db")
    _insert_video(database_url, "video_paid")
    _store_transcript(
        database_url,
        "video_paid",
        source="paid_provider",
        provider="TranscriptAPI.com",
        text=_long_transcript(),
    )
    paid_summary = tmp_path / "paid_summary.csv"
    _write_csv_rows(
        paid_summary,
        [
            {
                "video_id": "failed_one",
                "selected_order": 1,
                "status": "provider_failed",
                "provider": "TranscriptAPI.com",
                "message": "HTTP 404",
            },
            {
                "video_id": "failed_two",
                "selected_order": 2,
                "status": "provider_failed",
                "provider": "TranscriptAPI.com",
                "message": "HTTP 408",
            },
        ],
        [
            "video_id",
            "selected_order",
            "status",
            "provider",
            "transcript_source",
            "word_count",
            "character_count",
            "checksum",
            "estimated_credit_cost",
            "message",
        ],
    )

    result = build_expanded_transcript_coverage_report(
        csv_path=tmp_path / "coverage.csv",
        md_path=tmp_path / "coverage.md",
        paid_summary_path=paid_summary,
    )
    text = result.md_path.read_text(encoding="utf-8")

    assert result.failed_provider_rows == 2
    assert "failed_one" in text
    assert "failed_two" in text


def test_expanded_robustness_outputs_do_not_overwrite_baseline_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "expanded_robustness.db")
    _insert_video(database_url, "video_paid", title="Buy Nvidia stock now")
    _store_transcript(
        database_url,
        "video_paid",
        source="paid_provider",
        provider="TranscriptAPI.com",
        text=_long_transcript(),
    )
    extract_events_from_new_transcripts(
        summary_csv_path=tmp_path / "incremental.csv",
        summary_md_path=tmp_path / "incremental.md",
    )

    import finfluencer_alpha.expanded_robustness as expanded_robustness

    baseline_main = tmp_path / "baseline_main_table.csv"
    baseline_main.write_text(
        "event_count,matched_count,mean_abnormal_return_1d,mean_abnormal_return_5d,"
        "mean_abnormal_return_20d,mean_car_5d,mean_car_20d\n"
        "1,1,0.010000,0.020000,0.030000,0.040000,0.050000\n",
        encoding="utf-8",
    )
    baseline_clean = tmp_path / "baseline_clean_events.csv"
    baseline_results = tmp_path / "baseline_event_study_results.csv"
    baseline_before = baseline_main.read_text(encoding="utf-8")
    monkeypatch.setattr(expanded_robustness, "DEFAULT_MAIN_TABLE_CSV_PATH", baseline_main)
    monkeypatch.setattr(expanded_robustness, "DEFAULT_CLEAN_EVENTS_PATH", baseline_clean)
    monkeypatch.setattr(expanded_robustness, "DEFAULT_EVENT_STUDY_RESULTS_PATH", baseline_results)

    market_data = tmp_path / "market_data.csv"
    _write_market_data_csv(market_data)
    output_dir = tmp_path / "expanded_outputs"
    result = build_expanded_robustness_outputs(
        output_dir=output_dir,
        input_market_data=market_data,
    )
    comparison = result.expanded_comparison_path.read_text(encoding="utf-8")

    assert baseline_main.read_text(encoding="utf-8") == baseline_before
    assert result.expanded_clean_events_path.parent == output_dir
    assert result.expanded_event_study_results_path.parent == output_dir
    assert result.expanded_clean_events_path != baseline_clean
    assert result.expanded_event_study_results_path != baseline_results
    assert "Baseline clean events: 1" in comparison
    assert "Expanded clean events:" in comparison
