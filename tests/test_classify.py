from pathlib import Path

from finfluencer_alpha.classify import classify_text, should_create_candidate
from finfluencer_alpha.cli import _source_rows_for_classification
from finfluencer_alpha.db import connect, init_db


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


def test_short_keywords_do_not_match_urls_or_marketing_boilerplate() -> None:
    result = classify_text("AMD. OWN IT. Join my group at https://example.com/1000xStocks")
    assert result.stance == "bullish"
    assert result.actionability_score == 3
    assert result.valuation_discussion_flag is False


def test_price_target_does_not_match_http_url() -> None:
    result = classify_text("AMD shareholder update https://example.com/1000xStocks")
    assert result.stance == "neutral"
    assert result.actionability_score == 0
    assert result.valuation_discussion_flag is False


def test_youtube_classification_uses_title_not_description(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'classification_source.db'}"
    init_db(database_url)

    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, published_at, title, description
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "video123",
                "channel123",
                "2026-01-01T00:00:00Z",
                "Neutral market update",
                "I am buying Nvidia stock",
            ),
        )
        conn.execute(
            """
            INSERT INTO ticker_mentions (
              platform, source_id, ticker, mention_text, cashtag_flag, extraction_method, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("youtube", "video123", "NVDA", "I am buying Nvidia stock", 0, "company_alias_context", 0.75),
        )
        rows = _source_rows_for_classification(conn)

    assert len(rows) == 1
    assert rows[0]["text"] == "Neutral market update"
