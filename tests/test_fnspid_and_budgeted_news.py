from __future__ import annotations

import pandas as pd
from scripts import build_v2_fnspid_news_layer as fn
from scripts import news_provider_utils as npu
from scripts.plan_budgeted_news_queries import DEFAULT_CAPS


def test_fnspid_window_counts_use_timedelta_not_strings() -> None:
    events = pd.DataFrame(
        [
            {"event_id": 1, "ticker": "ZZZ", "event_date": "2020-06-15"},
        ]
    )
    news = pd.DataFrame(
        [
            {"ticker": "ZZZ", "date": "2020-06-14", "title": "x"},
            {"ticker": "ZZZ", "date": "2020-06-16", "title": "y"},
        ]
    )
    panel, _, _, _ = fn.process_fnspid(events, news)
    assert len(panel) == 1
    row = panel.iloc[0]
    assert bool(row["fnspid_news_hit"])
    assert int(row["fnspid_news_count_pre_1d"]) >= 1
    assert int(row["fnspid_news_count_post_1d"]) >= 1


def test_fnspid_narrow_drops_out_of_range() -> None:
    ev = pd.DataFrame([{"event_id": 1, "ticker": "ZZZ", "event_date": "2020-06-15"}])
    news = pd.DataFrame(
        [
            {"ticker": "ZZZ", "date": "2018-01-01", "title": "old"},
            {"ticker": "ZZZ", "date": "2020-06-13", "title": "near"},
        ]
    )
    out = fn.narrow_fnspid_to_events(news, "ticker", "date", ev)
    assert len(out) == 1


def test_coverage_quality_monotone_in_external_success() -> None:
    s0 = npu.compute_news_coverage_quality_score(
        official_sec_earnings_checks_ok=False,
        external_success_count=0,
        fnspid_coverage_available=False,
        market_quiet_screen_passed=False,
    )
    s2 = npu.compute_news_coverage_quality_score(
        official_sec_earnings_checks_ok=False,
        external_success_count=2,
        fnspid_coverage_available=False,
        market_quiet_screen_passed=False,
    )
    assert s0 < s2


def test_quota_permission_detection() -> None:
    q, p = npu.provider_quota_or_permission("http_429")
    assert q and not p
    q2, p2 = npu.provider_quota_or_permission("http_403")
    assert p2


def test_budget_caps_defaults() -> None:
    assert DEFAULT_CAPS["marketaux"] == 50
    assert DEFAULT_CAPS["newsapi"] == 5
