# Remaining X-native creator budget plan

Generated: 2026-05-14T23:59:00Z

## When further Apify spend is justified

**Update after RunPod replay (`9c78f0d`, `36_kaito_payload_schema_debug.md`):** candidate selection is **fixed** (dry-run **`x_creator_authored_in_selected_runs` > 0**). The **0.50 USD** capped smoke still yielded **270 returned / 0 imported** because Apify dataset rows were **`type: mock_tweet`** **placeholders** (not real tweets) — a **normalization cannot fix mocks** situation until the Actor returns real payloads.

**Update after RunPod provider canaries (`ab19753`, `2026-05-14`):** `scripts/discover_x_apify_actor_inputs.py` populated **`37_…`**. A **≤ 0.25 USD** capped canary over **`xquik`**, **`scrapebadger`**, **`apidojo_v2`** recorded **no `PASS`** in **`39_x_provider_canary_results.csv`**. Spend was **≈ 0.0011 USD** total (see CSV `run_cost_usd` / `session_spend_usd_after`). **Overnight X collection remains blocked.** Blockers: **`xquik`** — one row flagged **`suspect_same_utc_today_collapse`** (timestamp quality vs historical window); **`scrapebadger`** — run **`FAILED`**, **0** rows; **`apidojo_v2`** — **`noResults`-shaped rows** (no tweet id/text in sample; **`real_id_rate_below_threshold`**). **`38_x_provider_schema_debug.md`** replays dataset samples for **`kW6cbataRA3FQLjee`** (xquik) and **`wzCDaKL4HA6umhk1F`** (apidojo). Next: adjust actor inputs per **`37_`** / Apify docs, try **`apidojo_lite`** / **`scweet`**, or alternate queries — not larger overnight spend.

**Update (code, 2026-05-14):** `scripts/run_x_provider_canaries.py` now defaults to **`apidojo_lite`** + **`scweet`** ( **`apidojo_v2`** opt-in via **`X_PROVIDER_CANARY_INCLUDE_APIDOJO_V2=1`** ; **`xquik`** opt-in via **`X_PROVIDER_CANARY_INCLUDE_XQUIK=1`** , exploratory-only). Actor inputs are **provider-specific** (e.g. **`apidojo/twitter-scraper-lite`**: `searchTerms` + `sort`/`maxItems`/`includeSearchTerms`; **`altimis/scweet`**: `source_mode`/`search_query`/`since`/`until`/`max_items`). **`X_PROVIDER_CANARY_QUERY_MODE=strict|broad|both`** runs strict creator **`$TICKER`** queries first; **`both`** may add a **broad** probe ( **`schema_probe_not_research_sample`** ) only when strict returns **0** rows — broad never satisfies the overnight gate. **`X_PROVIDER_CANARY_INCLUDE_SANITY_QUERY=1`** adds one **`schema_sanity_control`** run ( **`AAPL since:2021-01-01 until:2021-01-08 lang:en`** , default actor **`apidojo_lite`** via **`X_PROVIDER_CANARY_SANITY_PROVIDER`**) for date/schema viability only. CSV column **`sample_kind`** must be **`research_strict`** with **`provider_status=PASS`** for **`latest_canary_pass_from_csv`** / overnight unlock. **`X_PROVIDER_PRIMARY`**: leave **unset** until such a research PASS is recorded on RunPod; if only sanity or broad probes look healthy, treat as **`SCHEMA_PASS_RESEARCH_FAIL`** and keep overnight blocked.

Spend is **not** justified for another **paid** checkpoint until:

1. **Dry-run gate:** `X_CHECKPOINT_DRY_RUN=1` shows **`x_creator_authored_in_selected_runs` > 0** for the CSV you will actually run on RunPod (ship `all_clean_events.csv` to the pod if that is the canonical list).
2. **Provider canary gate:** run `scripts/run_x_provider_canaries.py` with **`X_PROVIDER_CANARY_DRY_RUN=1`** first; then a **≤ 0.25 USD** capped canary on RunPod. **`39_x_provider_canary_results.csv`** must record **`provider_status=PASS`** within **24h** before overnight X collection (`run_main_x_collection`) is allowed (unless **`X_REQUIRE_PROVIDER_CANARY_PASS=0`** for diagnostics). See **`37_x_apify_actor_input_schema_audit.md`**, **`38_x_provider_schema_debug.md`**, **`39_x_provider_canary_results.md`**.
3. **Dataset replay gate:** `scripts/debug_kaito_dataset_schema.py` / `scripts/debug_x_provider_dataset_schema.py` should show **≥ 1** non-**`mock_tweet`** row with a real id + parseable **`created_at`** + query-relevant text so **`normalize_apify_x_post`** can succeed in principle.
4. **Normalization gate:** real-shaped rows pass **`_is_usable_finance_post`** / window / language rules for your research design.

Optional tiny spend (**≤ 0.25 USD**, skip-raw) **only** after all three gates pass — **single** smoke batch, **stop** if imports stay **0** or counters show **0** cashtags / **0** `created_at` again.

## When to hold spend

- If dataset replay still shows **only** **`mock_tweet`** rows, treat this as **Kaito / Apify product or billing configuration**, not a FIN496 pipeline-only bug.
- If the active event CSV still opens with a long unmapped-creator block **and** `CHANNEL_X` has not gained **manually verified** needles for the dominant names, expect **`x-creator-mentioned`** / **`x-creator-panel`** volume instead of true YouTube-author linkage — useful diagnostics only, not a substitute for verified `from:` maps (`34_x_creator_mapping_gap_audit.md`).

## Canonical data on RunPod

Copy `data/exports/research_expansion/all_clean_events.csv` to the pod when that file should drive row selection; the discovery order prefers it over validation exports.
