from __future__ import annotations

import pandas as pd
from scripts import build_v2_alpha_vantage_news_layer as av


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": 1,
                "ticker": "NVDA",
                "company_name": "Nvidia",
                "event_date": "2024-01-15",
            }
        ]
    )


def test_alpha_vantage_unknown_is_not_clean_without_successful_query() -> None:
    plan = pd.DataFrame(
        [{"query_key": "q1", "ticker": "NVDA", "query_status": "rate_limited"}]
    )
    flags = av.map_events(_events(), pd.DataFrame(), plan)
    row = flags.iloc[0]
    assert bool(row["av_news_unknown_flag"])
    assert not bool(row["av_news_clean_flag"])
    assert not bool(row["av_news_confounded_flag"])


def test_alpha_vantage_confounded_overrides_clean() -> None:
    plan = pd.DataFrame([{"query_key": "q1", "ticker": "NVDA", "query_status": "ok"}])
    articles = pd.DataFrame(
        [
            {
                "query_key": "q1",
                "ticker": "NVDA",
                "article_key": f"a{i}",
                "time_published": "20240115T120000",
                "source_domain": "example.com",
                "title_truncated": "Nvidia earnings analyst update",
                "earnings_news_flag": True,
                "analyst_news_flag": True,
                "product_news_flag": False,
                "legal_regulatory_news_flag": False,
                "macro_sector_news_flag": False,
            }
            for i in range(3)
        ]
    )
    flags = av.map_events(_events(), articles, plan)
    row = flags.iloc[0]
    assert bool(row["av_news_confounded_flag"])
    assert not bool(row["av_news_clean_flag"])
    assert not bool(row["av_news_unknown_flag"])


def test_alpha_vantage_clean_requires_successful_query_and_no_major_news() -> None:
    plan = pd.DataFrame([{"query_key": "q1", "ticker": "NVDA", "query_status": "ok"}])
    articles = pd.DataFrame(
        [
            {
                "query_key": "q1",
                "ticker": "NVDA",
                "article_key": "a1",
                "time_published": "20231201T120000",
                "source_domain": "example.com",
                "title_truncated": "old metadata outside event window",
                "earnings_news_flag": False,
                "analyst_news_flag": False,
                "product_news_flag": False,
                "legal_regulatory_news_flag": False,
                "macro_sector_news_flag": False,
            }
        ]
    )
    flags = av.map_events(_events(), articles, plan)
    row = flags.iloc[0]
    assert bool(row["av_news_clean_flag"])
    assert not bool(row["av_news_confounded_flag"])
    assert not bool(row["av_news_unknown_flag"])
