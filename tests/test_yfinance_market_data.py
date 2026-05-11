from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from finfluencer_alpha.event_study import run_event_study, validate_market_data_import
from finfluencer_alpha.yfinance_market_data import (
    YFINANCE_MARKET_DATA_COLUMNS,
    build_yfinance_fetch_plan,
    fetch_yfinance_market_data,
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


def _request_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "event_id": "1",
        "video_id": "video1",
        "ticker": "AAA",
        "company_name": "AAA Corp",
        "creator": "Creator A",
        "title": "Buying AAA",
        "published_at": "2026-01-05T12:00:00Z",
        "event_date_utc": "2026-01-05",
        "event_date_weekday_adjusted": "2026-01-05",
        "recommended_start_date": "2025-12-20",
        "recommended_end_date": "2026-01-20",
        "recommendation_type": "buy",
        "direction": "positive",
        "confidence": "0.91",
        "evidence_quality": "strong",
        "source_transcript_type": "external_provider:TranscriptAPI.com",
        "video_url": "https://www.youtube.com/watch?v=video1",
    }
    row.update(overrides)
    return row


def _unique_ticker_row(ticker: str, company_name: str = "Company") -> dict[str, object]:
    return {
        "ticker": ticker,
        "company_name": company_name,
        "event_count": "1",
        "first_event_date": "2026-01-05",
        "last_event_date": "2026-01-05",
    }


def _history_frame(ticker: str, start: date, end: date) -> pd.DataFrame:
    dates = pd.date_range(start=start, end=end, freq="B")
    base = 400.0 if ticker == "SPY" else 100.0
    frame = pd.DataFrame(
        {
            "Adj Close": [base + index for index, _ in enumerate(dates)],
            "Close": [base + index + 0.5 for index, _ in enumerate(dates)],
            "Volume": [1_000_000 + index for index, _ in enumerate(dates)],
        },
        index=dates,
    )
    frame.columns = pd.MultiIndex.from_tuples(
        [(column, ticker) for column in frame.columns],
        names=["Price", "Ticker"],
    )
    return frame


def _write_request_inputs(tmp_path: Path, tickers: list[str]) -> tuple[Path, Path]:
    request_path = tmp_path / "market_data_request.csv"
    tickers_path = tmp_path / "unique_tickers.csv"
    _write_csv(
        request_path,
        [_request_row(ticker=ticker, event_id=str(index)) for index, ticker in enumerate(tickers, 1)],
    )
    _write_csv(tickers_path, [_unique_ticker_row(ticker) for ticker in tickers])
    return request_path, tickers_path


def _write_aliases(path: Path, rows: list[dict[str, object]]) -> None:
    _write_csv(path, rows)


def test_dry_run_does_not_call_yfinance(tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["AAA"])

    def fail_downloader(*args: object, **kwargs: object) -> pd.DataFrame:
        raise AssertionError("dry-run should not call yfinance downloader")

    result = fetch_yfinance_market_data(
        input_request_path=request_path,
        input_tickers_path=tickers_path,
        output_path=tmp_path / "yfinance.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        dry_run=True,
        downloader=fail_downloader,
    )

    assert result.dry_run
    assert result.tickers_requested == 1
    assert not result.output_path.exists()


def test_refuses_without_confirm_yfinance_run(tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["AAA"])

    with pytest.raises(PermissionError, match="confirm-yfinance-run"):
        fetch_yfinance_market_data(
            input_request_path=request_path,
            input_tickers_path=tickers_path,
            output_path=tmp_path / "yfinance.csv",
            summary_md_path=tmp_path / "summary.md",
            summary_csv_path=tmp_path / "summary.csv",
            confirm_yfinance_run=False,
            downloader=_history_frame,
        )


def test_output_schema_matches_required_columns(tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["AAA"])

    result = fetch_yfinance_market_data(
        input_request_path=request_path,
        input_tickers_path=tickers_path,
        output_path=tmp_path / "yfinance.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        confirm_yfinance_run=True,
        downloader=_history_frame,
    )
    df = pd.read_csv(result.output_path)

    assert list(df.columns) == YFINANCE_MARKET_DATA_COLUMNS
    assert df["original_ticker"].eq("AAA").all()
    assert set(df["data_source"]) == {"yfinance_yahoo_prototype"}


def test_benchmark_merge_works(tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["AAA"])

    result = fetch_yfinance_market_data(
        input_request_path=request_path,
        input_tickers_path=tickers_path,
        output_path=tmp_path / "yfinance.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        confirm_yfinance_run=True,
        downloader=_history_frame,
    )
    df = pd.read_csv(result.output_path)

    assert df["benchmark_ticker"].eq("SPY").all()
    assert df["benchmark_adjusted_close"].notna().all()
    assert df.iloc[0]["benchmark_adjusted_close"] == 400.0


def test_failed_ticker_is_reported_and_does_not_crash_all_downloads(tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["AAA", "FAIL"])

    def downloader(ticker: str, start: date, end: date) -> pd.DataFrame:
        if ticker == "FAIL":
            raise RuntimeError("simulated failure")
        return _history_frame(ticker, start, end)

    result = fetch_yfinance_market_data(
        input_request_path=request_path,
        input_tickers_path=tickers_path,
        output_path=tmp_path / "yfinance.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        confirm_yfinance_run=True,
        downloader=downloader,
    )
    df = pd.read_csv(result.output_path)
    summary = pd.read_csv(result.summary_csv_path)

    assert result.failed_tickers == ("FAIL",)
    assert set(df["ticker"]) == {"AAA"}
    assert summary[summary["ticker"] == "FAIL"].iloc[0]["status"] == "failed"


def test_event_study_can_use_yfinance_market_data_csv(tmp_path: Path) -> None:
    market_data_path = tmp_path / "yfinance_market_data.csv"
    events_path = tmp_path / "clean_events.csv"
    _write_csv(
        market_data_path,
        [
            {
                "original_ticker": "AAA",
                "ticker": "AAA",
                "date": f"2026-01-{day:02d}",
                "adjusted_close": 100 + day,
                "volume": 1_000_000,
                "benchmark_ticker": "SPY",
                "benchmark_adjusted_close": 400 + day,
                "market_cap": "",
                "sector": "",
                "industry": "",
                "beta": "",
                "average_dollar_volume": "",
                "data_source": "yfinance_yahoo_prototype",
                "downloaded_at_utc": "2026-01-01T00:00:00Z",
            }
            for day in range(5, 15)
        ],
    )
    _write_csv(
        events_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "published_at": "2026-01-05T12:00:00Z",
                "recommendation_type": "buy",
                "direction": "positive",
                "confidence": "0.91",
            }
        ],
    )

    validation = validate_market_data_import(input_path=market_data_path)
    result = run_event_study(
        input_events=events_path,
        input_market_data=market_data_path,
        output_path=tmp_path / "event_study.csv",
        summary_md_path=tmp_path / "event_study.md",
    )
    output = pd.read_csv(result.output_path)

    assert validation.row_count == 10
    assert result.events_matched == 1
    assert output.loc[0, "data_source"] == "yfinance_yahoo_prototype"
    assert "Using interim yfinance" in result.warning


def test_alias_file_maps_sq_to_xyz(tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["SQ"])
    aliases_path = tmp_path / "ticker_aliases.csv"
    _write_aliases(
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

    plan = build_yfinance_fetch_plan(
        input_request_path=request_path,
        input_tickers_path=tickers_path,
        output_path=tmp_path / "yfinance.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        ticker_aliases_path=aliases_path,
    )

    assert plan.data_ticker_by_original["SQ"] == "XYZ"
    assert plan.alias_mappings == (("SQ", "XYZ"),)


def test_yfinance_fetch_uses_xyz_for_sq_and_preserves_original_ticker(tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["SQ"])
    aliases_path = tmp_path / "ticker_aliases.csv"
    _write_aliases(
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
    calls: list[str] = []

    def downloader(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append(ticker)
        return _history_frame(ticker, start, end)

    result = fetch_yfinance_market_data(
        input_request_path=request_path,
        input_tickers_path=tickers_path,
        output_path=tmp_path / "yfinance.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        ticker_aliases_path=aliases_path,
        confirm_yfinance_run=True,
        downloader=downloader,
    )
    df = pd.read_csv(result.output_path)
    summary = pd.read_csv(result.summary_csv_path)
    summary_md = result.summary_md_path.read_text(encoding="utf-8")

    assert "SPY" in calls
    assert "XYZ" in calls
    assert "SQ" not in calls
    assert set(df["original_ticker"]) == {"SQ"}
    assert set(df["ticker"]) == {"XYZ"}
    row = summary[summary["role"] == "security"].iloc[0]
    assert row["original_ticker"] == "SQ"
    assert row["data_ticker"] == "XYZ"
    assert str(row["ticker_alias_applied"]).lower() == "true"
    assert "SQ -> XYZ" in summary_md


def test_event_study_matches_sq_event_to_xyz_market_data(tmp_path: Path) -> None:
    market_data_path = tmp_path / "yfinance_market_data.csv"
    events_path = tmp_path / "clean_events.csv"
    aliases_path = tmp_path / "ticker_aliases.csv"
    _write_aliases(
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
    _write_csv(
        market_data_path,
        [
            {
                "original_ticker": "SQ",
                "ticker": "XYZ",
                "date": f"2026-01-{day:02d}",
                "adjusted_close": 100 + day,
                "volume": 1_000_000,
                "benchmark_ticker": "SPY",
                "benchmark_adjusted_close": 400 + day,
                "market_cap": "",
                "sector": "",
                "industry": "",
                "beta": "",
                "average_dollar_volume": "",
                "data_source": "yfinance_yahoo_prototype",
                "downloaded_at_utc": "2026-01-01T00:00:00Z",
            }
            for day in range(5, 15)
        ],
    )
    _write_csv(
        events_path,
        [
            {
                "event_id": "1",
                "ticker": "SQ",
                "published_at": "2026-01-05T12:00:00Z",
                "recommendation_type": "buy",
                "direction": "positive",
                "confidence": "0.91",
            }
        ],
    )

    result = run_event_study(
        input_events=events_path,
        input_market_data=market_data_path,
        ticker_aliases_path=aliases_path,
        output_path=tmp_path / "event_study.csv",
        summary_md_path=tmp_path / "event_study.md",
    )
    output = pd.read_csv(result.output_path)

    assert result.events_matched == 1
    assert output.loc[0, "ticker"] == "SQ"
    assert output.loc[0, "data_ticker"] == "XYZ"
    assert str(output.loc[0, "ticker_alias_applied"]).lower() == "true"


def test_no_llm_or_openai_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    request_path, tickers_path = _write_request_inputs(tmp_path, ["AAA"])

    def fail_post(*args: object, **kwargs: object) -> None:
        raise AssertionError("OpenAI/LLM calls should not be made")

    monkeypatch.setattr("requests.post", fail_post)
    fetch_yfinance_market_data(
        input_request_path=request_path,
        input_tickers_path=tickers_path,
        output_path=tmp_path / "yfinance.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        confirm_yfinance_run=True,
        downloader=_history_frame,
    )
