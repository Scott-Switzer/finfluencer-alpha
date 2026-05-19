# News layer status

## Alpha Vantage (NEWS_SENTIMENT)

- Stores **compact metadata only** (counts, truncated titles, flags). No raw article bodies or API keys in exports.
- **Coverage:** partial (~4 tickers under free-tier daily limits); ticker-chunk mode with resume.
- **Expanded panel counts:** 98 clean / 586 confounded / 1,657 unknown (of 2,341 events).

### Critical rule

**Unknown coverage is never treated as clean.**

Events without a successful provider query remain **unknown**, not “no news.”

## GDELT

- **Diagnostic only.** Retry success rate ~**28%** — below threshold for headline robustness claims.
- Do **not** cite GDELT-clean samples as confirmatory.

## Extreme-event news audit

- Module: `scripts/build_v2_extreme_event_news_audit.py`
- Output: `data/exports/final_paper_package_v2_expanded/news_extreme_event_audit/`
- Scope: **75** unique events selected from the top/bottom 25 1D and 5D SPY-adjusted abnormal-return events after event-id deduplication.
- Primary conservative labels: **56** official-confounded, **15** media-confounded, **2** Bloomberg-news-flow-high, **2** market-attention-high, **0** institutionally-followed as the primary label, **0** unresolved unknown as the primary label, and **0** candidate-clean extreme events.
- Provider evidence uses existing cached/derived Alpha Vantage, GDELT, FNSPID/media, fallback provider, `news_confound_master`, Bloomberg proxy, analyst coverage, and market-attention layers. No broad full-sample news rebuild was run.

The extreme-event news audit examines the largest positive and negative return reactions, rather than attempting to certify the full sample as news-clean. The audit is diagnostic: it shows whether the largest return moves coincide with official filings, public-news indicators, Bloomberg news-flow proxies, market-implied attention, or institutional following. Events with incomplete provider coverage remain unknown, not clean.

## FNSPID (static historical **media** backbone)

- **Access:** Hugging Face **Dataset Server** (`/is-valid`, `/splits`, `/first-rows`) for schema and canary; **viewer/filter/search are disabled** for `Zihan1004/FNSPID`, and `/rows` fails on hub conversion — substantive coverage uses a **single-pass HTTP stream** of `Stock_news/nasdaq_exteral_data.csv` (plus optional `All_external.csv`), with `csv.field_size_limit` raised for wide text fields.
- **Outputs:** `fnspid/fnspid_event_window_hits.csv`, `fnspid_ticker_coverage.csv`, `fnspid_year_coverage.csv`, `fnspid_summary.md`, and legacy-compatible `fnspid_derived_event_panel.csv` for the master layer. **No full article bodies** in exports.
- **Latest RunPod panel (post-stream rebuild):** ~**15.5M** primary + ~**13.1M** secondary CSV rows scanned; **340** events with deduped ±7d FNSPID article hits (all **primary_only** in source attribution).

### FNSPID verification (audit — passed)

Run `scripts/audit_fnspid_processing.py` on RunPod after each full FNSPID rebuild. Artifacts:

| File | Purpose |
| --- | --- |
| `fnspid_processing_audit.md` / `.csv` | Verdict + metrics |
| `fnspid_event_year_overlap.csv` | Events / unknown / hits by year |
| `fnspid_ticker_overlap_audit.csv` | Top tickers vs spine rows |
| `fnspid_window_sensitivity.csv` | Hits at ±1…±60d windows |
| `fnspid_secondary_dedupe_audit.csv` | Why All_external did or did not add hits |

**May 2026 audit conclusions:**

- **~79%** of events are **2024–2026** (outside FNSPID article history); all **340** hits fall in **2020–2023**.
- Window sensitivity: hits rise only **331 → 340** from ±1d to ±60d — **not** a “±7d too narrow” artifact.
- **All_external.csv:** **644** secondary rows in event ±7d windows matched tickers, but **0** new `article_key` vs primary (**644** duplicates). Secondary added **no incremental hits**; processing is correct.
- **Unknown news is never clean.**

## Multi-provider public-news master

- Module: `scripts/build_v2_public_news_confound_master_layer.py` — output under `news_confound_master/`
- **Budgeted live probes:** `scripts/probe_news_provider_canaries.py` → `plan_budgeted_news_queries.py` → `fetch_budgeted_news_providers.py` (compact cache only). Treat **403/429/missing keys** as provider-limited, never as “no news.”
- **NewsAPI / Marketaux / EODHD / Alpaca / Polygon Massive:** free-tier **diagnostics**; not a Bloomberg-grade backbone.
- **Current status counts (RunPod, post-audit + targeted unknown fetch):** **1,102** `official_confounded`, **461** `media_confounded`, **110** `market_implied_confounded`, **668** `unknown_news_coverage`, **0** `multi_source_clean` (was **710** unknown / **419** media before targeted provider pass).
- Public-news-clean claims require SEC/earnings/press-release checks, at least two successful **external** (non-FNSPID) provider checks with coverage-quality score ≥ 3, no relevant media hits, and no market-implied confound. `multi_source_clean` may be **zero** in small samples.
- Non-top weakness is therefore **not** public-news-clean in the current build.

## SEC / earnings

- Expanded SEC/earnings flags feed the master confound panel.
- See `confounds_expanded/` for merged clean / confounded / unknown counts.

## Market-implied activity screen

- Separate layer in `market_implied_confounds/`
- Flags pre-event return/volume **z-scores** (market-quiet vs market-active)
- **Not** equivalent to public-news-clean — sensitivity for abnormal pre-event trading only
- Example: non-top + market_quiet 21D SPY BHAR ≈ **-0.56%**

## Analyst relay (FMP / Finnhub + yfinance diagnostic)

- Module: `information_environment/analyst_relay/`, `information_environment/yfinance_analyst_diagnostic/`, and `bloomberg_validation/`
- **Priority:** FMP stable API → Finnhub recommendation trends → **yfinance** gap-filler (`diagnostic_yfinance_fallback`; dated pre-event rows may be event-time usable)
- yfinance improves **coverage** for narrative-relay classification; it does **not** establish analyst-news-clean or causal identification
- Analyst grade normalization now maps common grade strings (buy / outperform / equal-weight / underperform / etc.) into conservative bullish / neutral / bearish buckets; ambiguous provider action codes remain unknown
- Keys load from env or `/root/.config/fin496/marketdata.env` (never committed)
- **Dated** consensus/revisions → `analyst_event_time_usable` when pre-event rows exist
- **Latest-only** / current yfinance snapshots → diagnostic only, not event-time historical proof
- Finnhub free tier: monthly bins often **2026-only** — limited event-study depth
- FMP may **rate-limit** on bulk pulls; re-run with `FIN496_FORCE_ANALYST_RELAY=1` after cooldown
- Unknown analyst coverage is **never clean**
- Bloomberg validation is now included as an institutional mechanism layer; Bloomberg analyst coverage count (`TOT_ANALYST_REC`) is institutional-following context, not proof creators copied analysts.

## Transcript narrative relay

- Evidence-window keyword scores only (no full transcript export)
- Tests whether language resembles Wall Street / earnings / hype relay

## Paper language

| Allowed | Prohibited |
| --- | --- |
| Partial real-news metadata; unknown is not clean | Results survive complete public-news controls |
| GDELT attempted but unreliable for main robustness | GDELT validates the finding |
| Market-quiet sensitivity slice | News-clean identification |
| Multi-provider status as a diagnostic coverage audit | Non-top survives public-news-clean controls |
| Extreme-event audit for largest return moves | Full-sample news-clean certification |
