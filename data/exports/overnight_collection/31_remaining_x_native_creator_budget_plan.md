# Remaining X-native creator budget plan

Generated: 2026-05-14T22:35:00Z

## When further Apify spend is justified

After deploying `scripts/x_native_creator_checkpoint_1.py` updates on RunPod (mapped-first ordering, query tiering, per-event Kaito date windows), run a **single** capped checkpoint:

- `X_APIFY_SKIP_RAW_ITEM_SAVE=1`
- `APIFY_SESSION_MAX_TOTAL_USD` at or below **0.75** for a smoke batch
- Confirm JSON shows non-zero **`x-creator-authored`** rows when `all_clean_events.csv` or validation exports include mapped creators near the top of the prioritized pool.

## When to hold spend

- If the active event CSV still opens with a long unmapped-creator block **and** `CHANNEL_X` has not gained **manually verified** needles for the dominant names, expect **`x-creator-mentioned`** / **`x-creator-panel`** volume instead of true YouTube-author linkage — useful diagnostics only, not a substitute for verified `from:` maps (`34_x_creator_mapping_gap_audit.md`).

## Canonical data on RunPod

Copy `data/exports/research_expansion/all_clean_events.csv` to the pod when that file should drive row selection; the discovery order prefers it over validation exports.
