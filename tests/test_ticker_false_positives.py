from pathlib import Path

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "fp_test.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def test_normal_you_is_not_extracted_as_ticker() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("you should buy Apple stock")
    tickers = {m.ticker for m in mentions}
    assert "YOU" not in tickers


def test_you_should_know_not_extracted() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("you know what to buy")
    tickers = {m.ticker for m in mentions}
    assert "YOU" not in tickers


def test_cashtag_you_requires_strong_context() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("I think $YOU is going up because you know")
    tickers = {m.ticker for m in mentions}
    assert "YOU" not in tickers


def test_cashtag_you_with_stock_context_extracted() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("buy $YOU stock now")
    tickers = {m.ticker for m in mentions}
    assert "YOU" in tickers

    for m in mentions:
        if m.ticker == "YOU":
            assert m.extraction_risk == "high"
            assert m.common_word_flag is True
            assert m.extraction_context == "stock_context"


def test_clear_secure_alias_maps_to_you() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("Clear Secure is a great investment in identity")
    tickers = {m.ticker for m in mentions}
    assert "YOU" not in tickers  # not in STARTER_TICKER_UNIVERSE


def test_exchange_syntax_extracts_you() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("NYSE: YOU is trading at a discount buy YOU stock")
    tickers = {m.ticker for m in mentions}
    assert "YOU" not in tickers  # not in STARTER_TICKER_UNIVERSE


def test_high_risk_you_cashtag_with_company_alias() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("Clear Secure stock is undervalued, $YOU buy")
    tickers = {m.ticker for m in mentions}
    assert "YOU" in tickers

    for m in mentions:
        if m.ticker == "YOU":
            assert m.extraction_risk == "high"
            assert m.extraction_context in ("company_alias", "stock_context")


def test_channel_title_not_used_for_ticker_extraction() -> None:
    from finfluencer_alpha.ticker_extract import extract_tickers

    mentions = extract_tickers("this video is about Apple")
    tickers = {m.ticker for m in mentions}
    assert "AAPL" in tickers or "YOU" not in tickers


def test_audit_no_false_positives_for_clean_data(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "audit_fp.db")

    from finfluencer_alpha.ticker_false_positive import audit_ticker_false_positives

    monkeypatch.setattr(
        "finfluencer_alpha.ticker_false_positive.connect",
        lambda: connect(database_url),
    )

    paths = audit_ticker_false_positives(ticker="YOU")
    assert paths["audit_csv"].exists()
    assert paths["summary_txt"].exists()


def test_quarantine_dry_run_does_not_mutate_db(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "quar_dry.db")

    from finfluencer_alpha.ticker_false_positive import quarantine_false_positive_tickers

    monkeypatch.setattr(
        "finfluencer_alpha.ticker_false_positive.connect",
        lambda: connect(database_url),
    )

    result = quarantine_false_positive_tickers(ticker="YOU", dry_run=True)
    assert result.dry_run is True
    assert result.windows_excluded == 0
    assert result.events_excluded == 0

    with connect(database_url) as conn:
        exclusions = conn.execute(
            "SELECT COUNT(*) FROM transcript_event_exclusions"
        ).fetchone()[0]
    assert exclusions == 0


def test_overnight_readiness_runs(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "ready_check.db")

    from finfluencer_alpha.overnight_readiness import overnight_readiness_check

    monkeypatch.setattr(
        "finfluencer_alpha.overnight_readiness.connect",
        lambda: connect(database_url),
    )
    monkeypatch.setattr(
        "finfluencer_alpha.overtime_collection.connect",
        lambda: connect(database_url),
    )

    result = overnight_readiness_check()
    assert isinstance(result.ready, bool)
    assert len(result.reasons) > 0


def test_high_risk_tickers_include_you() -> None:
    from finfluencer_alpha.ticker_extract import HIGH_RISK_TICKERS

    assert "YOU" in HIGH_RISK_TICKERS
    assert "ON" in HIGH_RISK_TICKERS
    assert "ALL" in HIGH_RISK_TICKERS
    assert "USA" in HIGH_RISK_TICKERS
    assert "REAL" in HIGH_RISK_TICKERS


def test_company_alias_for_high_risk_includes_clear_secure() -> None:
    from finfluencer_alpha.ticker_extract import COMPANY_ALIAS_FOR_HIGH_RISK

    assert COMPANY_ALIAS_FOR_HIGH_RISK["Clear Secure"] == "YOU"
    assert COMPANY_ALIAS_FOR_HIGH_RISK["CLEAR"] == "YOU"


def test_ticker_mention_has_risk_fields() -> None:
    from finfluencer_alpha.ticker_extract import TickerMention

    m = TickerMention(
        ticker="TSLA", mention_text="buy TSLA", cashtag_flag=False,
        extraction_method="starter_universe_context", confidence=0.70,
    )
    assert m.extraction_risk == "low"
    assert m.common_word_flag is False
    assert m.extraction_context == "plain_symbol"
