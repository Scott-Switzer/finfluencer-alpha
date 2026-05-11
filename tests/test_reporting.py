from __future__ import annotations

import csv
import socket
from pathlib import Path

import pandas as pd
import pytest

from finfluencer_alpha.reporting import (
    CHART_FILENAMES,
    build_event_study_charts,
    build_event_study_reporting,
    diagnose_event_study_matches,
)


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


def _business_dates(start: str, periods: int) -> list[str]:
    return [value.date().isoformat() for value in pd.bdate_range(start=start, periods=periods)]


def _build_fixture_inputs(tmp_path: Path) -> dict[str, Path]:
    clean_events_path = tmp_path / "clean_auto_labeled_events.csv"
    event_study_results_path = tmp_path / "event_study_results.csv"
    market_data_path = tmp_path / "yfinance_market_data.csv"
    threshold_path = tmp_path / "clean_event_threshold_sensitivity.csv"
    yfinance_summary_path = tmp_path / "yfinance_fetch_summary.csv"
    aliases_path = tmp_path / "ticker_aliases.csv"

    _write_csv(
        clean_events_path,
        [
            {
                "event_id": "1",
                "video_id": "v1",
                "creator": "Creator A",
                "title": "AAA thesis",
                "published_at": "2026-01-05T12:00:00Z",
                "event_date_utc": "2026-01-05",
                "event_date_weekday_adjusted": "2026-01-05",
                "ticker": "AAA",
                "recommendation_type": "buy",
                "direction": "positive",
            },
            {
                "event_id": "2",
                "video_id": "v2",
                "creator": "Creator B",
                "title": "BBB thesis",
                "published_at": "2026-01-06T12:00:00Z",
                "event_date_utc": "2026-01-06",
                "event_date_weekday_adjusted": "2026-01-06",
                "ticker": "BBB",
                "recommendation_type": "buy",
                "direction": "positive",
            },
            {
                "event_id": "3",
                "video_id": "v3",
                "creator": "Creator A",
                "title": "SQ thesis",
                "published_at": "2026-01-07T12:00:00Z",
                "event_date_utc": "2026-01-07",
                "event_date_weekday_adjusted": "2026-01-07",
                "ticker": "SQ",
                "recommendation_type": "price_target",
                "direction": "positive",
            },
        ],
    )

    _write_csv(
        event_study_results_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "data_ticker": "AAA",
                "ticker_alias_applied": False,
                "event_date_weekday_adjusted": "2026-01-05",
                "matched_market_date": "2026-01-05",
                "recommendation_type": "buy",
                "direction": "positive",
                "confidence": "0.90",
                "adjusted_close": "100",
                "benchmark_ticker": "SPY",
                "benchmark_adjusted_close": "300",
                "return_1d": "0.010000",
                "benchmark_return_1d": "0.002000",
                "abnormal_return_1d": "0.008000",
                "return_5d": "0.050000",
                "benchmark_return_5d": "0.010000",
                "abnormal_return_5d": "0.040000",
                "data_source": "yfinance_yahoo_prototype",
            },
            {
                "event_id": "3",
                "ticker": "SQ",
                "data_ticker": "XYZ",
                "ticker_alias_applied": True,
                "event_date_weekday_adjusted": "2026-01-07",
                "matched_market_date": "2026-01-07",
                "recommendation_type": "price_target",
                "direction": "positive",
                "confidence": "0.85",
                "adjusted_close": "200",
                "benchmark_ticker": "SPY",
                "benchmark_adjusted_close": "320",
                "return_1d": "0.000000",
                "benchmark_return_1d": "0.001000",
                "abnormal_return_1d": "-0.001000",
                "return_5d": "0.030000",
                "benchmark_return_5d": "0.010000",
                "abnormal_return_5d": "0.020000",
                "data_source": "yfinance_yahoo_prototype",
            },
        ],
    )

    dates = _business_dates("2026-01-05", 30)
    market_rows: list[dict[str, object]] = []
    for index, date_value in enumerate(dates):
        market_rows.append(
            {
                "original_ticker": "AAA",
                "ticker": "AAA",
                "date": date_value,
                "adjusted_close": 100 + index,
                "volume": 1_000_000 + (index * 1000),
                "benchmark_ticker": "SPY",
                "benchmark_adjusted_close": 300 + index,
                "market_cap": "",
                "sector": "",
                "industry": "",
                "beta": "",
                "average_dollar_volume": "",
                "data_source": "yfinance_yahoo_prototype",
                "downloaded_at_utc": "2026-01-01T00:00:00Z",
            }
        )
        market_rows.append(
            {
                "original_ticker": "SQ",
                "ticker": "XYZ",
                "date": date_value,
                "adjusted_close": 200 + index,
                "volume": 2_000_000 + (index * 1000),
                "benchmark_ticker": "SPY",
                "benchmark_adjusted_close": 320 + index,
                "market_cap": "",
                "sector": "",
                "industry": "",
                "beta": "",
                "average_dollar_volume": "",
                "data_source": "yfinance_yahoo_prototype",
                "downloaded_at_utc": "2026-01-01T00:00:00Z",
            }
        )
    _write_csv(market_data_path, market_rows)

    _write_csv(
        threshold_path,
        [
            {
                "min_confidence": "0.90",
                "included_strict_count": "10",
                "included_with_review_count": "10",
                "included_with_weak_evidence_count": "10",
                "excluded_count": "2",
                "unique_ticker_count": "2",
                "unique_creator_count": "2",
            },
            {
                "min_confidence": "0.75",
                "included_strict_count": "12",
                "included_with_review_count": "12",
                "included_with_weak_evidence_count": "12",
                "excluded_count": "0",
                "unique_ticker_count": "3",
                "unique_creator_count": "2",
            },
        ],
    )

    _write_csv(
        yfinance_summary_path,
        [
            {
                "original_ticker": "SQ",
                "data_ticker": "XYZ",
                "ticker_alias_applied": True,
                "ticker": "XYZ",
                "role": "security",
                "status": "downloaded",
                "row_count": "30",
            }
        ],
    )

    _write_csv(
        aliases_path,
        [
            {
                "original_ticker": "SQ",
                "data_ticker": "XYZ",
                "company_name": "Block",
                "effective_date": "2025-01-21",
                "reason": "Block ticker changed from SQ to XYZ",
            }
        ],
    )

    return {
        "clean_events": clean_events_path,
        "event_results": event_study_results_path,
        "market_data": market_data_path,
        "thresholds": threshold_path,
        "yfinance_summary": yfinance_summary_path,
        "aliases": aliases_path,
    }


def test_diagnostics_identifies_unmatched_events(tmp_path: Path) -> None:
    paths = _build_fixture_inputs(tmp_path)
    result = diagnose_event_study_matches(
        event_study_results_path=paths["event_results"],
        clean_events_path=paths["clean_events"],
        market_data_path=paths["market_data"],
        ticker_aliases_path=paths["aliases"],
        output_csv_path=tmp_path / "diagnostics.csv",
        output_md_path=tmp_path / "diagnostics.md",
    )
    diagnostics = pd.read_csv(result.csv_path)
    unmatched = diagnostics[diagnostics["missing_market_data_flag"] == True]  # noqa: E712

    assert result.total_clean_events == 3
    assert result.matched_events == 2
    assert result.unmatched_events == 1
    assert len(unmatched) == 1
    assert unmatched.iloc[0]["event_id"] == 2
    assert unmatched.iloc[0]["missing_market_data_reason"] == "no ticker data"


def test_reporting_table_computes_means_and_medians_and_t_stat(tmp_path: Path) -> None:
    paths = _build_fixture_inputs(tmp_path)
    result = build_event_study_reporting(
        event_study_results_path=paths["event_results"],
        clean_events_path=paths["clean_events"],
        threshold_sensitivity_path=paths["thresholds"],
        market_data_path=paths["market_data"],
        yfinance_fetch_summary_path=paths["yfinance_summary"],
        main_table_csv_path=tmp_path / "main.csv",
        main_table_md_path=tmp_path / "main.md",
        by_creator_csv_path=tmp_path / "by_creator.csv",
        by_ticker_csv_path=tmp_path / "by_ticker.csv",
        by_year_csv_path=tmp_path / "by_year.csv",
        by_recommendation_type_csv_path=tmp_path / "by_type.csv",
        by_direction_csv_path=tmp_path / "by_direction.csv",
        robustness_csv_path=tmp_path / "robustness.csv",
        report_summary_md_path=tmp_path / "summary.md",
        methodology_note_path=tmp_path / "methodology.md",
    )
    main = pd.read_csv(result.main_table_csv_path).iloc[0]

    assert result.event_count == 3
    assert result.matched_count == 2
    assert float(main["mean_abnormal_return_1d"]) == pytest.approx(0.0035, abs=1e-6)
    assert float(main["median_abnormal_return_1d"]) == pytest.approx(0.0035, abs=1e-6)
    assert float(main["mean_abnormal_return_5d"]) == pytest.approx(0.03, abs=1e-6)
    assert _clean_str(main["t_stat_abnormal_return_1d"]) != ""


def _clean_str(value: object) -> str:
    return str(value or "").strip()


def test_grouped_summaries_and_methodology_note_created(tmp_path: Path) -> None:
    paths = _build_fixture_inputs(tmp_path)
    result = build_event_study_reporting(
        event_study_results_path=paths["event_results"],
        clean_events_path=paths["clean_events"],
        threshold_sensitivity_path=paths["thresholds"],
        market_data_path=paths["market_data"],
        yfinance_fetch_summary_path=paths["yfinance_summary"],
        main_table_csv_path=tmp_path / "main.csv",
        main_table_md_path=tmp_path / "main.md",
        by_creator_csv_path=tmp_path / "by_creator.csv",
        by_ticker_csv_path=tmp_path / "by_ticker.csv",
        by_year_csv_path=tmp_path / "by_year.csv",
        by_recommendation_type_csv_path=tmp_path / "by_type.csv",
        by_direction_csv_path=tmp_path / "by_direction.csv",
        robustness_csv_path=tmp_path / "robustness.csv",
        report_summary_md_path=tmp_path / "summary.md",
        methodology_note_path=tmp_path / "methodology.md",
    )
    by_creator = pd.read_csv(result.by_creator_csv_path)

    assert result.methodology_note_path.exists()
    assert "Creator A" in set(by_creator["group"])
    assert "Creator B" in set(by_creator["group"])
    assert Path(result.by_ticker_csv_path).exists()
    assert Path(result.by_year_csv_path).exists()
    assert Path(result.by_recommendation_type_csv_path).exists()
    assert Path(result.by_direction_csv_path).exists()


def test_charts_are_written_to_expected_paths(tmp_path: Path) -> None:
    paths = _build_fixture_inputs(tmp_path)
    result = build_event_study_charts(
        event_study_results_path=paths["event_results"],
        clean_events_path=paths["clean_events"],
        market_data_path=paths["market_data"],
        output_dir=tmp_path / "charts",
    )

    expected = {str((tmp_path / "charts" / filename).resolve()) for filename in CHART_FILENAMES}
    actual = {str(path.resolve()) for path in result.chart_paths}
    assert expected == actual
    assert all(path.exists() for path in result.chart_paths)


def test_reporting_makes_no_external_api_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    paths = _build_fixture_inputs(tmp_path)

    def fail_post(*args: object, **kwargs: object) -> None:
        raise AssertionError("External API calls should not be made during reporting.")

    def fail_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network sockets should not be used during reporting.")

    monkeypatch.setattr("requests.post", fail_post)
    monkeypatch.setattr(socket, "create_connection", fail_connection)

    diagnose_event_study_matches(
        event_study_results_path=paths["event_results"],
        clean_events_path=paths["clean_events"],
        market_data_path=paths["market_data"],
        ticker_aliases_path=paths["aliases"],
        output_csv_path=tmp_path / "diagnostics.csv",
        output_md_path=tmp_path / "diagnostics.md",
    )
    build_event_study_reporting(
        event_study_results_path=paths["event_results"],
        clean_events_path=paths["clean_events"],
        threshold_sensitivity_path=paths["thresholds"],
        market_data_path=paths["market_data"],
        yfinance_fetch_summary_path=paths["yfinance_summary"],
        main_table_csv_path=tmp_path / "main.csv",
        main_table_md_path=tmp_path / "main.md",
        by_creator_csv_path=tmp_path / "by_creator.csv",
        by_ticker_csv_path=tmp_path / "by_ticker.csv",
        by_year_csv_path=tmp_path / "by_year.csv",
        by_recommendation_type_csv_path=tmp_path / "by_type.csv",
        by_direction_csv_path=tmp_path / "by_direction.csv",
        robustness_csv_path=tmp_path / "robustness.csv",
        report_summary_md_path=tmp_path / "summary.md",
        methodology_note_path=tmp_path / "methodology.md",
    )
    build_event_study_charts(
        event_study_results_path=paths["event_results"],
        clean_events_path=paths["clean_events"],
        market_data_path=paths["market_data"],
        output_dir=tmp_path / "charts",
    )
