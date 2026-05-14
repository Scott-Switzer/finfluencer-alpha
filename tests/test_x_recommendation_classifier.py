from finfluencer_alpha.x_recommendation_classifier import (
    classify_x_recommendation,
    extract_x_ticker_mentions,
)


def test_cashtag_extraction() -> None:
    mentions = extract_x_ticker_mentions("Buying more $PLTR and watching $NVDA")
    assert [mention.ticker for mention in mentions] == ["NVDA", "PLTR"]
    assert all(mention.mention_type == "cashtag" for mention in mentions)


def test_buy_sell_hold_and_price_target_rules() -> None:
    assert classify_x_recommendation("Buying more $PLTR here").recommendation_type == "explicit_buy"
    assert classify_x_recommendation("Selling $COIN into this move").direction == "bearish"
    assert classify_x_recommendation("I will hold $MSFT").recommendation_type == "hold"
    assert classify_x_recommendation("$NVDA PT $250 after earnings").recommendation_type == "price_target"


def test_portfolio_disclosure_not_treated_as_buy() -> None:
    result = classify_x_recommendation("I own $TSLA in my long term portfolio")
    assert result.recommendation_type == "portfolio_disclosure"
    assert not result.is_recommendation


def test_news_only_not_treated_as_recommendation() -> None:
    result = classify_x_recommendation("$AAPL earnings today after the close")
    assert result.recommendation_type == "news_or_earnings_discussion"
    assert not result.is_recommendation


def test_ambiguous_ticker_handling() -> None:
    mentions = extract_x_ticker_mentions("LOW shares are on my watchlist", {"LOW"})
    assert mentions[0].mention_type == "ambiguous_plain"
    assert mentions[0].confidence < 0.5


def test_duplicate_mention_prevention() -> None:
    mentions = extract_x_ticker_mentions("$TSLA Tesla TSLA stock")
    assert [mention.ticker for mention in mentions] == ["TSLA"]
