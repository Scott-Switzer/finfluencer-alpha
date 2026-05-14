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


def test_strict_cashtag_only_excludes_plain_and_company_mentions() -> None:
    mentions = extract_x_ticker_mentions(
        "Buying TSLA stock and Nvidia, adding $NVDA here",
        {"TSLA", "NVDA"},
        strict_cashtag_only=True,
    )

    assert [mention.ticker for mention in mentions] == ["NVDA"]
    assert mentions[0].mention_type == "cashtag"


def test_seed_universe_filter_limits_cashtags() -> None:
    mentions = extract_x_ticker_mentions(
        "Buying $TSLA and $XYZ into earnings",
        {"TSLA"},
        strict_cashtag_only=True,
    )

    assert [mention.ticker for mention in mentions] == ["TSLA"]


def test_plain_uppercase_false_positive_suppression() -> None:
    mentions = extract_x_ticker_mentions(
        "THE market is wild, BUY and HOLD are everywhere, AI headlines are moving stocks"
    )

    assert mentions == []
