from __future__ import annotations

import re
from dataclasses import dataclass

BULLISH_KEYWORDS = {
    "buy",
    "buying",
    "bought",
    "adding",
    "added",
    "long",
    "bullish",
    "undervalued",
    "cheap",
    "upside",
    "multibagger",
    "10x",
    "load up",
    "own it",
    "accumulation",
    "watchlist",
    "breakout",
    "calls",
    "price target",
    "pt",
}

BEARISH_KEYWORDS = {
    "short",
    "puts",
    "sell",
    "selling",
    "avoid",
    "overvalued",
    "downside",
    "bubble",
    "fraud",
    "collapse",
    "bearish",
}

RETROSPECTIVE_KEYWORDS = {
    "called it",
    "told you",
    "was right",
    "up since",
    "my pick",
    "from my last video",
    "i sent a course member signal",
    "i sent a signal",
    "we've been bullish since",
    "we have been bullish since",
    "since my last",
    "up 121% on the stock",
    "turned into multi",
    "turned into millions",
}

STRONG_RETROSPECTIVE_KEYWORDS = {
    "i sent a course member signal",
    "we have been bullish since",
    "we've been bullish since",
    "turned into multi-millions",
    "turned into millions of",
}

THIRD_PARTY_KEYWORDS = {
    "analysts are saying",
    "analysts said",
    "analysts expect",
    "analysts predict",
    "investors have suggested",
    "mutual funds",
    "according to the",
    "the information is reporting",
    "they reported",
    "they are reporting",
    "tom lee said",
    "tom lee just said",
    "dan ives said",
    "michael burry",
    "according to",
    "a report from",
}

AMBIGUOUS_REF_KEYWORDS = {
    "not even talking about that",
    "not even talking about",
    "if you had bought",
    "if you would have bought",
    "would have been",
    "if you had",
    "had you bought",
}

DISCLOSURE_KEYWORDS = {
    "i own",
    "my position",
    "holding",
    "portfolio",
    "not financial advice",
    "sponsored",
    "affiliate",
}

RISK_KEYWORDS = {"risk", "downside", "debt", "balance sheet"}

VALUATION_KEYWORDS = {
    "valuation",
    "dcf",
    "revenue",
    "earnings",
    "eps",
    "margin",
    "cash flow",
    "catalyst",
}

NEWS_ONLY_KEYWORDS = {
    "reports",
    "reported",
    "announces",
    "announced",
    "breaking",
    "according to",
    "files",
    "sec filing",
    "earnings released",
}

TARGET_KEYWORDS = {"target", "price target", "pt", "catalyst"}
EXTREME_HYPE_KEYWORDS = {"10x", "load up", "generational opportunity", "multibagger"}
SOFT_REC_KEYWORDS = {"watchlist", "undervalued", "overvalued", "breakout", "cheap", "upside"}
EXPLICIT_BULLISH = {"buy", "buying", "bought", "adding", "added", "long", "own it", "calls"}
EXPLICIT_BEARISH = {"short", "puts", "sell", "selling", "avoid"}


@dataclass(frozen=True)
class ClassificationResult:
    label: str
    stance: str
    actionability_score: int
    recommendation_type: str
    horizon: str
    disclosure_flag: bool
    risk_discussion_flag: bool
    valuation_discussion_flag: bool
    retrospective_flag: bool
    news_only_flag: bool
    third_party_flag: bool
    ambiguous_ref_flag: bool
    classifier_confidence: float


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(_keyword_matches(text, keyword) for keyword in keywords)


def _count_keywords(text: str, keywords: set[str]) -> int:
    return sum(1 for keyword in keywords if _keyword_matches(text, keyword))


def _keyword_matches(text: str, keyword: str) -> bool:
    escaped = re.escape(keyword).replace(r"\ ", r"\s+")
    if keyword.replace(" ", "").isalnum():
        pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    else:
        pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def infer_horizon(text: str) -> str:
    if any(term in text for term in ["today", "tomorrow", "this week", "short term", "swing"]):
        return "short_term"
    if any(term in text for term in ["this year", "2025", "12 month", "medium term"]):
        return "medium_term"
    if any(term in text for term in ["long term", "multi-year", "5 year", "decade"]):
        return "long_term"
    return "unspecified"


def actionability_score(text: str, stance: str) -> int:
    if stance not in {"bullish", "bearish"}:
        return 0

    explicit = EXPLICIT_BULLISH if stance == "bullish" else EXPLICIT_BEARISH
    score = 1
    if _contains_any(text, SOFT_REC_KEYWORDS):
        score = max(score, 2)
    if _contains_any(text, explicit):
        score = max(score, 3)
    if _contains_any(text, TARGET_KEYWORDS):
        score = max(score, 4)
    if _contains_any(text, EXTREME_HYPE_KEYWORDS):
        score = max(score, 5)
    return score


def classify_text(text: str | None) -> ClassificationResult:
    normalized = _normalize(text)
    bullish_count = _count_keywords(normalized, BULLISH_KEYWORDS)
    bearish_count = _count_keywords(normalized, BEARISH_KEYWORDS)
    retrospective = _contains_any(normalized, RETROSPECTIVE_KEYWORDS)
    disclosure = _contains_any(normalized, DISCLOSURE_KEYWORDS)
    risk = _contains_any(normalized, RISK_KEYWORDS)
    valuation = _contains_any(normalized, VALUATION_KEYWORDS)
    news_terms = _contains_any(normalized, NEWS_ONLY_KEYWORDS)
    third_party = _contains_any(normalized, THIRD_PARTY_KEYWORDS)
    ambiguous_ref = _contains_any(normalized, AMBIGUOUS_REF_KEYWORDS)

    if bullish_count > bearish_count:
        stance = "bullish"
        label = "bullish_recommendation"
    elif bearish_count > bullish_count:
        stance = "bearish"
        label = "bearish_recommendation"
    else:
        stance = "neutral"
        label = "neutral_mention"

    score = actionability_score(normalized, stance)
    news_only = bool(news_terms and stance == "neutral")
    strong_retrospective = _contains_any(normalized, STRONG_RETROSPECTIVE_KEYWORDS)

    if third_party and stance != "neutral":
        label = "third_party_attribution"
    elif ambiguous_ref and stance != "neutral":
        label = "ambiguous_reference"
    elif strong_retrospective:
        label = "retrospective_claim"
    elif retrospective and score < 3:
        label = "retrospective_claim"
    elif disclosure and stance == "neutral":
        label = "portfolio_disclosure"
    elif news_only:
        label = "news_only"
    elif stance == "neutral" and _contains_any(normalized, EXTREME_HYPE_KEYWORDS):
        label = "non_actionable_hype"

    confidence = 0.35
    if stance in {"bullish", "bearish"}:
        confidence += min((bullish_count + bearish_count) * 0.12, 0.35)
    if score >= 3:
        confidence += 0.15
    if risk or valuation:
        confidence += 0.05
    if retrospective and label == "retrospective_claim":
        confidence += 0.10
    confidence = min(confidence, 0.95)

    return ClassificationResult(
        label=label,
        stance=stance,
        actionability_score=score,
        recommendation_type=label,
        horizon=infer_horizon(normalized),
        disclosure_flag=disclosure,
        risk_discussion_flag=risk,
        valuation_discussion_flag=valuation,
        retrospective_flag=retrospective,
        news_only_flag=news_only,
        third_party_flag=third_party,
        ambiguous_ref_flag=ambiguous_ref,
        classifier_confidence=round(confidence, 3),
    )


def should_create_candidate(result: ClassificationResult, has_ticker: bool = True) -> bool:
    if not has_ticker:
        return False
    if result.stance not in {"bullish", "bearish"}:
        return False
    if result.actionability_score < 2:
        return False
    if result.label in {"retrospective_claim", "news_only"}:
        return False
    return True
