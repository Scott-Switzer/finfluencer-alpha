from finfluencer_alpha.creator_score import CreatorScoreInput, compute_relevance_score


def test_creator_relevance_score_increases_with_actionable_content() -> None:
    low = compute_relevance_score(
        CreatorScoreInput(
            platform="x",
            total_items=10,
            ticker_mentions=2,
            actionable_mentions=0,
            avg_engagement=100,
            ticker_diversity=1,
        )
    )
    high = compute_relevance_score(
        CreatorScoreInput(
            platform="x",
            total_items=25,
            ticker_mentions=20,
            actionable_mentions=10,
            avg_engagement=5000,
            ticker_diversity=8,
        )
    )
    assert high > low


def test_creator_relevance_score_is_bounded() -> None:
    score = compute_relevance_score(
        CreatorScoreInput(
            platform="youtube",
            total_items=10_000,
            ticker_mentions=10_000,
            actionable_mentions=10_000,
            avg_engagement=1_000_000_000,
            ticker_diversity=500,
        )
    )
    assert 0 <= score <= 100
