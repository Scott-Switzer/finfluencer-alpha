# Event Study Readiness Check

Generated: 2026-05-14T16:50:00Z

## Readiness

| Analysis | Decision | Reason |
|---|---|---|
| X-only event studies | Blocked for final inference; diagnostic only with explicit override | Prior X coverage is same-day only: 2026-05-14 to 2026-05-14 across 1 calendar day. Strict `$CASHTAG` seed events cannot be rebuilt from accessible live data. |
| YouTube-only event studies | Can proceed | The accessible DB has 6,404 transcripts, 2,147 transcript recommendation events, and existing research expansion event-window outputs. |
| YouTube + X overlap tables | Diagnostic only | Overlap tables can describe same-day/current X attention only; they cannot support historical X overlap claims. |
| Market-control comparisons | Diagnostic only | Market-control posts are attention/control observations, not recommendation events. |

## Accessible File/Table State

| Item | Rows/status |
|---|---:|
| `x_posts` | not present in accessible DB |
| `raw_x_posts` | 0 |
| `x_post_ticker_mentions` | not present in accessible DB |
| `x_recommendation_events` | not present in accessible DB |
| legacy `ticker_mentions` where platform=`x` | 0 |
| legacy `recommendation_candidates` where platform=`x` | 0 |
| `raw_youtube_videos` | 11,922 |
| `youtube_transcripts` | 6,404 |
| `youtube_transcript_segments` | 1,178,472 |
| `transcript_recommendation_events` | 2,147 |
| `data/exports/research_expansion/all_clean_events.csv` | 2,078 |
| `data/exports/research_expansion/event_windows/event_window_returns.csv` | 25,622 |
| `data/exports/research_expansion/event_windows/event_window_summary.csv` | 14 |

## Required Tables And Columns

For final X studies, required tables/columns are:

- `x_posts`: `post_id`, `author_handle`, `text`, `created_at`, `source_type`, `source_query`, `like_count`, `repost_count`, `reply_count`, `quote_count`, `normalized_text_hash`.
- `x_post_ticker_mentions`: `post_id`, `ticker`, `cashtag`, `mention_type`, `confidence`.
- `x_recommendation_events`: `post_id`, `author_handle`, `ticker`, `event_datetime`, `event_date`, `recommendation_type`, `direction`, `confidence`, `source_method`.
- `apify_collection_runs`: `run_id`, `platform`, `actor_id`, `key_label`, `status`, `imported_items`, `duplicates`, `cost_usd`.

For YouTube-only studies, required tables/outputs are available through:

- `youtube_transcripts`, `youtube_transcript_segments`, `transcript_recommendation_events`;
- `data/exports/research_expansion/all_clean_events.csv`;
- `data/exports/research_expansion/event_windows/event_window_returns.csv`;
- market data exports used by the existing event-window pipeline.

## Missing Fields Or Schema Issues

- The populated X schema is missing from the accessible DB: `x_posts`, `x_post_ticker_mentions`, `x_recommendation_events`, and `apify_collection_runs` are not present.
- The legacy accessible X tables contain 0 X rows.
- Raw Apify item JSON is absent from `data/raw/apify/x`.
- Prior committed X evidence shows same-day-only parsed date coverage, which cannot support final historical event-study claims.
- Strict explicit-cashtag seed-filtered X event counts cannot be recomputed from the accessible data.

## Exact Commands To Run Next

Read-only verification on the actual populated RunPod host:

```bash
cd /workspace/FIN496CAPSTONE
source .venv/bin/activate
python - <<'PY'
import sqlite3
con = sqlite3.connect('data/finfluencer_alpha.db')
for table in ['x_posts', 'x_post_ticker_mentions', 'x_recommendation_events', 'apify_collection_runs']:
    exists = con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
    print(table, 'exists' if exists else 'missing')
    if exists:
        print('rows', con.execute(f'select count(*) from {table}').fetchone()[0])
if con.execute("select 1 from sqlite_master where type='table' and name='x_posts'").fetchone():
    print('x date range', con.execute("select min(created_at), max(created_at), count(distinct substr(created_at,1,10)) from x_posts").fetchone())
PY
ruff check .
pytest tests/
```

If and only if the populated RunPod DB proves historical X dates, rebuild strict X events with the committed guardrails before any X event-study output. Do not run broad collection or spend more Apify budget during this check.

## Conservative Interpretation Guardrails

- Same-day-only X coverage cannot support final historical event-study claims.
- Do not claim causality.
- Do not claim human validation unless a manual-labeling pass is documented.
- Do not claim tradable alpha.
- Treat YouTube and X classifier outputs as rule-based pseudo-labels.
- yfinance remains prototype-grade market data.
- Raw X data must not be committed or shared.
