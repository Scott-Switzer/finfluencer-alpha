# Data Dictionary

## creators

Candidate creator/channel records discovered through seed lists or API search. Seed accounts are labeled as candidate finance/market-attention accounts pending filtering, not as confirmed stock pickers.

## raw_x_posts

Normalized X post metadata collected through the official X API. Raw API JSON is retained in `raw_json` and as files under `data/raw/x/` for auditability.

## raw_youtube_videos

Normalized YouTube video metadata collected through the YouTube Data API. Raw API JSON is retained in `raw_json` and as files under `data/raw/youtube/`.

## ticker_mentions

Ticker or cashtag mentions extracted from post/video text. Cashtags receive higher confidence. Plain uppercase tickers are accepted only when they appear in a starter U.S. equity universe and have nearby stock-related context.

## recommendation_candidates

Rule-classified stock recommendation candidates. Rows require a ticker, bullish or bearish stance, actionability score of at least 2, and cannot be purely retrospective or news-only.

## creator_scores

Creator-level relevance scores based on item count, ticker density, actionable recommendation count, engagement, ticker diversity, and platform suitability. These scores are for sample selection, not evidence of investment skill.
