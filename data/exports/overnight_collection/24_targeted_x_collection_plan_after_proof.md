# Targeted X collection plan (post historical proof)

Generated: 2026-05-14T18:15:00Z

Audience: operator of `Scott-Switzer/finfluencer-alpha` on RunPod, branch `x-youtube-full-research-expansion`.

## Preconditions

- Historical date filtering for Kaito is documented as **PASS** in `20_x_historical_proof_test.md` (multi-window section: prior `$TSLA` 2020 window plus three new windows).
- **Do not** commit raw X payloads, Apify JSON dumps, logs, DB snapshots, or `.env`.
- **Do not** add new API keys until this `$5` phase completes and a post-run quality audit passes.
- RunPod **X platform ledger headroom** is tight (near configured cap in `ApifyKeyManager`); raise caps or rotate keys only with explicit budget approval.

## Budget and checkpoints

- **First tranche:** about **$5.00** total Apify spend for X, not the full `$20` envelope.
- **Checkpoint cadence:** pause and review after every **~$1.00** incremental spend (ledger CSV + Apify console usage).
- **Stop conditions:** halt immediately if timestamps show same-day collapse, if `since_time` / `until_time` drift from requested windows, if duplicate rate spikes, or if finance-quality ratio collapses versus the overnight audit baselines.

## Actor and strict input schema

- **Actor:** `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`.
- **Required input fields (only):** `searchTerms`, `since_time`, `until_time`, `maxItems`.
- **Conditionally allowed (actor schema / repo helper):** `queryType`, `lang`, and the existing `searchTerms` string composition produced by `build_x_actor_input()` (cashtag + `lang:en -filter:retweets` + embedded `since_time` / `until_time` in the query text, plus top-level UNIX fields).
- **Forbidden as primary date control:** `query`, `queries`, `keywords`, `startDate`, `endDate`, `since`, `until`, `language`, `sort` (do not introduce these as actor-level keys).

## Universe construction

- **Queries:** explicit cashtags only (`$TICKER`), aligned with `config/x_sources/cashtags.txt` seed universe where possible.
- **Tickers:** prioritize **YouTube-linked event tickers** and names that already passed transcript or metadata alignment in the overnight audit.
- **Windows:** short spans around validated YouTube recommendation / publication dates (typically a few days before through a few days after), never whole-year pulls in this phase.

## `maxItems` discipline

- Default **20–50** items per cashtag per narrow window unless a pilot shows stable yield.
- Keep `maxTotalChargeUsd` per Apify run small enough to respect both the **global X cap** and the **$1 checkpoint** slices.

## Outputs and tables (no raw commits)

- Persist **aggregates only** into existing markdown ledgers under `data/exports/overnight_collection/` (counts, cost, pass/fail gates, anomaly lists with tweet IDs redacted or hashed).
- Store normalized rows through the existing **SQLite import path** on RunPod if needed, but **never** `git add` `*.db`, `data/raw/apify/x`, or dataset dumps.

## Quality gate before any larger spend

- Run `python3 -m ruff check .` and `python3 -m pytest tests/`.
- Recompute date coverage via `analyze_x_date_coverage()` on imported `created_at` values.
- Only if this `$5` tranche passes should you schedule an additional **$10–$15** follow-on tranche with the same checkpoint rules.

## Inference guardrails

- **No X-only final inference** until a post-collection classifier audit confirms cashtag and recommendation fields behave as expected on the new slice.
- This document is operational guidance only; it does not assert causal alpha, human labels, or production trading performance.
