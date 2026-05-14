# X-native creator checkpoint 1 audit

Generated: 2026-05-14T21:50:00Z  
**Live run (RunPod):** after env readiness fixes; repo `x-youtube-full-research-expansion` @ `b31a5d9` + patched `scripts/x_native_creator_checkpoint_1.py` deployed via `scp`.

## 1. Gates and env (non-secret)

| Gate | Result |
|---|---|
| `APIFY_TOKEN_COUNT == 11` | **yes** |
| `APIFY_TOKEN_1` … `APIFY_TOKEN_11` present | **all yes** (booleans only; no values logged) |
| `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN == 1` | **yes** |
| `APIFY_SESSION_MAX_TOTAL_USD == 1.25` | **yes** |
| `X_APIFY_SKIP_RAW_ITEM_SAVE == 1` | **yes** |
| Target events source | **`csv:data/exports/validation/clean_auto_labeled_events.csv`** (`all_clean_events.csv` absent on pod; script used safe export fallback) |

## 2. Spend and keys

| Field | Value |
|---|---|
| Session cap | **1.25 USD** |
| **Session spend (manager ledger)** | **~0.0515 USD** (under cap) |
| Actor runs attempted | **8** |
| All runs `SUCCEEDED` (actor status) | **8 / 8** |
| Key labels used | **`apify_main` only** (all eight runs) |
| Keys skipped / rotated | **none** (no credit/auth failures in this batch) |

## 3. Posts and import quality (pipeline counters)

| Metric | Value |
|---|---|
| Posts returned (sum `posts_returned`) | **320** |
| Posts imported to SQLite (sum `posts_imported`) | **117** |
| Rows with parsed `created_at` hits (`posts_with_created_at`) | **320** |
| Explicit cashtag counter hits (`posts_with_cashtags`) | **320** |
| Usable finance post counter (`usable_finance_posts`) | **320** |
| Implied duplicate / already-present rows (`returned − imported`) | **203** |
| Total Apify-reported cost (sum `cost_usd`) | **~0.0515 USD** |

## 4. Window / timestamp QA

- The checkpoint driver **does not** currently re-parse each tweet timestamp against `[since_time, until_time]` in Python; it relies on the **Kaito + `build_x_actor_input()` UNIX bounds** and downstream normalization inside `run_single_x_apify_source`.
- **Current-day collapse:** not evaluated row-by-row in this driver; prior multi-window audit supports historical mode for Kaito with UNIX bounds.

## 5. Creator specificity

| Bucket | Count (of 8 runs) |
|---|---:|
| `x-creator-authored` | **0** |
| `ticker-only-control` | **8** |

**Reason:** the first eight validation CSV rows were all **“Parkev Tatevosian, CFA”** events with **no deterministic handle mapping** in the small `CHANNEL_X` map, so the script correctly fell back to **labeled ticker-only controls**.

## 6. YouTube linkage

- Tickers/windows: **PLTR** and **META** near-term 2026 windows (see JSON run list on RunPod host if needed).
- YouTube video IDs present on each run row in the checkpoint JSON (`youtube_video_id`).

## 7. Decision

**Checkpoint verdict:** **PARTIAL PASS**

- **Passes:** real Apify runs executed; spend **well under** `APIFY_SESSION_MAX_TOTAL_USD`; actor **`SUCCEEDED`** on all eight calls; explicit-cashtag counters matched returned rows; keys stayed under the (raised) X cap after non-secret `.env` tuning documented in `33_runpod_env_readiness_audit.md`.
- **Fails PASS bar:** **no X-native creator-authored or creator-panel rows** in this batch (100% ticker-only controls); duplicate import rate is **high** (expected when re-hitting similar windows / overlapping content).

**`31_remaining_x_native_creator_budget_plan.md`:** **not created** (checkpoint did not meet full PASS criteria).

## 8. Remaining budget guidance

- Additional spend should wait until: (a) **handle mapping** is expanded for the dominant YouTube creators in the validation slice, and/or (b) **`all_clean_events.csv`** is synced to RunPod if that file is the preferred canonical event list.
- Keep **`APIFY_SESSION_MAX_TOTAL_USD`** as the hard checkpoint ceiling; treat **`X_TOTAL_COST_CAP_USD`** as a separate ledger headroom knob that may need occasional non-secret adjustment when the ledger sits near saturation.

## Safety

- Raw Apify JSON shards were suppressed via `X_APIFY_SKIP_RAW_ITEM_SAVE=1`.
- No tweet bodies, tokens, or `.env` contents are embedded in this audit.
