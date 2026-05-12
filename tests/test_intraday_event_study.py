from __future__ import annotations

import csv
import socket
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from finfluencer_alpha.intraday_event_study import (
    fetch_yfinance_intraday_market_data,
    run_intraday_event_study,
    scan_intraday_event_feasibility,
)
from finfluencer_alpha.x_extension_plan import build_x_extension_cost_plan


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


def test_intraday_feasibility_identifies_recent_and_old_events(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.csv"
    alias_path = tmp_path / "aliases.csv"
    _write_csv(
        clean_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "creator": "Creator A",
                "title": "Recent",
                "published_at": "2026-05-01T15:00:00Z",
            },
            {
                "event_id": "2",
                "ticker": "BBB",
                "creator": "Creator B",
                "title": "Old",
                "published_at": "2026-02-01T15:00:00Z",
            },
        ],
    )
    _write_csv(
        alias_path,
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

    result = scan_intraday_event_feasibility(
        input_path=clean_path,
        ticker_aliases_path=alias_path,
        output_path=tmp_path / "feasibility.csv",
        summary_md_path=tmp_path / "feasibility.md",
        now_utc=datetime(2026, 5, 11, tzinfo=UTC),
    )
    output = pd.read_csv(result.output_path)

    assert result.total_events == 2
    assert result.eligible_events == 1
    assert bool(output[output["event_id"] == 1].iloc[0]["yfinance_intraday_eligible"]) is True
    assert bool(output[output["event_id"] == 2].iloc[0]["yfinance_intraday_eligible"]) is False


def test_intraday_feasibility_applies_ticker_alias(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.csv"
    alias_path = tmp_path / "aliases.csv"
    _write_csv(
        clean_path,
        [
            {
                "event_id": "1",
                "ticker": "SQ",
                "creator": "Creator",
                "title": "Alias test",
                "published_at": "2026-05-01T15:00:00Z",
            }
        ],
    )
    _write_csv(
        alias_path,
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
    result = scan_intraday_event_feasibility(
        input_path=clean_path,
        ticker_aliases_path=alias_path,
        output_path=tmp_path / "feasibility.csv",
        summary_md_path=tmp_path / "feasibility.md",
        now_utc=datetime(2026, 5, 11, tzinfo=UTC),
    )
    output = pd.read_csv(result.output_path)

    assert output.loc[0, "data_ticker"] == "XYZ"


def test_intraday_fetch_refuses_without_confirm(tmp_path: Path) -> None:
    feasibility_path = tmp_path / "feasibility.csv"
    _write_csv(
        feasibility_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "data_ticker": "AAA",
                "event_timestamp_utc": "2026-05-01T15:00:00Z",
                "yfinance_intraday_eligible": True,
            }
        ],
    )
    with pytest.raises(PermissionError, match="confirm-yfinance-run"):
        fetch_yfinance_intraday_market_data(
            feasibility_input_path=feasibility_path,
            output_path=tmp_path / "intraday.csv",
            summary_md_path=tmp_path / "summary.md",
            summary_csv_path=tmp_path / "summary.csv",
            confirm_yfinance_run=False,
            dry_run=False,
        )


def test_intraday_fetch_dry_run_does_not_call_yfinance_and_reports_metrics(tmp_path: Path) -> None:
    feasibility_path = tmp_path / "feasibility.csv"
    _write_csv(
        feasibility_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "data_ticker": "AAA",
                "event_timestamp_utc": "2026-05-01T15:00:00Z",
                "yfinance_intraday_eligible": True,
            }
        ],
    )

    def fail_downloader(*args: object, **kwargs: object) -> pd.DataFrame:
        raise AssertionError("dry-run should not call yfinance downloader")

    result = fetch_yfinance_intraday_market_data(
        feasibility_input_path=feasibility_path,
        output_path=tmp_path / "intraday.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        confirm_yfinance_run=False,
        dry_run=True,
        downloader=fail_downloader,
    )

    assert result.dry_run
    assert result.eligible_events == 1
    assert result.planned_event_windows == 1
    assert result.shifted_windows == 0


def test_intraday_fetch_excludes_old_events_not_shifts_them(tmp_path: Path) -> None:
    feasibility_path = tmp_path / "feasibility.csv"
    _write_csv(
        feasibility_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "data_ticker": "AAA",
                "event_timestamp_utc": "2026-05-01T15:00:00Z",
                "yfinance_intraday_eligible": True,
            },
            {
                "event_id": "2",
                "ticker": "BBB",
                "data_ticker": "BBB",
                "event_timestamp_utc": "2026-01-01T15:00:00Z",
                "yfinance_intraday_eligible": True,
            },
        ],
    )

    def fail_downloader(*args: object, **kwargs: object) -> pd.DataFrame:
        raise AssertionError("should not call yfinance for old excluded event")

    result = fetch_yfinance_intraday_market_data(
        feasibility_input_path=feasibility_path,
        output_path=tmp_path / "intraday.csv",
        summary_md_path=tmp_path / "summary.md",
        summary_csv_path=tmp_path / "summary.csv",
        confirm_yfinance_run=True,
        dry_run=True,
        downloader=fail_downloader,
    )

    assert result.dry_run
    assert result.eligible_events == 2
    assert result.planned_event_windows == 1
    assert result.events_excluded_outside_1m_limit == 1
    assert result.shifted_windows == 0


def test_intraday_event_study_aligns_after_hours_and_calculates_abnormal_return(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.csv"
    market_path = tmp_path / "intraday.csv"
    alias_path = tmp_path / "aliases.csv"
    _write_csv(
        clean_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "creator": "Creator A",
                "title": "After hours event",
                "published_at": "2026-05-01T21:00:00Z",
                "recommendation_type": "buy",
                "direction": "positive",
            }
        ],
    )
    _write_csv(alias_path, [])
    _write_csv(
        market_path,
        [
            {
                "event_id": "1",
                "original_ticker": "AAA",
                "data_ticker": "AAA",
                "datetime_utc": "2026-05-04T13:30:00Z",
                "open": "100",
                "high": "100",
                "low": "100",
                "close": "100",
                "adjusted_close": "100",
                "volume": "1000",
                "benchmark_ticker": "SPY",
                "benchmark_close": "200",
                "interval": "1m",
                "data_source": "yfinance_yahoo_intraday_prototype",
                "downloaded_at_utc": "2026-05-04T14:00:00Z",
            },
            {
                "event_id": "1",
                "original_ticker": "AAA",
                "data_ticker": "AAA",
                "datetime_utc": "2026-05-04T13:35:00Z",
                "open": "101",
                "high": "101",
                "low": "101",
                "close": "101",
                "adjusted_close": "101",
                "volume": "1100",
                "benchmark_ticker": "SPY",
                "benchmark_close": "200.5",
                "interval": "1m",
                "data_source": "yfinance_yahoo_intraday_prototype",
                "downloaded_at_utc": "2026-05-04T14:00:00Z",
            },
            {
                "event_id": "1",
                "original_ticker": "AAA",
                "data_ticker": "AAA",
                "datetime_utc": "2026-05-04T13:45:00Z",
                "open": "102",
                "high": "102",
                "low": "102",
                "close": "102",
                "adjusted_close": "102",
                "volume": "1200",
                "benchmark_ticker": "SPY",
                "benchmark_close": "201",
                "interval": "1m",
                "data_source": "yfinance_yahoo_intraday_prototype",
                "downloaded_at_utc": "2026-05-04T14:00:00Z",
            },
            {
                "event_id": "1",
                "original_ticker": "AAA",
                "data_ticker": "AAA",
                "datetime_utc": "2026-05-04T14:00:00Z",
                "open": "103",
                "high": "103",
                "low": "103",
                "close": "103",
                "adjusted_close": "103",
                "volume": "1300",
                "benchmark_ticker": "SPY",
                "benchmark_close": "201.5",
                "interval": "1m",
                "data_source": "yfinance_yahoo_intraday_prototype",
                "downloaded_at_utc": "2026-05-04T14:00:00Z",
            },
            {
                "event_id": "1",
                "original_ticker": "AAA",
                "data_ticker": "AAA",
                "datetime_utc": "2026-05-04T20:00:00Z",
                "open": "104",
                "high": "104",
                "low": "104",
                "close": "104",
                "adjusted_close": "104",
                "volume": "1500",
                "benchmark_ticker": "SPY",
                "benchmark_close": "202",
                "interval": "1m",
                "data_source": "yfinance_yahoo_intraday_prototype",
                "downloaded_at_utc": "2026-05-04T14:00:00Z",
            },
        ],
    )
    result = run_intraday_event_study(
        input_events_path=clean_path,
        input_intraday_market_data_path=market_path,
        ticker_aliases_path=alias_path,
        output_path=tmp_path / "results.csv",
        summary_md_path=tmp_path / "summary.md",
        by_creator_path=tmp_path / "by_creator.csv",
        by_ticker_path=tmp_path / "by_ticker.csv",
        methodology_note_path=tmp_path / "method.md",
    )
    output = pd.read_csv(result.output_path)

    assert result.events_processed == 1
    assert result.events_matched == 1
    assert output.loc[0, "event_timestamp_aligned_utc"] == "2026-05-04T13:30:00Z"
    # Stock 5m return=(101/100-1)=0.01; benchmark 5m return=(200.5/200-1)=0.0025; abnormal=0.0075
    assert float(output.loc[0, "abnormal_return_5m"]) == pytest.approx(0.0075, abs=1e-6)


def test_intraday_event_study_only_matches_fetched_event_ids(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.csv"
    market_path = tmp_path / "intraday.csv"
    alias_path = tmp_path / "aliases.csv"
    _write_csv(
        clean_path,
        [
            {
                "event_id": "1",
                "ticker": "AAA",
                "creator": "Creator A",
                "title": "Event 1",
                "published_at": "2026-05-01T15:00:00Z",
                "recommendation_type": "buy",
                "direction": "positive",
            },
            {
                "event_id": "2",
                "ticker": "AAA",
                "creator": "Creator A",
                "title": "Event 2 same ticker",
                "published_at": "2026-05-01T16:00:00Z",
                "recommendation_type": "buy",
                "direction": "positive",
            },
        ],
    )
    _write_csv(alias_path, [])
    # Only event_id=1 has market data; event_id=2 does not
    _write_csv(
        market_path,
        [
            {
                "event_id": "1",
                "original_ticker": "AAA",
                "data_ticker": "AAA",
                "datetime_utc": "2026-05-01T15:00:00Z",
                "open": "100",
                "high": "100",
                "low": "100",
                "close": "100",
                "adjusted_close": "100",
                "volume": "1000",
                "benchmark_ticker": "SPY",
                "benchmark_close": "200",
                "interval": "1m",
                "data_source": "yfinance_yahoo_intraday_prototype",
                "downloaded_at_utc": "2026-05-04T14:00:00Z",
            },
            {
                "event_id": "1",
                "original_ticker": "AAA",
                "data_ticker": "AAA",
                "datetime_utc": "2026-05-01T15:05:00Z",
                "open": "101",
                "high": "101",
                "low": "101",
                "close": "101",
                "adjusted_close": "101",
                "volume": "1100",
                "benchmark_ticker": "SPY",
                "benchmark_close": "200.5",
                "interval": "1m",
                "data_source": "yfinance_yahoo_intraday_prototype",
                "downloaded_at_utc": "2026-05-04T14:00:00Z",
            },
        ],
    )
    result = run_intraday_event_study(
        input_events_path=clean_path,
        input_intraday_market_data_path=market_path,
        ticker_aliases_path=alias_path,
        output_path=tmp_path / "results.csv",
        summary_md_path=tmp_path / "summary.md",
        by_creator_path=tmp_path / "by_creator.csv",
        by_ticker_path=tmp_path / "by_ticker.csv",
        methodology_note_path=tmp_path / "method.md",
    )
    output = pd.read_csv(result.output_path)

    assert result.events_processed == 2
    assert result.events_matched == 1
    assert result.missing_events == 1
    # Event 1 matched, Event 2 missing because no event_id=2 data
    matched_ids = output[~output["missing_intraday_data_flag"].astype(bool)]["event_id"].tolist()
    missing_ids = output[output["missing_intraday_data_flag"].astype(bool)]["event_id"].tolist()
    assert matched_ids == [1]
    assert missing_ids == [2]


def test_x_cost_plan_computes_estimates_and_makes_no_network_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed_path = tmp_path / "x_creator_candidates.csv"
    taxonomy_path = tmp_path / "creator_taxonomy_seed.csv"
    _write_csv(
        seed_path,
        [
            {
                "handle": "alpha",
                "display_name": "alpha",
                "category": "stock_picker",
                "priority": "high",
                "notes": "",
            },
            {
                "handle": "beta",
                "display_name": "beta",
                "category": "news_attention",
                "priority": "low",
                "notes": "",
            },
        ],
    )
    _write_csv(
        taxonomy_path,
        [
            {
                "handle": "alpha",
                "platform": "x",
                "initial_category": "stock_picker",
            }
        ],
    )

    def fail_post(*args: object, **kwargs: object) -> None:
        raise AssertionError("X/OpenAI network calls should not be made")

    def fail_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("Socket connections should not be opened")

    monkeypatch.setattr("requests.post", fail_post)
    monkeypatch.setattr(socket, "create_connection", fail_connection)

    result = build_x_extension_cost_plan(
        candidate_seed_path=seed_path,
        creator_taxonomy_seed_path=taxonomy_path,
        output_cost_plan_csv_path=tmp_path / "cost_plan.csv",
        output_cost_plan_md_path=tmp_path / "cost_plan.md",
        output_candidate_queries_csv_path=tmp_path / "queries.csv",
    )
    cost = pd.read_csv(result.cost_plan_csv_path)

    assert result.creator_count == 2
    assert int(cost[cost["handle"] == "alpha"].iloc[0]["estimated_post_reads"]) == 2000
    assert float(cost[cost["handle"] == "alpha"].iloc[0]["estimated_cost_usd"]) == pytest.approx(10.0)
