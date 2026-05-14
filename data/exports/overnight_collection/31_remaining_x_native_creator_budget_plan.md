# Remaining X-native creator budget plan

Generated: 2026-05-14T22:35:00Z

## When further Apify spend is justified

**Update after RunPod paid smoke (`30_x_native_creator_checkpoint_1_audit.md`, `19c853b`):** a **0.50 USD** capped batch ran **only on RunPod** after dry-run showed **18** `x-creator-authored` candidates. All **18** actor runs **`SUCCEEDED`**, but **270 returned / 0 imported** with **zero** cashtag / `created_at` counter hits — same **normalization gate** as prior smokes. **Hold further Apify spend** until `35_x_checkpoint_zero_import_debug.md` items are resolved in code or actor payload shapes are reconciled.

Spend is **not** justified for another **paid** checkpoint until:

1. **Dry-run gate:** `X_CHECKPOINT_DRY_RUN=1` shows **`x_creator_authored_in_selected_runs` > 0** for the CSV you will actually run on RunPod (ship `all_clean_events.csv` to the pod if that is the canonical list).
2. **Normalization gate:** `35_x_checkpoint_zero_import_debug.md` / fixture diagnostics show that items can pass **`normalize_apify_x_post`** and **`_is_usable_finance_post`** for the query shapes you intend to run; otherwise expect **0 imports** even when Apify returns rows.

Optional tiny spend (**≤ 0.50 USD**, skip-raw) **only** after both gates pass, for a **single** smoke batch — stop immediately if imports stay at **0**.

## When to hold spend

- If the active event CSV still opens with a long unmapped-creator block **and** `CHANNEL_X` has not gained **manually verified** needles for the dominant names, expect **`x-creator-mentioned`** / **`x-creator-panel`** volume instead of true YouTube-author linkage — useful diagnostics only, not a substitute for verified `from:` maps (`34_x_creator_mapping_gap_audit.md`).

## Canonical data on RunPod

Copy `data/exports/research_expansion/all_clean_events.csv` to the pod when that file should drive row selection; the discovery order prefers it over validation exports.
