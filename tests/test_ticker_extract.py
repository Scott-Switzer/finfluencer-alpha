from finfluencer_alpha.ticker_extract import extract_tickers


def test_extracts_cashtags() -> None:
    mentions = extract_tickers("I am watching $NVDA and $TSLA calls this week.")
    tickers = {mention.ticker for mention in mentions}
    assert {"NVDA", "TSLA"} <= tickers
    assert all(mention.cashtag_flag for mention in mentions)


def test_filters_false_positive_plain_terms() -> None:
    mentions = extract_tickers("The CEO discussed GDP, EPS, USD, AI, and SEC rules.")
    assert mentions == []


def test_extracts_plain_ticker_with_stock_context() -> None:
    mentions = extract_tickers("NVDA stock still has upside after earnings.")
    assert [mention.ticker for mention in mentions] == ["NVDA"]
    assert mentions[0].extraction_method == "starter_universe_context"
