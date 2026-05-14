# Remaining X-native creator budget plan

Generated: 2026-05-14T22:35:00Z

## When further Apify spend is justified

**Update after 2026-05-14 smoke (`30_x_native_creator_checkpoint_1_audit.md`):** the **0.75 USD** capped run completed, but **`x-creator-authored` stayed at zero** because the **54-row CSV head** (three × max runs) contained **no** `CHANNEL_X` matches on that pod export. **Do not increase caps** to “force” authored pulls.

Spend is **not** justified for another broad checkpoint until:

1. **Discovery pool fix:** widen or re-source events so **mapped** creators are actually eligible (e.g. ship `all_clean_events.csv` to RunPod, or change the driver to scan beyond the first `max_runs×3` rows / merge mapped rows explicitly).
2. **Manual `CHANNEL_X` expansion** for the **highest-volume** unmapped YouTube names **after** profile verification (`34_x_creator_mapping_gap_audit.md`).

Optional tiny spend **only** for **row-level QA** (single run, tiny `maxItems`) if engineering needs to reproduce why **`posts_with_cashtags` / `posts_with_created_at` were all zero** on mention/panel queries — still capped and skip-raw.

## When to hold spend

- If the active event CSV still opens with a long unmapped-creator block **and** `CHANNEL_X` has not gained **manually verified** needles for the dominant names, expect **`x-creator-mentioned`** / **`x-creator-panel`** volume instead of true YouTube-author linkage — useful diagnostics only, not a substitute for verified `from:` maps (`34_x_creator_mapping_gap_audit.md`).

## Canonical data on RunPod

Copy `data/exports/research_expansion/all_clean_events.csv` to the pod when that file should drive row selection; the discovery order prefers it over validation exports.
