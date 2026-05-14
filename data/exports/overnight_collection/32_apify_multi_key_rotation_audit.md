# Apify multi-key rotation audit

Generated: 2026-05-14T20:30:00Z

## Scope

This document describes how `ApifyKeyManager` loads and rotates Apify credentials for X (and shared) collection, after the resilient rotation patch. No `.env` contents, token values, or raw Apify payloads are recorded here.

## Key loading

- Indexed variables `APIFY_TOKEN_1` … `APIFY_TOKEN_N` are read in ascending numeric order when `APIFY_TOKEN_COUNT=N` (N > 0). Empty slots are skipped; order among defined keys follows index order so **older low-index keys are tried before higher-index keys**.
- If `APIFY_TOKEN_COUNT` is unset or zero, the loader falls back to scanning indices `1..20` for backwards compatibility.
- If no indexed tokens exist but `APIFY_TOKEN` is set, a single fallback key is created (label `APIFY_TOKEN` or `APIFY_TOKEN_LABEL`).
- `APIFY_MULTI_KEY_MODE` may be set to `0` / `false` / `single` to restrict runtime to **only the first** indexed key (legacy single-key behavior).

## Caps and ordering

| Mechanism | Behavior |
|---|---|
| Per-key cap | `APIFY_TOKEN_i_MAX_TOTAL_USD` plus optional `APIFY_TOKEN_i_MIN_REMAINING_USD` reserves headroom under the per-key ceiling. |
| Platform / global cap | `X_TOTAL_COST_CAP_USD` (X) or `APIFY_GLOBAL_MAX_TOTAL_USD` (shared) still gate `choose_key` via ledger-backed `platform_spend`. |
| Global min headroom | `APIFY_GLOBAL_MIN_REMAINING_USD` blocks a pick when remaining headroom under the platform cap would drop below the configured floor. |
| **Session cap** | `APIFY_SESSION_MAX_TOTAL_USD` limits **incremental** spend for the current checkpoint session only (in-memory `session_spend_usd`, reset via `begin_session()`). This is separate from lifetime ledger totals reflected in global caps. |
| Pick order | `choose_key` scans keys **in index order** (no round-robin cursor), selecting the first key that is not permanently disabled, not session-excluded, and `can_spend(projected)`. |

## Failure handling

| Failure signal | Typical classification | Default policy |
|---|---|---|
| HTTP 401 / unauthorized / invalid token | `auth` | Permanent disable when `APIFY_DISABLE_KEY_ON_AUTH_ERROR` is true (default); otherwise session-exclude only. |
| HTTP 402 / payment / insufficient / quota exhausted | `credit` | Session-exclude when `APIFY_DISABLE_KEY_ON_CREDIT_ERROR` is false (default); permanent disable when set true. |
| HTTP 429 / rate limit / timeouts / 502–504 | `transient` | Count per key; after `APIFY_MAX_TRANSIENT_RETRIES_PER_KEY` (default mirrors `APIFY_MAX_KEY_FAILURES_PER_RUN`) the key is session-excluded so the next index can run. |
| Actor `FAILED` status with a key-health message | Same classifier on `statusMessage` | `run_single_x_apify_source` retries with another key when `note_key_failure_for_rotation` returns true. |
| Empty datasets, parsing / timestamp quality issues | **Not** classified as key failures | Keys are not disabled; `record_run(..., key_health_failure=False)` avoids coupling data quality to credential health. |

## Environment toggles

- `APIFY_SKIP_EXHAUSTED_KEYS` (default true): exhausted keys are skipped rather than selected.
- `APIFY_MAX_KEY_FAILURES_PER_RUN`: cap on repeated `mark_failure` strikes before permanent disable (legacy path).
- `APIFY_MAX_TRANSIENT_RETRIES_PER_KEY`: optional override for transient retries before session exclusion (defaults to the same numeric value when unset).
- `X_APIFY_SKIP_RAW_ITEM_SAVE`: when true/`1`, `run_single_x_apify_source` skips writing raw Apify JSON shards under `data/raw/apify/x` (checkpoint-friendly).

## Session observability

`ApifyKeyManager.session_key_status_summary()` returns rows with:

- `label`, `used_this_session`, `permanently_disabled`, `session_excluded`, `disable_reason_category`, `transient_hits_this_session`, `estimated_spend_this_session_usd`, `calls_attempted_this_session`

… and **never** includes secret material.

## Safety

- `.env` was not printed, cat-ed, or committed while preparing this change set.
- Token literals do not appear in structured summaries (`safe_summary`, `public_summary`, `repr` of `ApifyKey`).
