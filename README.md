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

## $50 X Budget Strategy

The X full-archive path is budget-constrained by default. The repo assumes:

```text
X_COST_PER_POST_READ=0.005
X_MAX_BUDGET_USD=50
X_MAX_TOTAL_POST_READS=10000
```

At $0.005 per post resource read, the hard cap is 10,000 X post reads. Paid X post retrieval commands require `--confirm-paid-run`, print the estimated reads and cost before running, and are blocked by the budget guard unless `--override-budget` is explicitly passed.

The budget is split into planning buckets:

- `X_DISCOVERY_READ_BUDGET=1000`
- `X_MAIN_COLLECTION_READ_BUDGET=6000`
- `X_ENRICHMENT_READ_BUDGET=2000`
- `X_BUFFER_READ_BUDGET=1000`

Counts are run before retrieval with `/2/tweets/counts/all`. Counts estimate creator-level stock-pick-filtered volume without retrieving full post resources. The system then ranks creators and retrieves only stock-pick-filtered posts for selected high-value creators, not full timelines.

## Creator Selection

The project separates creators into:

- `stock_picker`
- `news_attention`
- `analytical_control`
- `meme_retail`
- `macro_commentary`
- `unknown`

Seed taxonomy lives in `data/seeds/creator_taxonomy_seed.csv`. News and attention accounts are useful controls, but they are excluded from the primary stock-picker sample. Analytical and macro accounts can be included as controls. Stock-picking creators must show enough stock-pick-filtered volume and expected actionable recommendation density before the system spends paid X reads.

Run the budgeted workflow:

```bash
python -m finfluencer_alpha count-x-creators --start-date 2020-01-01 --end-date 2026-05-06
python -m finfluencer_alpha select-creators --budget 50
python -m finfluencer_alpha collect-x-budgeted --start-date 2020-01-01 --end-date 2026-05-06 --budget 50 --confirm-paid-run
python -m finfluencer_alpha enrich-x-budgeted --budget 10 --confirm-paid-run
python -m finfluencer_alpha export-creator-selection-report
```

Replies and quotes are enriched only after recommendation classification. The enrichment planner sorts high-confidence X recommendation events first, caps replies at 20 and quotes at 20 per event, and stops at `MAX_X_ENRICHED_EVENTS` or the enrichment read budget.

YouTube remains the larger historical backbone because the YouTube Data API can retrieve public historical video metadata without the same per-post full-archive read budget. X is used more selectively to test the faster upstream attention layer.

Important limitation: current X and YouTube engagement fields are collection-time public metrics, not historical engagement at the event timestamp.

YouTube seed channels are loaded from the canonical file `data/seeds/youtube_seed_channels.csv`. Runtime collection, seed consistency tests, and taxonomy review should all agree with that file before broad collection.

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
X_COST_PER_POST_READ=0.005
X_MAX_BUDGET_USD=50
X_MAX_TOTAL_POST_READS=10000
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
python -m finfluencer_alpha collect-youtube-history-seeds --start-date 2025-01-01 --end-date 2026-05-06 --max-channels 1
python -m finfluencer_alpha collect-youtube-history-seeds --start-date 2024-01-01 --end-date 2026-05-06 --max-channels 3 --max-pages 1 --dry-run
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
- `data/raw/x/counts/*.json`
- `data/raw/youtube/*.json`
- `data/exports/x_creator_candidates.csv`
- `data/exports/youtube_creator_candidates.csv`
- `data/exports/recommendation_candidates.csv`
- `data/exports/creator_selection_report.csv`
- `data/exports/x_budget_plan.csv`
- `data/exports/x_counts_by_creator.csv`
- `data/exports/final_selected_creators.csv`

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

The YouTube history seed command stores cumulative public metrics in explicitly named `current_view_count`, `current_like_count`, and `current_comment_count` fields. These are current-at-collection metrics, not historical metrics from the video publication date.

For the pilot command below, quota is small when channel IDs are already resolved and larger when names must be searched:

```bash
python -m finfluencer_alpha collect-youtube-history-seeds --start-date 2024-01-01 --end-date 2026-05-06 --max-channels 3 --max-pages 1
```

With resolved channel IDs, expect about 3 `channels.list`, 3 `playlistItems.list`, up to 3 `videos.list`, and roughly 9 quota units. With unresolved names, add up to 3 `search.list` calls at 100 units each, for roughly 309 total units. Use `--dry-run` to print the estimate without calling the API.

The official captions endpoints are not a scalable public transcript source for third-party videos. `captions.list` returns caption-track metadata and costs 50 units. `captions.download` costs 200 units and requires authorization plus permission to edit the video. Public YouTube transcripts are therefore not assumed to be automatically available through the Data API key.

## Ticker Extraction and Classification

Ticker extraction uses:

- cashtag regex for explicit mentions such as `$NVDA`
- cautious plain uppercase extraction only when a ticker is in the starter U.S. equity universe and appears near stock-related words
- a false-positive denylist for terms such as `GDP`, `CEO`, `IPO`, `USD`, `EPS`, `AI`, `ETF`

Classification is rule-based for MVP transparency. No paid LLM dependency is required.

For YouTube, title and description matches are screening candidates. High-confidence recommendation events require transcript, X text, or manual evidence with explicit recommendation language. Comments are audience reaction data, not creator recommendation source data.

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
