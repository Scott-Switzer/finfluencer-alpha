from finfluencer_alpha.creator_selection import (
    CreatorResearchMetrics,
    plan_enrichment_events,
    score_creator_for_research_sample,
)


def test_stock_picker_with_signal_is_primary_include() -> None:
    result = score_creator_for_research_sample(
        CreatorResearchMetrics(
            platform="x",
            handle_or_channel="realMeetKevin",
            initial_category="stock_picker",
            count_stockpick_filtered=100,
            estimated_x_reads=100,
            ticker_density=0.40,
            actionable_density=0.30,
            engagement_available=True,
            cross_platform_present=True,
        )
    )
    assert result.recommended_action == "include_primary"
    assert result.creator_selection_score > 50


def test_news_heavy_account_excluded_from_primary_stock_picker_sample() -> None:
    result = score_creator_for_research_sample(
        CreatorResearchMetrics(
            platform="x",
            handle_or_channel="StockMKTNewz",
            initial_category="news_attention",
            count_stockpick_filtered=5_000,
            estimated_x_reads=5_000,
            ticker_density=0.80,
            actionable_density=0.20,
            engagement_available=True,
        )
    )
    assert result.recommended_action == "exclude_too_news_heavy"
    assert result.creator_selection_score <= 49


def test_enrichment_plan_caps_replies_and_quotes() -> None:
    candidates = [
        {"candidate_id": 1, "source_id": "post_1"},
        {"candidate_id": 2, "source_id": "post_2"},
    ]
    plans = plan_enrichment_events(
        candidates,
        max_events=100,
        max_replies=20,
        max_quotes=20,
        remaining_reads=1_000,
    )
    assert len(plans) == 2
    assert all(plan.reply_read_cap <= 20 for plan in plans)
    assert all(plan.quote_read_cap <= 20 for plan in plans)
