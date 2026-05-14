# X-native creator checkpoint 1 audit

## Latest: RunPod (`19c853b`) — dry-run gate + capped author smoke

Generated: 2026-05-14T21:00:00Z
**Host:** RunPod `/workspace/FIN496CAPSTONE` (confirmed: `USER=root`, `PWD=/workspace/FIN496CAPSTONE`, Linux container hostname `b00f50b71ec1`). **Not** local Mac.

### Dry-run gate (no Apify)

| Field | Value |
|---|---|
| Repo `HEAD` | **`19c853b`** |
| Event source | **`csv:data/exports/validation/clean_auto_labeled_events.csv`** (`all_clean_events.csv` **absent** on this pod) |
| `X_CHECKPOINT_DISCOVERY_POOL_SIZE` | **5000** (file had **562** rows; full file loaded) |
| Total rows loaded | **562** |
| Valid event rows | **562** |
| Mapped rows in valid pool | **19** |
| Selected run count | **18** |
| `query_type_counts` | **`x-creator-authored`: 18** |
| `x_creator_authored_in_selected_runs` | **18** |
| Selected creators (distinct) | Meet Kevin, Everything Money, Graham Stephan, Stock Moe, The Plain Bagel |
| Selected tickers (distinct) | NVDA, AAPL, PYPL, DIS, META, AMZN, GOOGL, UBER, TSLA |

### Capped paid smoke (`APIFY_SESSION_MAX_TOTAL_USD=0.50`)

| Field | Value |
|---|---|
| Command | `X_APIFY_SKIP_RAW_ITEM_SAVE=1 APIFY_SESSION_MAX_TOTAL_USD=0.50 PYTHONPATH=src .venv/bin/python scripts/x_native_creator_checkpoint_1.py` |
| Session spend (manager ledger) | **~0.0447 USD** |
| Actor runs | **18** (`18` × **`SUCCEEDED`**) |
| `query_type` mix | **18 × `x-creator-authored`** |
| Posts returned / imported | **270** / **0** |
| `posts_with_cashtags` (sum) | **0** |
| `posts_with_created_at` (sum) | **0** |
| Key labels | **`apify_main` only** (labels only; no tokens logged) |

**Verdict (this batch):** **PARTIAL PASS** — dry-run proves **mapped-first + widened pool** yields **author-only** queries on RunPod validation CSV, but **imports and field-quality counters are still zero**, matching the **normalization / `_is_usable_finance_post` gating** diagnosis in `35_x_checkpoint_zero_import_debug.md`. **Stop further paid X checkpoints** until that path is fixed or payloads are proven compatible.

---

## Prior: capped smoke checkpoint (RunPod, `547beb7`)

Generated: 2026-05-14T22:20:00Z
**Host:** RunPod workspace `/workspace/FIN496CAPSTONE` after `git pull` to **`547beb7`** (local `scripts/x_native_creator_checkpoint_1.py` stash was required once so `git pull` could fast-forward).
**Command:** `X_APIFY_SKIP_RAW_ITEM_SAVE=1 APIFY_SESSION_MAX_TOTAL_USD=0.75 PYTHONPATH=src .venv/bin/python scripts/x_native_creator_checkpoint_1.py`

### Gates and env (non-secret)

| Gate | Result |
|---|---|
| `.env` present | **yes** |
| `APIFY_TOKEN_COUNT` | **11** |
| Indexed `APIFY_TOKEN_1` … `APIFY_TOKEN_11` present | **yes** (values not logged) |
| `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN` | **1** |
| Runtime `APIFY_SESSION_MAX_TOTAL_USD` (smoke) | **0.75** (`.env` still showed **1.25**; smoke used the process cap **0.75**) |
| `X_APIFY_SKIP_RAW_ITEM_SAVE` | **1** (runtime + `.env`) |

### Spend and keys

| Field | Value |
|---|---|
| Session cap (effective) | **0.75 USD** |
| Session spend (manager ledger) | **~0.0611 USD** |
| Actor runs (`len(runs)`) | **18** |
| Run status | **17 × `SUCCEEDED`**, **1 × `FAILED`** (actor wait timeout at default **60s**) |
| Key labels used | **`apify_main` only** (all 18 runs) |
| Keys skipped / rotated | **none** logged for credit/auth in this batch |

### Query mix (this smoke batch)

| `query_type` | Runs | Posts returned (sum) | Posts imported (sum) |
|---|---:|---:|---:|
| `x-creator-authored` | **0** | **0** | **0** |
| `x-creator-mentioned` | **17** | **240** | **0** |
| `x-creator-panel` | **1** | **15** | **0** |
| `ticker-only-control` | **0** | **0** | **0** |

**Why `x-creator-authored` stayed at zero:** `discover_events()` still reads only the **first `X_CHECKPOINT_MAX_RUNS × 3` CSV rows** in file order **before** `prioritize_checkpoint_events()` sorts. On this RunPod export, that **54-row head slice** contained **no** `CHANNEL_X` matches, so every eligible row fell through to **mention** (two-token phrase + cashtag) or, when the phrase was too short, **panel** (`Dividendology` → panel). **Fix for next iteration:** widen the discovery pool (read more rows, full scan, or prefer `all_clean_events.csv` on the pod) so mapped creators can enter the candidate set.

### Posts and import quality (pipeline counters, smoke)

| Metric | Value |
|---|---|
| Posts returned (sum `posts_returned`) | **255** |
| Posts imported (sum `posts_imported`) | **0** |
| `posts_with_cashtags` (sum) | **0** |
| `posts_with_created_at` (sum) | **0** |
| `usable_finance_posts` (sum) | **0** |

**Interpretation:** Apify returned items, but **normalization / finance filters rejected every item** in this batch (no cashtag hits and no parseable `created_at` hits in the checkpoint counters). This is **not** the same outcome as the earlier smoke where imports were non-zero; treat this batch as a **pipeline-quality regression signal** for these query shapes until row-level QA is done on RunPod (no raw payloads committed here).

### Duplicate pressure

With **255** returned and **0** imported, **100%** of returned rows failed the import path for this run (duplicates vs rejects not split in the checkpoint JSON).

### Window / timestamp QA

- Per-event **`date_start` / `date_end`** are now passed into `run_single_x_apify_source` on **`547beb7`**, so Kaito **`since_time` / `until_time`** align with each run’s logged window.
- **Inside-window rate:** **not computed** in the checkpoint driver (no per-post timestamp audit in Python here).
- **Current-day collapse:** **not evaluated** row-by-row in this driver output.

### Decision (smoke)

**Checkpoint verdict:** **PARTIAL PASS**

- **Passes:** spend **under** the **0.75** cap; **non-ticker-only** query diversity (**mention** + **panel**); mapping/ordering diagnosis is clearer.
- **Fails full PASS:** **zero** `x-creator-authored` rows; **zero** SQLite imports; **zero** cashtag / `created_at` counter hits; one **timeout** failure.

---

## Prior batch: first RunPod checkpoint (pre-`547beb7` driver behavior)

Generated: 2026-05-14T21:50:00Z  
**Live run (RunPod):** after env readiness fixes; repo `x-youtube-full-research-expansion` @ `b31a5d9` + patched `scripts/x_native_creator_checkpoint_1.py` deployed via `scp`.

### Gates and env (non-secret)

| Gate | Result |
|---|---|
| `APIFY_TOKEN_COUNT == 11` | **yes** |
| `APIFY_TOKEN_1` … `APIFY_TOKEN_11` present | **all yes** (booleans only; no values logged) |
| `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN == 1` | **yes** |
| `APIFY_SESSION_MAX_TOTAL_USD == 1.25` | **yes** |
| `X_APIFY_SKIP_RAW_ITEM_SAVE == 1` | **yes** |
| Target events source | **`csv:data/exports/validation/clean_auto_labeled_events.csv`** (`all_clean_events.csv` absent on pod; script used safe export fallback) |

### Spend and keys (prior)

| Field | Value |
|---|---|
| Session cap | **1.25 USD** |
| **Session spend (manager ledger)** | **~0.0515 USD** (under cap) |
| Actor runs attempted | **8** |
| All runs `SUCCEEDED` (actor status) | **8 / 8** |
| Key labels used | **`apify_main` only** (all eight runs) |
| Keys skipped / rotated | **none** (no credit/auth failures in this batch) |

### Posts and import quality (prior)

| Metric | Value |
|---|---|
| Posts returned (sum `posts_returned`) | **320** |
| Posts imported to SQLite (sum `posts_imported`) | **117** |
| Rows with parsed `created_at` hits (`posts_with_created_at`) | **320** |
| Explicit cashtag counter hits (`posts_with_cashtags`) | **320** |
| Usable finance post counter (`usable_finance_posts`) | **320** |
| Implied duplicate / already-present rows (`returned − imported`) | **203** |
| Total Apify-reported cost (sum `cost_usd`) | **~0.0515 USD** |

### Creator specificity (prior)

| Bucket | Count (of 8 runs) |
|---|---:|
| `x-creator-authored` | **0** |
| `ticker-only-control` | **8** |

**Reason:** the first eight validation CSV rows were all **“Parkev Tatevosian, CFA”** events with **no deterministic handle mapping** in the small `CHANNEL_X` map, so the script correctly fell back to **labeled ticker-only controls**.

### Prior decision

**Checkpoint verdict:** **PARTIAL PASS** for that batch (real pulls; all `SUCCEEDED`; high duplicate pressure; no creator-authored rows).

## Safety

- Raw Apify JSON shards were suppressed via `X_APIFY_SKIP_RAW_ITEM_SAVE=1`.
- No tweet bodies, tokens, or `.env` contents are embedded in this audit.
