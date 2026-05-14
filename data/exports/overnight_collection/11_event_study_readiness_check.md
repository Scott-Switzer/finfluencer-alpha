# Event Study Readiness Check

Generated: 2026-05-14T16:17:46Z

## Readiness
- X-only event studies can proceed: no for final inference from the current unfiltered X sample. A small diagnostic/pilot can proceed only after deriving ISO event dates and filtering to validated investable tickers.
- YouTube-only event studies can proceed: yes, using the corrected audited YouTube sample and benchmark-adjusted return files.
- YouTube + X overlap tables can proceed: only as diagnostics. Current X date coverage is one collection-day slice, so historical overlap windows would be incomplete and misleading for final claims.
- Market-control comparisons can proceed: only as same-sample attention diagnostics; market-control posts must not be presented as recommendations.

## Current File/Table State
- `x_posts`: 6,936 rows
- `x_post_ticker_mentions`: 5,605 rows
- `x_recommendation_events`: 1,462 rows
- Integrated inventory CSV: 2,024 rows; columns include source_event_id, source_type, ticker, event_date, creator, x_count_prior_30_8d, x_count_prior_7_1d, x_count_same_day, x_count_post_1_7d, x_count_post_8_30d, x_engagement_prior_30_8d, x_engagement_prior_7_1d...
- Event-window returns CSV: 29,268 rows; columns include sample_mode, event_id, video_id, creator, ticker, recommendation_type, direction, event_date, next_trading_day, horizon, end_trading_day, raw_stock_return...
- Event-window summary CSV: 42 rows; columns include horizon, benchmark_ticker, N, mean_abnormal_return, median_abnormal_return, win_rate

## Required Tables And Columns
- `x_posts`: `post_id`, `author_handle`, `text`, `created_at`, `source_type`, `source_query`, `like_count`, `repost_count`, `reply_count`, `quote_count`, `normalized_text_hash`
- `x_post_ticker_mentions`: `post_id`, `ticker`, `mention_type`, `confidence`
- `x_recommendation_events`: `post_id`, `author_handle`, `ticker`, `event_datetime`, `event_date`, `recommendation_type`, `direction`, `confidence`
- `apify_collection_runs`: `run_id`, `platform`, `actor_id`, `key_label`, `status`, `imported_items`, `duplicates`, `cost_usd`
- `data/exports/overnight_collection/06_integrated_event_inventory.csv`: `source_type`, `ticker`, `event_date`, `creator`, `attention_category`, and X attention-window counts.
- `data/exports/x_youtube_event_study/event_window_returns.csv`: `event_id`, `ticker`, `horizon`, raw returns, benchmark labels or benchmark-specific abnormal-return columns.

## Missing Fields Or Schema Issues
- Missing required DB columns: none
- X `event_date` is not ISO-normalized; derive a safe `event_date_iso` from `x_posts.created_at` before using X events in return windows.
- X parsed date coverage is 2026-05-14 to 2026-05-14 across 1 calendar day(s), not the intended multi-year 2020-2026 window.
- Ticker precision issue: only 46 of 1,462 X recommendation events match configured seed cashtags.
- Known reporting issue fixed in prior recovery: event-window returns may lack `benchmark_ticker`; summary code now infers benchmark labels from abnormal-return columns or defaults safely.

## Exact Commands To Run Next
Do not run collection commands yet. Use these commands for validation and read-only diagnostics from existing data:
```bash
cd /workspace/FIN496CAPSTONE
source .venv/bin/activate
python - <<'PY'
import sqlite3
from pathlib import Path
con = sqlite3.connect("data/finfluencer_alpha.db")
for table in ["x_posts", "x_post_ticker_mentions", "x_recommendation_events", "apify_collection_runs"]:
    print(table, con.execute(f"select count(*) from {table}").fetchone()[0])
print("date_min_max", con.execute("select min(created_at), max(created_at) from x_posts").fetchone())
PY
ruff check .
pytest tests/
```

Next code step before final X studies: add a research-only normalization/filter command that creates derived X event-study inputs with ISO dates and a validated ticker universe. Do not use the overnight runner for this step because it can collect data.

## Conservative Interpretation Guardrails
- Treat X and YouTube classifications as pseudo-labels unless manually validated.
- Separate creator recommendation events from broad attention/search events and market-control/news events.
- Treat the current X sample as a diagnostic collection, not the final historical X dataset.
- Do not claim causality.
- Do not claim human validation.
- Do not claim tradable alpha unless benchmark-adjusted, post-cost, robustness-tested evidence supports it.
- yfinance remains prototype-grade market data.
