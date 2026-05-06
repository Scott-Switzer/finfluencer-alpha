from finfluencer_alpha.classify import classify_text, should_create_candidate


def test_bullish_actionable_classification() -> None:
    result = classify_text("Buying $NVDA here. Bullish with a $140 price target.")
    assert result.label == "bullish_recommendation"
    assert result.stance == "bullish"
    assert result.actionability_score >= 4
    assert should_create_candidate(result)


def test_bearish_actionable_classification() -> None:
    result = classify_text("Avoid $TSLA. It is overvalued and has downside risk.")
    assert result.label == "bearish_recommendation"
    assert result.stance == "bearish"
    assert result.actionability_score >= 2
    assert result.risk_discussion_flag


def test_neutral_news_only_classification() -> None:
    result = classify_text("$AAPL reports earnings after the close according to filings.")
    assert result.label == "news_only"
    assert result.stance == "neutral"
    assert result.actionability_score == 0
    assert not should_create_candidate(result)
