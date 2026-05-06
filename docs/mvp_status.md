# MVP Status

Last verified: 2026-05-06

## 1. What Works

- `python3 -m ruff check .` passes.
- `python3 -m pytest` passes with 8 tests.
- `python3 -m finfluencer_alpha run-mvp` initializes SQLite, creates tables, runs downstream processing, scores creators, and exports CSVs.
- Missing API keys are handled gracefully. The pipeline prints which keys are missing, skips X and YouTube collection, and still completes.
- `python3 -m finfluencer_alpha show-config` masks API keys and reports only whether each key is present.
- Raw-data directories, generated exports, SQLite databases, and secrets are ignored by git.
- The CLI no longer imports API collector modules unless API-backed commands actually need them, so missing-key runs do not emit `requests` dependency warnings from the local global Python environment.

## 2. What Does Not Work Yet

- Live X and YouTube collection was not verified in this local run because no API keys were available. `show-config` reported `"x_bearer_token": false` and `"youtube_api_key": false`.
- X full-archive search is implemented as an optional mode but remains unverified. It requires elevated X API access.
- Recommendation classification is rule-based and needs manual validation before a final research sample is used.
- The ticker universe is a starter set of common U.S. equities, not a complete ticker master.
- There is no event-study or abnormal-return module yet.
- There is no Bloomberg import/join layer yet.

## 3. API Limitations

- X recent search uses `/2/tweets/search/recent`, which supports forward collection but not long historical reconstruction.
- X full archive uses `/2/tweets/search/all` only when `X_SEARCH_MODE=all`; access depends on the X API product tier.
- YouTube historical metadata collection is feasible through the YouTube Data API, but `search.list` can consume quota quickly.
- YouTube engagement metrics are platform-level metadata, not a full impression or viewer-level dataset.
- Both platforms can return incomplete or unavailable metrics depending on endpoint access, privacy, deleted content, quota, and account/video state.

## 4. Sample Output Files Generated

The missing-key smoke run generated these ignored local files:

- `data/finfluencer_alpha.db`
- `data/interim/missing_key_smoke.db`
- `data/exports/x_creator_candidates.csv`
- `data/exports/youtube_creator_candidates.csv`
- `data/exports/recommendation_candidates.csv`

Because no API keys were available, each export CSV currently contains only headers.

## 5. Next Steps for Bloomberg Market-Data Integration

- Build an event table from `recommendation_candidates` with `ticker`, `event_time`, `platform`, `creator_handle`, `stance`, and `actionability_score`.
- Export the distinct ticker/date event list for Bloomberg lookup.
- Pull or export Bloomberg fields for adjusted price, volume, shares outstanding or market cap, beta, sector, industry, liquidity controls, benchmark returns, and risk-free rate where needed.
- Store Bloomberg-derived clean data in ignored local files under `data/interim/` or `data/processed/`; do not commit raw Bloomberg files.
- Add a join module that maps recommendation event windows to return and volume windows.
- Add abnormal return, abnormal volume, prior momentum, and cross-platform timing features.
- Add tests using small synthetic market-data fixtures rather than licensed Bloomberg data.

## 6. Exact Commands to Run Next

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add available API keys:

```bash
X_BEARER_TOKEN=your_x_bearer_token
X_SEARCH_MODE=recent
YOUTUBE_API_KEY=your_youtube_api_key
DATABASE_URL=sqlite:///data/finfluencer_alpha.db
```

Run a small live smoke test:

```bash
python -m finfluencer_alpha show-config
python -m finfluencer_alpha run-mvp --x-max-pages 1 --youtube-max-results 5 --youtube-max-pages 1
```

Run a fuller MVP collection:

```bash
python -m finfluencer_alpha run-mvp --x-max-pages 2 --youtube-max-results 25 --youtube-max-pages 2
```

Review outputs:

```bash
python -m finfluencer_alpha export
open data/exports
```

Verify code after local edits:

```bash
python -m ruff check .
python -m pytest
```
