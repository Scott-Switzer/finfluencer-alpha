from __future__ import annotations

from finfluencer_alpha.youtube_stock_pick_scoring import (
    score_creator_stock_picker_likelihood,
    score_video_stock_pick_likelihood,
)


def test_ticker_and_recommendation_title_scores_highest() -> None:
    best = score_video_stock_pick_likelihood(
        title="TSLA stock to buy now with price target",
        description="My top stocks to buy this year.",
        channel_title="Growth Stocks Daily",
        duration_seconds=900,
        creator_prior_stats={"prior_conversion_rate": 0.25, "prior_accepted_events": 15, "creator_type": "stock_picker"},
    )
    generic = score_video_stock_pick_likelihood(
        title="How to budget your monthly expenses",
        description="Beginner personal finance tips",
        channel_title="Money Basics",
        duration_seconds=900,
        creator_prior_stats={},
    )
    assert best > generic


def test_macro_only_title_ranks_lower() -> None:
    stock_pick = score_video_stock_pick_likelihood(
        title="Best stocks to buy now: NVDA, AAPL",
        description="Price targets and portfolio update",
        channel_title="Stock Picks",
        duration_seconds=1200,
        creator_prior_stats={},
    )
    macro = score_video_stock_pick_likelihood(
        title="Fed meeting macro outlook 2026",
        description="Economic update and inflation overview",
        channel_title="Macro Watch",
        duration_seconds=1200,
        creator_prior_stats={},
    )
    assert stock_pick > macro


def test_shorts_are_deprioritized_without_strong_signal() -> None:
    normal = score_video_stock_pick_likelihood(
        title="Top stocks to buy now",
        description="Detailed buy thesis and price targets",
        channel_title="Stock Picks",
        duration_seconds=600,
        creator_prior_stats={},
    )
    short = score_video_stock_pick_likelihood(
        title="Top stocks to buy now #shorts",
        description="quick thought",
        channel_title="Stock Picks",
        duration_seconds=45,
        creator_prior_stats={},
    )
    assert normal > short


def test_creator_scoring_prefers_stock_picker_profile() -> None:
    strong = score_creator_stock_picker_likelihood(
        "Dividend Stock Portfolio",
        "Stock picks and portfolio updates every week",
        {"prior_accepted_events": 12, "prior_conversion_rate": 0.3, "creator_type": "stock_picker"},
    )
    weak = score_creator_stock_picker_likelihood(
        "General News Channel",
        "Daily macro and world news recap",
        {"prior_accepted_events": 0, "prior_conversion_rate": 0.0, "creator_type": "news_commentary"},
    )
    assert strong > weak
