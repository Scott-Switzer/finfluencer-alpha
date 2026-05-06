# Data Dictionary

## creators

Candidate creator/channel records discovered through seed lists or API search. Seed accounts are labeled as candidate finance/market-attention accounts pending filtering, not as confirmed stock pickers.

## raw_x_posts

Normalized X post metadata collected through the official X API. Raw API JSON is retained in `raw_json` and as files under `data/raw/x/` for auditability.

## raw_youtube_videos

Normalized YouTube video metadata collected through the YouTube Data API. Raw API JSON is retained in `raw_json` and as files under `data/raw/youtube/`.

`current_view_count`, `current_like_count`, and `current_comment_count` are current public cumulative metrics at collection time. They are not historical engagement values as of the video publication timestamp. The older `view_count`, `like_count`, and `comment_count` columns are retained for backward compatibility and mirror the current values.

## ticker_mentions

Ticker or cashtag mentions extracted from post/video text. Cashtags receive higher confidence. Plain uppercase tickers are accepted only when they appear in a starter U.S. equity universe and have nearby stock-related context.

## recommendation_candidates

Rule-classified stock recommendation candidates. Rows require a ticker, bullish or bearish stance, actionability score of at least 2, and cannot be purely retrospective or news-only.

## creator_scores

Creator-level relevance scores based on item count, ticker density, actionable recommendation count, engagement, ticker diversity, and platform suitability. These scores are for sample selection, not evidence of investment skill.

## x_query_counts

Full-archive X counts collected before paid post retrieval. Rows store the stock-pick-filtered query, creator handle, date window, total count, period-level count JSON, and raw API response JSON.

## x_budget_usage

Budget ledger for paid X post reads. Reserved jobs count against the hard budget until actual reads are recorded.

## creator_taxonomy

Seeded creator categories: `stock_picker`, `news_attention`, `analytical_control`, `meme_retail`, `macro_commentary`, and `unknown`.

## creator_selection

Professor-readable research sample planning table. It combines taxonomy, X counts, observed ticker/actionable density, estimated read cost, selection score, and recommended action.

## x_enriched_events

Tracks selective reply and quote enrichment for high-confidence X recommendation events. Enrichment is capped per event and by the global enrichment budget.
