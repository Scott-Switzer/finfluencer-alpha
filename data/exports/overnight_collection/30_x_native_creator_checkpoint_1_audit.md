# X-native creator checkpoint 1 audit

Generated: 2026-05-14T20:40:00Z

## Execution note

Checkpoint driver: `scripts/x_native_creator_checkpoint_1.py` (RunPod: `PYTHONPATH=src`, `X_APIFY_SKIP_RAW_ITEM_SAVE=1`, `APIFY_SESSION_MAX_TOTAL_USD=1.25`). This file is updated after the live RunPod pass; **metrics below reflect the first post-rotation checkpoint** (see git history if revised).

## 1. Spend and keys

| Field | Value |
|---|---|
| Actor runs (attempted) | *filled post-run* |
| Estimated spend (sum `cost_usd`) | *filled post-run* |
| Session cap (`APIFY_SESSION_MAX_TOTAL_USD`) | 1.25 (operator export; not committed in `.env`) |
| Remaining session budget | *filled post-run* |
| Key labels used | *filled post-run (labels only)* |
| Keys skipped / disabled (category only) | *filled post-run* |

## 2. X creator coverage

- Targeted handles / query stems: mix of `from:<handle> $<TICKER>` and labeled `$<TICKER>` controls per `26_x_native_creator_target_windows.md`.
- Categories: stock-picking / education / macro / news as tagged in `29_x_native_creator_panel_audit.md`.

## 3. YouTube linkage

- Event tickers and dates drawn from `all_clean_events.csv` (first N rows processed by the checkpoint script).
- YouTube creator / video IDs echoed per run in JSON (`runs[].youtube_*` fields).

## 4. Collection quality (aggregates only)

| Metric | Value |
|---|---|
| Total posts returned | *post-run* |
| Posts imported | *post-run* |
| Posts with parsed `created_at` | *post-run* |
| Explicit cashtag posts (pipeline counter) | *post-run* |
| Duplicate rows (pipeline counter) | *post-run* |
| Current-day collapse observed | *post-run (yes/no)* |

## 5. Creator specificity mix

| Query type bucket | Count |
|---|---:|
| x-creator-authored | *post-run* |
| ticker-only-control | *post-run* |

## 6. Overlap / attention value (descriptive)

- YouTube events with ≥1 matching creator-specific X pull: *post-run*
- Tickers with creator-specific coverage: *post-run*
- Years covered: inferred from event dates in the processed batch

## 7. Failure modes observed

- *Populated post-run* (examples: missing handle mapping → ticker-only control; actor `FAILED`; key rotation; low cashtag yield).

## 8. Decision gate

**Checkpoint verdict:** *PASS / PARTIAL PASS / FAIL — filled post-run.*

PASS requires: valid historical timestamps, no current-day collapse, meaningful creator-specific coverage, acceptable duplicate and cashtag rates, resilient key rotation without manual key picking, spend under session cap.

## Safety

- No raw tweet text, Apify JSON blobs, or tokens are committed with this audit.
- Raw JSON writes suppressed via `X_APIFY_SKIP_RAW_ITEM_SAVE` for this checkpoint driver.
