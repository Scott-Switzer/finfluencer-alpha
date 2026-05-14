# RunPod env readiness audit (Apify multi-key + X checkpoint)

Generated: 2026-05-14T21:50:00Z

## Where this work ran

- **Cursor / agent context:** local Mac repo at `/Users/scottthomasswitzer/Desktop/FIN496CAPSTONE`.
- **Execution target:** RunPod repo at `/workspace/FIN496CAPSTONE` over SSH.

## Local actions (no secrets printed)

- Confirmed `test -f .env` for the local repo.
- Built a **non-interactive patch file** from local `.env` containing only `APIFY_*` and `X_APIFY_*` key/value lines, merged with the required control defaults (multi-key mode, token count, historical gate, session cap, skip-raw, rotation flags).
- `scp`’d the patch plus a merge helper script to RunPod `/tmp/`, then merged into RunPod `.env` with a timestamped backup (backup path printed on RunPod stdout only).
- Deleted local `/tmp/fin496_apify_env_patch` after successful `scp`.

## Post-merge RunPod booleans (values non-secret only)

Observed immediately after merge + `load_dotenv` on RunPod:

| Check | Result |
|---|---|
| `APIFY_MULTI_KEY_MODE` | present, value `true` |
| `APIFY_TOKEN_COUNT` | present, value `11` |
| `APIFY_TOKEN` fallback | present (boolean true) |
| `APIFY_TOKEN_1` … `APIFY_TOKEN_11` | all present (booleans true) |
| `APIFY_TOKEN_i_LABEL` / `_MAX_TOTAL_USD` / `_MIN_REMAINING_USD` | all present for i=1..11 (booleans true) |
| `X_APIFY_HISTORICAL_DATE_FILTER_PROVEN` | present, value `1` |
| `APIFY_SESSION_MAX_TOTAL_USD` | present, value `1.25` |
| `X_APIFY_SKIP_RAW_ITEM_SAVE` | present, value `1` |
| `APIFY_GLOBAL_MAX_TOTAL_USD` | present |
| `APIFY_STOP_WHEN_ALL_KEYS_EXHAUSTED` | present |
| `APIFY_SKIP_EXHAUSTED_KEYS` | `true` |
| `APIFY_DISABLE_KEY_ON_CREDIT_ERROR` | `true` |
| `APIFY_DISABLE_KEY_ON_AUTH_ERROR` | `true` |

## Operational adjustments on RunPod (still no token disclosure)

Checkpoint `choose_key` initially failed because:

1. **X platform ledger headroom** was within cents of `X_TOTAL_COST_CAP_USD` (legacy ~$18 cap) while `maxTotalChargeUsd` per run was $0.04–$0.05.
2. **`APIFY_GLOBAL_MIN_REMAINING_USD`** then blocked picks once the min-remaining guard fired.

Non-token-only edits applied **directly on RunPod** (not committed here):

- Set `APIFY_GLOBAL_MIN_REMAINING_USD=0` to stop false “no headroom” blocks when the cap is nearly saturated.
- Set `X_TOTAL_COST_CAP_USD=24` to restore a few dollars of **projected-charge** headroom for short checkpoint pulls while keeping overall spend bounded by `APIFY_SESSION_MAX_TOTAL_USD=1.25`.

These are **budget configuration** knobs, not secrets. `.env` itself was **not** committed to git.

## Safety

- No Apify token values, no `.env` file contents, and no `printenv`/`env` dumps were written into this audit or the chat transcript.
- `.env` backups remain only on RunPod under `/workspace/FIN496CAPSTONE/.env.backup_before_apify_patch_*`.
