# finfluencer-alpha

MVP research pipeline for:

> Finfluencer Alpha or Attention Spillover? A Cross-Platform Study of X and YouTube Stock Recommendations

Core question: do finfluencer stock recommendations on X and YouTube generate abnormal risk-adjusted returns for retail investors, or do they mostly amplify attention toward stocks that were already moving?

The project is designed for a FIN 496 capstone workflow. It discovers finance creators, collects posts/videos through official APIs, extracts tickers, classifies actionable recommendation candidates, scores creators for sample selection, and exports professor-review CSVs from a local SQLite database.

## Architecture

```text
Official APIs
  X API v2 recent/full-archive search
  YouTube Data API search/channels/playlists/videos
        |
        v
Raw JSON audit files in data/raw/
        |
        v
SQLite normalized tables
        |
        v
Ticker extraction -> rule classification -> creator scoring
        |
        v
CSV exports in data/exports/
```

No X website HTML scraping is used.

## Setup

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```bash
X_BEARER_TOKEN=
X_SEARCH_MODE=recent
YOUTUBE_API_KEY=
DATABASE_URL=sqlite:///data/finfluencer_alpha.db
```

You can also run directly from the repo root:

```bash
python -m finfluencer_alpha run-mvp
```

If API keys are missing, the pipeline initializes the database, skips API collection, and still creates empty export CSVs.

## CLI

```bash
python -m finfluencer_alpha init-db
python -m finfluencer_alpha discover-x --max-pages 2
python -m finfluencer_alpha collect-x-seeds --days-back 7 --max-pages 2
python -m finfluencer_alpha discover-youtube --max-results 25
python -m finfluencer_alpha collect-youtube-seeds --max-pages 2
python -m finfluencer_alpha extract-tickers
python -m finfluencer_alpha classify
python -m finfluencer_alpha score-creators
python -m finfluencer_alpha export
python -m finfluencer_alpha run-mvp
```

## Expected Outputs

The MVP writes:

- `data/finfluencer_alpha.db`
- `data/raw/x/*.json`
- `data/raw/youtube/*.json`
- `data/exports/x_creator_candidates.csv`
- `data/exports/youtube_creator_candidates.csv`
- `data/exports/recommendation_candidates.csv`

The `data/raw/`, `data/interim/`, `data/processed/`, `data/exports/`, database files, and `.env` are ignored by git.

## Database Tables

- `creators`
- `raw_x_posts`
- `raw_youtube_videos`
- `ticker_mentions`
- `recommendation_candidates`
- `creator_scores`

See `docs/data_dictionary.md` for field-level interpretation.

## X API Notes

By default, `X_SEARCH_MODE=recent` uses:

```text
/2/tweets/search/recent
```

If `X_SEARCH_MODE=all`, the code switches to:

```text
/2/tweets/search/all
```

Full archive search requires elevated X API access. If the token cannot use full archive, the system warns and continues. This MVP is therefore strongest for forward collection unless full-archive access is available.

## YouTube API Notes

The YouTube Data API supports historical metadata collection for public videos, but quota limits can be binding. `search.list` is relatively expensive. For larger research runs, resolve seed channels once, store channel IDs, then collect uploads through `playlistItems.list` and `videos.list`.

## Ticker Extraction and Classification

Ticker extraction uses:

- cashtag regex for explicit mentions such as `$NVDA`
- cautious plain uppercase extraction only when a ticker is in the starter U.S. equity universe and appears near stock-related words
- a false-positive denylist for terms such as `GDP`, `CEO`, `IPO`, `USD`, `EPS`, `AI`, `ETF`

Classification is rule-based for MVP transparency. No paid LLM dependency is required.

Recommendation candidate labels:

- `bullish_recommendation`
- `bearish_recommendation`
- `neutral_mention`
- `retrospective_claim`
- `portfolio_disclosure`
- `non_actionable_hype`
- `news_only`

Only ticker-bearing bullish/bearish items with actionability score at least 2 become recommendation candidates.

## Bloomberg Role

Bloomberg Terminal data should enter after event construction. The later event-study layer can join recommendation candidates to price, volume, beta, sector, market cap, liquidity, benchmark returns, and prior momentum. Do not commit Bloomberg exports or any licensed raw market data.

## Data Limitations

This MVP produces a research dataset, not final causal evidence. Key limitations:

- X recent search is forward-looking and cannot reconstruct long history without full archive access.
- YouTube metadata gives publish time and engagement, but not every view/impression path.
- Rule classification needs manual validation before final sample construction.
- Creator scores identify relevant candidates; they do not measure investment skill.
- Abnormal returns require a later market-data/event-study module.

## Tests and Linting

```bash
pytest
ruff check .
```

## Next Steps

1. Run the MVP with API keys and inspect CSV exports.
2. Manually validate recommendation candidates and creator categories.
3. Add a resolved YouTube channel ID seed file after initial discovery.
4. Replace the starter ticker universe with a full ticker master.
5. Add Bloomberg event-study joins and abnormal return calculations.
