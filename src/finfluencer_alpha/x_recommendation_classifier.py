from __future__ import annotations

import re
from dataclasses import dataclass

CASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])\$([A-Za-z]{1,5})(?![A-Za-z0-9_])")
PLAIN_TICKER_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]{2,5})(?![A-Za-z0-9_])")

AMBIGUOUS_TICKERS = {
    "ALL",
    "ARE",
    "BE",
    "BIG",
    "BY",
    "CAN",
    "CASH",
    "FOR",
    "GOOD",
    "IT",
    "LIFE",
    "LOVE",
    "LOW",
    "NOW",
    "ON",
    "OPEN",
    "OUT",
    "REAL",
    "SO",
    "TRUE",
    "UP",
    "VERY",
    "WELL",
    "YOU",
}

COMPANY_TO_TICKER = {
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "amazon": "AMZN",
    "meta": "META",
    "facebook": "META",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amd": "AMD",
    "palantir": "PLTR",
    "coinbase": "COIN",
    "shopify": "SHOP",
    "block": "SQ",
    "paypal": "PYPL",
    "netflix": "NFLX",
    "gamestop": "GME",
    "amc": "AMC",
    "sofi": "SOFI",
    "microstrategy": "MSTR",
}

FINANCE_CONTEXT_WORDS = {
    "stock",
    "stocks",
    "shares",
    "calls",
    "puts",
    "buy",
    "sell",
    "hold",
    "long",
    "short",
    "bullish",
    "bearish",
    "earnings",
    "portfolio",
    "watchlist",
    "price target",
    "pt",
}


@dataclass(frozen=True)
class TickerMention:
    ticker: str
    cashtag: str
    mention_type: str
    confidence: float


@dataclass(frozen=True)
class XClassification:
    recommendation_type: str
    direction: str
    confidence: float
    evidence_text: str
    is_recommendation: bool


def normalize_text_hash_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def extract_x_ticker_mentions(text: str, allowed_tickers: set[str] | None = None) -> list[TickerMention]:
    allowed = {ticker.upper() for ticker in allowed_tickers} if allowed_tickers else None
    mentions: dict[str, TickerMention] = {}

    for match in CASHTAG_RE.finditer(text or ""):
        ticker = match.group(1).upper()
        if allowed is not None and ticker not in allowed:
            continue
        confidence = 0.65 if ticker in AMBIGUOUS_TICKERS else 0.95
        mentions[ticker] = TickerMention(ticker, f"${ticker}", "cashtag", confidence)

    lower = (text or "").lower()
    for company, ticker in COMPANY_TO_TICKER.items():
        if allowed is not None and ticker not in allowed:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(company)}(?![a-z0-9])", lower):
            mentions.setdefault(ticker, TickerMention(ticker, "", "company_name", 0.75))

    has_context = any(word in lower for word in FINANCE_CONTEXT_WORDS)
    if has_context:
        for match in PLAIN_TICKER_RE.finditer(text or ""):
            ticker = match.group(1).upper()
            if allowed is not None and ticker not in allowed:
                continue
            if ticker in AMBIGUOUS_TICKERS:
                mentions.setdefault(ticker, TickerMention(ticker, "", "ambiguous_plain", 0.35))
            elif ticker not in {"CEO", "CFO", "USA", "USD", "SEC", "ETF", "IPO"}:
                mentions.setdefault(ticker, TickerMention(ticker, "", "plain_context", 0.60))

    return sorted(mentions.values(), key=lambda mention: mention.ticker)


def classify_x_recommendation(text: str) -> XClassification:
    original = text or ""
    lower = original.lower()
    evidence = _evidence(original)

    if _looks_like_false_positive(lower):
        return XClassification("false_positive", "unclear", 0.20, evidence, False)

    if re.search(r"\b(i|we)\s+(own|have)\b", lower) or "my position" in lower:
        return XClassification("portfolio_disclosure", "neutral", 0.70, evidence, False)

    if re.search(r"\b(watching|watching for|watchlist|on watch|keeping an eye)\b", lower):
        return XClassification("watchlist", "neutral", 0.65, evidence, False)

    if re.search(r"\b(earnings|guidance|revenue|eps|reported|announces|news)\b", lower) and not re.search(
        r"\b(buy|buying|sell|selling|short|long|adding|avoid|price target|pt)\b", lower
    ):
        return XClassification("news_or_earnings_discussion", "neutral", 0.65, evidence, False)

    if re.search(r"\b(selling|sold|sell|trimmed|exit|exiting|avoid|shorting|short)\b", lower):
        return XClassification("explicit_sell_or_avoid", "bearish", 0.85, evidence, True)

    if re.search(r"\b(buying|bought|buy|adding|added|accumulating|going long|long)\b", lower):
        return XClassification("explicit_buy", "bullish", 0.85, evidence, True)

    if re.search(r"\b(hold|holding|continue to hold|not selling)\b", lower):
        return XClassification("hold", "neutral", 0.70, evidence, True)

    if re.search(r"\b(price target|pt)\b|\btarget\s*[:=]?\s*\$?\d", lower):
        direction = "bullish" if re.search(r"\b(upside|raise|higher|bullish)\b", lower) else "neutral"
        return XClassification("price_target", direction, 0.75, evidence, True)

    if re.search(r"\b(bullish|bearish|moon|squeeze|breakout|ripping|dumping)\b", lower):
        direction = "bearish" if "bearish" in lower or "dumping" in lower else "bullish"
        label = "meme_or_noise" if re.search(r"\b(meme|lol|moon|squeeze)\b", lower) else "sentiment_only"
        return XClassification(label, direction, 0.50, evidence, False)

    return XClassification("unclear", "unclear", 0.30, evidence, False)


def _looks_like_false_positive(lower: str) -> bool:
    return lower.startswith("rt @") or "giveaway" in lower or "airdrop" in lower


def _evidence(text: str, max_len: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."
