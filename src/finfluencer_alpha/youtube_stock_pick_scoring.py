from __future__ import annotations

from typing import Any

RECOMMENDATION_PHRASES = (
    "stock to buy",
    "stocks to buy",
    "best stocks",
    "top stocks",
    "buy now",
    "sell now",
    "undervalued stock",
    "undervalued stocks",
    "10x stock",
    "portfolio update",
    "my portfolio",
    "stock pick",
    "price target",
    "earnings analysis",
)

TICKER_COMPANY_TERMS = (
    "$", "tsla", "tesla", "nvda", "nvidia", "pltr", "palantir", "aapl", "apple",
    "amzn", "amazon", "msft", "microsoft", "goog", "googl", "google", "amd",
    "meta", "sofi", "coin", "coinbase", "ai stocks", "dividend stocks", "growth stocks",
    "small cap",
)

DEPRIORITIZE_PHRASES = (
    "market update",
    "fed meeting",
    "macro update",
    "economy update",
    "budgeting",
    "credit score",
    "debt payoff",
    "personal finance basics",
)


def _clean(text: str | None) -> str:
    return (text or "").strip().lower()


def _bool_num(flag: bool) -> float:
    return 1.0 if flag else 0.0


def _title_desc_text(title: str | None, description: str | None) -> str:
    return f"{_clean(title)} {_clean(description)}".strip()


def score_video_stock_pick_likelihood(
    title: str | None,
    description: str | None,
    channel_title: str | None,
    duration_seconds: int | None,
    creator_prior_stats: dict[str, Any] | None = None,
) -> float:
    text = _title_desc_text(title, description)
    score = 0.0
    creator_stats = creator_prior_stats or {}

    recommendation_hits = sum(1 for phrase in RECOMMENDATION_PHRASES if phrase in text)
    score += min(4, recommendation_hits) * 14.0

    ticker_hits = sum(1 for term in TICKER_COMPANY_TERMS if term in text)
    score += min(6, ticker_hits) * 8.0

    score -= sum(1 for phrase in DEPRIORITIZE_PHRASES if phrase in text) * 10.0

    channel = _clean(channel_title)
    if "stock" in channel or "invest" in channel or "portfolio" in channel:
        score += 8.0

    if duration_seconds is not None and duration_seconds > 0:
        if duration_seconds < 90:
            score -= 12.0
        elif duration_seconds > 7200:
            score -= 8.0
        elif 180 <= duration_seconds <= 3600:
            score += 6.0

    prior_conversion = float(creator_stats.get("prior_conversion_rate", 0.0) or 0.0)
    prior_events = int(creator_stats.get("prior_accepted_events", 0) or 0)
    score += min(25.0, prior_conversion * 100.0 * 0.35)
    score += min(15.0, prior_events * 0.6)

    # Penalize bare generic titles with weak stock intent.
    has_stock_intent = recommendation_hits > 0 or ticker_hits > 0
    score -= 8.0 * _bool_num(not has_stock_intent and len(text) < 80)
    return round(max(score, 0.0), 3)


def score_creator_stock_picker_likelihood(
    channel_title: str | None,
    channel_description: str | None,
    prior_stats: dict[str, Any] | None = None,
) -> float:
    stats = prior_stats or {}
    text = f"{_clean(channel_title)} {_clean(channel_description)}"
    score = 0.0

    if "stock" in text or "invest" in text or "portfolio" in text:
        score += 30.0
    if "news" in text and "stock" not in text:
        score -= 12.0
    if "personal finance" in text and "stock" not in text:
        score -= 8.0

    prior_events = int(stats.get("prior_accepted_events", 0) or 0)
    prior_conversion = float(stats.get("prior_conversion_rate", 0.0) or 0.0)
    creator_type = _clean(str(stats.get("creator_type") or ""))
    if creator_type == "stock_picker":
        score += 22.0
    score += min(30.0, prior_events * 1.2)
    score += min(18.0, prior_conversion * 100.0 * 0.25)
    return round(max(score, 0.0), 3)
