from __future__ import annotations

import re
from dataclasses import dataclass

CASETAG_RE = re.compile(r"(?<![A-Za-z0-9])\$[A-Z]{1,5}(?![A-Za-z])")
PLAIN_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")

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
        mentions.append(
            TickerMention(
                ticker=ticker,
                mention_text=mention_text,
                cashtag_flag=True,
                extraction_method="cashtag_regex",
                confidence=0.95 if ticker in STARTER_TICKER_UNIVERSE else 0.85,
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
        mentions.append(
            TickerMention(
                ticker=ticker,
                mention_text=mention_text,
                cashtag_flag=False,
                extraction_method="starter_universe_context",
                confidence=0.70,
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
