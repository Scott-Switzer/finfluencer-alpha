from __future__ import annotations

import re
from dataclasses import dataclass

CASETAG_RE = re.compile(r"(?<![A-Za-z0-9])\$[A-Z]{1,5}(?![A-Za-z])")
PLAIN_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
EXCHANGE_TICKER_RE = re.compile(
    r"(NYSE|NASDAQ|NYSEARCA|NYSEAMERICAN|NYSEarca|NYSEAmerican)\s*:\s*\b[A-Z]{1,5}\b",
    re.IGNORECASE,
)

HIGH_RISK_TICKERS = frozenset({
    "YOU",
    "ON",
    "ALL",
    "ARE",
    "CAN",
    "FOR",
    "IT",
    "NOW",
    "OUT",
    "SO",
    "USA",
    "LOVE",
    "GOOD",
    "BIG",
    "LIFE",
    "REAL",
    "OPEN",
})

COMPANY_ALIAS_FOR_HIGH_RISK = {
    "Clear Secure": "YOU",
    "CLEAR": "YOU",
    "Clear Secure Inc": "YOU",
}

COMPANY_ALIAS_TO_TICKER = {
    "Tesla": "TSLA",
    "Nvidia": "NVDA",
    "NVIDIA": "NVDA",
    "Apple": "AAPL",
    "Amazon": "AMZN",
    "Google": "GOOGL",
    "Alphabet": "GOOGL",
    "Meta": "META",
    "Facebook": "META",
    "Palantir": "PLTR",
    "SoFi": "SOFI",
    "Microsoft": "MSFT",
    "Coinbase": "COIN",
    "Robinhood": "HOOD",
    "Uber": "UBER",
    "Netflix": "NFLX",
    "Disney": "DIS",
    "PayPal": "PYPL",
    "Shopify": "SHOP",
    "Roku": "ROKU",
    "Super Micro": "SMCI",
    "Supermicro": "SMCI",
    "MicroStrategy": "MSTR",
}
COMPANY_ALIAS_RE = re.compile(
    r"(?<![A-Za-z0-9])("
    + "|".join(re.escape(alias) for alias in sorted(COMPANY_ALIAS_TO_TICKER, key=len, reverse=True))
    + r")(?![A-Za-z0-9])"
)

DENYLIST = {
    "CASH",
    "GDP",
    "CEO",
    "CFO",
    "IPO",
    "USA",
    "USD",
    "EPS",
    "PE",
    "AI",
    "ATH",
    "FOMO",
    "YOLO",
    "SEC",
    "ETF",
}

STARTER_TICKER_UNIVERSE = {
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "META",
    "GOOGL",
    "GOOG",
    "AMD",
    "NFLX",
    "PLTR",
    "SOFI",
    "RIVN",
    "LCID",
    "GME",
    "AMC",
    "HOOD",
    "COIN",
    "MSTR",
    "SMCI",
    "BABA",
    "NIO",
    "DIS",
    "PYPL",
    "SQ",
    "SHOP",
    "CRM",
    "AVGO",
    "COST",
    "WMT",
    "TGT",
}

STOCK_CONTEXT_WORDS = {
    "stock",
    "stocks",
    "share",
    "shares",
    "equity",
    "buy",
    "buying",
    "bought",
    "sell",
    "selling",
    "avoid",
    "short",
    "long",
    "bullish",
    "bearish",
    "undervalued",
    "overvalued",
    "upside",
    "downside",
    "watchlist",
    "breakout",
    "calls",
    "puts",
    "target",
    "pt",
    "earnings",
    "revenue",
    "valuation",
    "portfolio",
    "position",
    "holding",
    "load",
    "accumulation",
}


@dataclass(frozen=True)
class TickerMention:
    ticker: str
    mention_text: str
    cashtag_flag: bool
    extraction_method: str
    confidence: float
    extraction_risk: str = "low"
    common_word_flag: bool = False
    extraction_context: str = "plain_symbol"


def _context_window(text: str, start: int, end: int, chars: int = 80) -> str:
    return text[max(0, start - chars) : min(len(text), end + chars)]


def _has_stock_context(text: str, start: int, end: int) -> bool:
    window = _context_window(text, start, end).lower()
    return any(keyword in window for keyword in STOCK_CONTEXT_WORDS)


def _is_valid_denylist_context(ticker: str, text: str, start: int, end: int, cashtag: bool) -> bool:
    if ticker not in DENYLIST:
        return True
    if ticker in STARTER_TICKER_UNIVERSE:
        return True
    if cashtag and _has_stock_context(text, start, end):
        return True
    return False


def _high_risk_context(text: str, ticker: str, match_start: int, match_end: int) -> tuple[bool, str]:
    window = text[max(0, match_start - 80): min(len(text), match_end + 80)]
    window_lower = window.lower()
    ticker_lower = ticker.lower()

    exchange_match = EXCHANGE_TICKER_RE.search(window[:match_start + 80])
    if exchange_match:
        exchange_ticker = exchange_match.group(0).split(":")[-1].strip().upper()
        if exchange_ticker == ticker:
            return True, "exchange_prefix"

    for alias, mapped_ticker in COMPANY_ALIAS_FOR_HIGH_RISK.items():
        if alias.lower() in window_lower and mapped_ticker == ticker:
            return True, "company_alias"

    if _has_stock_context(text, match_start, match_end):
        strong_phrases = [
            f"{ticker_lower} stock", f"{ticker_lower} shares",
            f"{ticker_lower} earnings", f"{ticker_lower} revenue",
            f"{ticker_lower} valuation", f"long {ticker_lower}",
            f"short {ticker_lower}", f"buy {ticker_lower}",
            f"sell {ticker_lower}", f"{ticker_lower} price target",
        ]
        if any(phrase in window_lower for phrase in strong_phrases):
            return True, "stock_context"

    common_phrases = [
        f"{ticker_lower} should", f"{ticker_lower} know", f"{ticker_lower} can",
        f"if {ticker_lower}", f"when {ticker_lower}", f"what {ticker_lower}",
        f"how {ticker_lower}", f"why {ticker_lower}", f"that {ticker_lower}",
        f"and {ticker_lower}", f"for {ticker_lower}", f"with {ticker_lower}",
        f"to {ticker_lower}", f"of {ticker_lower}", f"in {ticker_lower}",
        f"do {ticker_lower}", f"did {ticker_lower}", f"are {ticker_lower}",
        f"thank {ticker_lower}", f"love {ticker_lower}",
    ]
    if any(phrase.split()[-1] == ticker_lower and phrase in window_lower for phrase in common_phrases):
        return False, "common_word_context"

    return False, "no_strong_context"


def extract_tickers(text: str | None) -> list[TickerMention]:
    if not text:
        return []

    mentions: list[TickerMention] = []
    seen: set[tuple[str, bool, str]] = set()

    for match in CASETAG_RE.finditer(text):
        ticker = match.group(0).replace("$", "").upper()
        if not _is_valid_denylist_context(ticker, text, match.start(), match.end(), cashtag=True):
            continue
        mention_text = _context_window(text, match.start(), match.end())
        key = (ticker, True, mention_text)
        if key in seen:
            continue
        seen.add(key)
        is_high_risk = ticker in HIGH_RISK_TICKERS
        if is_high_risk:
            passed, context = _high_risk_context(text, ticker, match.start(), match.end())
            if not passed:
                continue
            extraction_method = "cashtag_regex_high_risk"
        else:
            extraction_method = "cashtag_regex"
            context = "cashtag"
        mentions.append(
            TickerMention(
                ticker=ticker,
                mention_text=mention_text,
                cashtag_flag=True,
                extraction_method=extraction_method,
                confidence=0.95 if ticker in STARTER_TICKER_UNIVERSE else 0.85,
                extraction_risk="high" if is_high_risk else "low",
                common_word_flag=is_high_risk,
                extraction_context=context,
            )
        )

    for match in PLAIN_TICKER_RE.finditer(text):
        if match.start() > 0 and text[match.start() - 1] == "$":
            continue
        ticker = match.group(0).upper()
        if ticker not in STARTER_TICKER_UNIVERSE:
            continue
        if not _has_stock_context(text, match.start(), match.end()):
            continue
        if not _is_valid_denylist_context(ticker, text, match.start(), match.end(), cashtag=False):
            continue
        mention_text = _context_window(text, match.start(), match.end())
        key = (ticker, False, mention_text)
        if key in seen:
            continue
        seen.add(key)
        is_high_risk = ticker in HIGH_RISK_TICKERS
        mentions.append(
            TickerMention(
                ticker=ticker,
                mention_text=mention_text,
                cashtag_flag=False,
                extraction_method="starter_universe_context",
                confidence=0.70,
                extraction_risk="high" if is_high_risk else "low",
                common_word_flag=is_high_risk,
                extraction_context="stock_context" if is_high_risk else "plain_symbol",
            )
        )

    for match in COMPANY_ALIAS_RE.finditer(text):
        if not _has_stock_context(text, match.start(), match.end()):
            continue
        ticker = COMPANY_ALIAS_TO_TICKER[match.group(0)]
        mention_text = _context_window(text, match.start(), match.end())
        key = (ticker, False, mention_text)
        if key in seen:
            continue
        seen.add(key)
        mentions.append(
            TickerMention(
                ticker=ticker,
                mention_text=mention_text,
                cashtag_flag=False,
                extraction_method="company_alias_context",
                confidence=0.75,
            )
        )

    return mentions


def ticker_density(text: str | None) -> float:
    if not text:
        return 0.0
    words = max(len(re.findall(r"\w+", text)), 1)
    return len(extract_tickers(text)) / words
