# Methodology

## Collection

The MVP uses official APIs only:

- X API v2 recent search at `/2/tweets/search/recent` by default.
- X API v2 full archive at `/2/tweets/search/all` only when `X_SEARCH_MODE=all`.
- YouTube Data API `search.list`, `channels.list`, `playlistItems.list`, and `videos.list`.

The system skips unavailable API steps when keys are missing and logs warnings instead of failing the whole pipeline.

## Ticker Extraction

Cashtags are extracted with:

```text
(?<![A-Za-z0-9])\$[A-Z]{1,5}(?![A-Za-z])
```

Plain uppercase tickers are intentionally conservative. They must exist in the starter ticker universe and appear near stock-related terms. The starter universe can later be replaced by a Bloomberg, Nasdaq, Polygon, or CRSP-style ticker master.

## Classification

The MVP uses transparent rules instead of paid LLM classification. It assigns one of:

- bullish_recommendation
- bearish_recommendation
- neutral_mention
- retrospective_claim
- portfolio_disclosure
- non_actionable_hype
- news_only

Recommendation candidates are retained only when they contain a ticker, have bullish or bearish stance, score at least 2 for actionability, and are not purely retrospective or news-only.

## Future Bloomberg Integration

Bloomberg data should be joined after recommendation event construction. The expected later joins are ticker/date to returns, volume, market cap, beta, sector, liquidity controls, and benchmark returns. Raw Bloomberg exports must not be committed.
