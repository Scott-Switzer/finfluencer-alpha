from __future__ import annotations

import pandas as pd
from scripts import news_provider_utils as npu


def test_event_window_counts_split_pre_and_post() -> None:
    event_date = npu.parse_date("2024-06-10")
    assert event_date is not None
    article_dates = [
        npu.parse_date("2024-06-09"),
        npu.parse_date("2024-06-10"),
        npu.parse_date("2024-06-13"),
        npu.parse_date("2024-06-18"),
    ]
    pre, post = npu.event_window_counts([d for d in article_dates if d is not None], event_date, 3)
    assert pre == 1
    assert post == 2


def test_relevant_item_uses_ticker_or_company_terms() -> None:
    item = {"title": "Acme Semiconductor reports quarterly earnings"}
    assert npu.relevant_item(item, "ACME", "Acme Semiconductor Inc.")
    assert not npu.relevant_item({"title": "Broad market roundup"}, "ACME", "Acme Semiconductor Inc.")


def test_compact_provider_result_keeps_failed_check_unknown() -> None:
    event = pd.Series({"event_id": 1, "ticker": "ACME", "company_name": "Acme Semiconductor", "event_date": "2024-06-10"})
    row = npu.compact_provider_result("provider_x", event, "rate_limited", [])
    assert row["provider_success"] is False
    assert row["provider_hit"] is False
    assert row["pre_3d_count"] == 0
    assert row["post_3d_count"] == 0


def test_compact_provider_result_flags_material_relevant_news() -> None:
    event = pd.Series({"event_id": 1, "ticker": "ACME", "company_name": "Acme Semiconductor", "event_date": "2024-06-10"})
    items = [{"title": "ACME raises guidance after earnings", "published_at": "2024-06-11"}]
    row = npu.compact_provider_result("provider_x", event, "ok", items)
    assert row["provider_success"] is True
    assert row["provider_hit"] is True
    assert row["provider_material_hit"] is True
    assert row["post_1d_count"] == 1
