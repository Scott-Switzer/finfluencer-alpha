from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from finfluencer_alpha.market_data_prep import (
    MARKET_DATA_REQUEST_COLUMNS,
    THRESHOLDS,
    build_clean_event_threshold_sensitivity,
    build_market_data_request,
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


def _clean_event_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "event_id": "1",
        "video_id": "video1",
        "ticker": "AAA",
        "company_name": "AAA Corp",
        "creator": "Creator A",
        "title": "Buying AAA",
        "published_at": "2026-04-09T18:42:37Z",
        "event_date_utc": "2026-04-09",
        "recommendation_type": "buy",
        "direction": "positive",
        "confidence": "0.930",
        "evidence_quality": "strong",
        "source_transcript_type": "external_provider:TranscriptAPI.com",
        "video_url": "https://www.youtube.com/watch?v=video1",
    }
    row.update(overrides)
    return row


def _auto_labeled_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "event_id": "1",
        "video_id": "video1",
        "ticker": "AAA",
        "creator": "Creator A",
        "is_true_recommendation": "yes",
        "recommendation_type": "buy",
        "direction": "positive",
        "evidence_quality": "strong",
        "auto_label_confidence": "0.91",
        "auto_label_needs_review": "false",
    }
    row.update(overrides)
    return row


def test_market_data_request_required_columns(tmp_path: Path) -> None:
    input_path = tmp_path / "clean.csv"
    request_path = tmp_path / "market_data_request.csv"
    _write_csv(input_path, [_clean_event_row()])

    result = build_market_data_request(
        input_path=input_path,
        request_path=request_path,
        unique_tickers_path=tmp_path / "unique_tickers.csv",
        event_dates_by_ticker_path=tmp_path / "event_dates.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    df = pd.read_csv(result.request_path)

    assert list(df.columns) == MARKET_DATA_REQUEST_COLUMNS
    assert df.loc[0, "requested_price_fields"] == "adjusted_close, volume"
    assert df.loc[0, "requested_security_fields"] == (
        "sector, industry, market_cap, beta, average_dollar_volume"
    )
    assert df.loc[0, "preferred_benchmark"] == "SPY"


def test_unique_ticker_output_aggregates_correctly(tmp_path: Path) -> None:
    input_path = tmp_path / "clean.csv"
    _write_csv(
        input_path,
        [
            _clean_event_row(event_id="1", ticker="AAA", published_at="2026-04-09T12:00:00Z"),
            _clean_event_row(event_id="2", ticker="AAA", published_at="2026-04-11T12:00:00Z"),
            _clean_event_row(event_id="3", ticker="BBB", published_at="2026-04-10T12:00:00Z"),
        ],
    )

    build_market_data_request(
        input_path=input_path,
        request_path=tmp_path / "request.csv",
        unique_tickers_path=tmp_path / "unique.csv",
        event_dates_by_ticker_path=tmp_path / "event_dates.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    unique = pd.read_csv(tmp_path / "unique.csv")
    aaa = unique[unique["ticker"] == "AAA"].iloc[0]

    assert aaa["event_count"] == 2
    assert aaa["first_event_date"] == "2026-04-09"
    assert aaa["last_event_date"] == "2026-04-13"
    assert set(unique["ticker"]) == {"AAA", "BBB"}


def test_saturday_adjusts_to_monday(tmp_path: Path) -> None:
    input_path = tmp_path / "clean.csv"
    _write_csv(input_path, [_clean_event_row(published_at="2026-04-11T12:00:00Z")])

    build_market_data_request(
        input_path=input_path,
        request_path=tmp_path / "request.csv",
        unique_tickers_path=tmp_path / "unique.csv",
        event_dates_by_ticker_path=tmp_path / "event_dates.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    df = pd.read_csv(tmp_path / "request.csv")

    assert df.loc[0, "event_date_weekday_adjusted"] == "2026-04-13"


def test_sunday_adjusts_to_monday(tmp_path: Path) -> None:
    input_path = tmp_path / "clean.csv"
    _write_csv(input_path, [_clean_event_row(published_at="2026-04-12T12:00:00Z")])

    build_market_data_request(
        input_path=input_path,
        request_path=tmp_path / "request.csv",
        unique_tickers_path=tmp_path / "unique.csv",
        event_dates_by_ticker_path=tmp_path / "event_dates.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    df = pd.read_csv(tmp_path / "request.csv")

    assert df.loc[0, "event_date_weekday_adjusted"] == "2026-04-13"


def test_weekday_stays_same(tmp_path: Path) -> None:
    input_path = tmp_path / "clean.csv"
    _write_csv(input_path, [_clean_event_row(published_at="2026-04-09T12:00:00Z")])

    build_market_data_request(
        input_path=input_path,
        request_path=tmp_path / "request.csv",
        unique_tickers_path=tmp_path / "unique.csv",
        event_dates_by_ticker_path=tmp_path / "event_dates.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    df = pd.read_csv(tmp_path / "request.csv")

    assert df.loc[0, "event_date_weekday_adjusted"] == "2026-04-09"


def test_recommended_date_window_is_correct(tmp_path: Path) -> None:
    input_path = tmp_path / "clean.csv"
    adjusted = date(2026, 4, 9)
    _write_csv(input_path, [_clean_event_row(published_at="2026-04-09T12:00:00Z")])

    build_market_data_request(
        input_path=input_path,
        request_path=tmp_path / "request.csv",
        unique_tickers_path=tmp_path / "unique.csv",
        event_dates_by_ticker_path=tmp_path / "event_dates.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    df = pd.read_csv(tmp_path / "request.csv")

    assert df.loc[0, "recommended_start_date"] == (adjusted - timedelta(days=260)).isoformat()
    assert df.loc[0, "recommended_end_date"] == (adjusted + timedelta(days=45)).isoformat()


def test_threshold_sensitivity_creates_all_six_threshold_rows(tmp_path: Path) -> None:
    input_path = tmp_path / "auto.csv"
    _write_csv(
        input_path,
        [
            _auto_labeled_row(event_id="1", ticker="AAA", auto_label_confidence="0.91"),
            _auto_labeled_row(event_id="2", ticker="BBB", auto_label_confidence="0.80"),
            _auto_labeled_row(
                event_id="3",
                ticker="CCC",
                evidence_quality="weak",
                auto_label_confidence="0.90",
            ),
            _auto_labeled_row(
                event_id="4",
                ticker="DDD",
                auto_label_confidence="0.86",
                auto_label_needs_review="true",
            ),
            _auto_labeled_row(
                event_id="5",
                ticker="EEE",
                is_true_recommendation="no",
                auto_label_confidence="0.95",
            ),
            _auto_labeled_row(
                event_id="6",
                ticker="FFF",
                direction="unclear",
                auto_label_confidence="0.95",
            ),
        ],
    )

    result = build_clean_event_threshold_sensitivity(
        input_path=input_path,
        csv_path=tmp_path / "sensitivity.csv",
        markdown_path=tmp_path / "sensitivity.md",
    )
    df = pd.read_csv(result.csv_path)

    assert df["min_confidence"].round(2).tolist() == THRESHOLDS
    assert len(df) == 6
    assert result.threshold_rows == 6
    row_090 = df[df["min_confidence"].round(2) == 0.90].iloc[0]
    assert row_090["included_strict_count"] == 1
    assert row_090["included_with_weak_evidence_count"] == 2


def test_market_data_prep_makes_no_external_api_calls(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_on_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("market-data prep should not open network connections")

    monkeypatch.setattr("socket.create_connection", fail_on_network)
    clean_path = tmp_path / "clean.csv"
    auto_path = tmp_path / "auto.csv"
    _write_csv(clean_path, [_clean_event_row()])
    _write_csv(auto_path, [_auto_labeled_row()])

    build_market_data_request(
        input_path=clean_path,
        request_path=tmp_path / "request.csv",
        unique_tickers_path=tmp_path / "unique.csv",
        event_dates_by_ticker_path=tmp_path / "event_dates.csv",
        summary_md_path=tmp_path / "summary.md",
    )
    build_clean_event_threshold_sensitivity(
        input_path=auto_path,
        csv_path=tmp_path / "sensitivity.csv",
        markdown_path=tmp_path / "sensitivity.md",
    )
