# Remaining X-native creator budget plan

Generated: 2026-05-14T22:35:00Z

## When further Apify spend is justified

**Update after driver + diagnostics work:** the **candidate truncation** bug is fixed in `scripts/x_native_creator_checkpoint_1.py` via **`X_CHECKPOINT_DISCOVERY_POOL_SIZE`** (default **5000**) and **`X_CHECKPOINT_DRY_RUN=1`** for a no-cost candidate plan. A local dry-run against `all_clean_events.csv` can show **non-zero** `x-creator-authored` selections once the widened pool is in use.

Spend is **not** justified for another **paid** checkpoint until:

1. **Dry-run gate:** `X_CHECKPOINT_DRY_RUN=1` shows **`x_creator_authored_in_selected_runs` > 0** for the CSV you will actually run on RunPod (ship `all_clean_events.csv` to the pod if that is the canonical list).
2. **Normalization gate:** `35_x_checkpoint_zero_import_debug.md` / fixture diagnostics show that items can pass **`normalize_apify_x_post`** and **`_is_usable_finance_post`** for the query shapes you intend to run; otherwise expect **0 imports** even when Apify returns rows.

Optional tiny spend (**≤ 0.50 USD**, skip-raw) **only** after both gates pass, for a **single** smoke batch — stop immediately if imports stay at **0**.

## When to hold spend

- If the active event CSV still opens with a long unmapped-creator block **and** `CHANNEL_X` has not gained **manually verified** needles for the dominant names, expect **`x-creator-mentioned`** / **`x-creator-panel`** volume instead of true YouTube-author linkage — useful diagnostics only, not a substitute for verified `from:` maps (`34_x_creator_mapping_gap_audit.md`).

## Canonical data on RunPod

Copy `data/exports/research_expansion/all_clean_events.csv` to the pod when that file should drive row selection; the discovery order prefers it over validation exports.
