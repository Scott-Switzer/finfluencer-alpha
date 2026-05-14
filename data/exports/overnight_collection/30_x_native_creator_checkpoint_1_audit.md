# X-native creator checkpoint 1 audit

Generated: 2026-05-14T20:40:00Z  
**Live run (RunPod):** 2026-05-14T21:05Z approx., branch `x-youtube-full-research-expansion` @ `bb4bca0`.

## Execution note

Driver: `scripts/x_native_creator_checkpoint_1.py` with `PYTHONPATH=src`, `X_APIFY_SKIP_RAW_ITEM_SAVE=1`, `APIFY_SESSION_MAX_TOTAL_USD=1.25`, `X_CHECKPOINT_MAX_RUNS=8`, `X_CHECKPOINT_MAX_CHARGE_PER_RUN=0.04`, `X_CHECKPOINT_MAX_ITEMS=30`.

## 1. Spend and keys

| Field | Value |
|---|---|
| Actor runs (attempted) | **0** (driver exited before any Apify actor start) |
| Estimated spend (sum `cost_usd`) | **0.000000** |
| Session cap (`APIFY_SESSION_MAX_TOTAL_USD`) | **1.25** (shell export only) |
| Remaining session budget | **1.25** |
| Key labels used | **none** (no `choose_key` reached) |
| Keys skipped / disabled | **none** |

## 2. Blocker (failure mode)

- **Missing input file on RunPod:** `data/exports/research_expansion/all_clean_events.csv` is **not present** on the `/workspace/FIN496CAPSTONE` volume at run time.
- Script response (JSON): `{"error": "events_csv_missing", "path": "/workspace/FIN496CAPSTONE/data/exports/research_expansion/all_clean_events.csv"}`.
- **Remediation:** copy or regenerate the clean-events CSV on RunPod (without committing raw X), or refactor the checkpoint to read the same slice from the populated SQLite DB with a read-only query.

## 3. X creator coverage

- **Not executed** (no queries issued). Design targets remain as documented in `26_x_native_creator_target_windows.md` and `29_x_native_creator_panel_audit.md`.

## 4. YouTube linkage

- **Not executed** (no event rows consumed).

## 5. Collection quality

| Metric | Value |
|---|---|
| Total posts returned | 0 |
| Posts imported | 0 |
| Posts with parsed `created_at` | 0 |
| Explicit cashtag posts | 0 |
| Duplicate rows | 0 |
| Current-day collapse observed | **no** (no data) |

## 6. Creator specificity mix

| Query type bucket | Count |
|---|---:|
| x-creator-authored | 0 |
| ticker-only-control | 0 |

## 7. Decision gate

**Checkpoint verdict:** **PARTIAL PASS** — key-rotation and spend plumbing were exercised only through import/start-up; **no** Kaito pulls ran because the YouTube clean-event CSV path was absent on RunPod.

**`31_remaining_x_native_creator_budget_plan.md`:** **not created** (checkpoint did not reach a PASS state).

## Safety

- No raw tweet payloads, Apify JSON dumps, or tokens were written to this audit.
- `.env` was not printed or modified by this checkpoint attempt.
