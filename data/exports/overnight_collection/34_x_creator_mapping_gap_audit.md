# X creator mapping gap audit (YouTube validation slice)

Generated: 2026-05-14T22:30:00Z  
Repo branch: `x-youtube-full-research-expansion` (local audit against committed exports).

## Executive summary

The checkpoint driver (`scripts/x_native_creator_checkpoint_1.py`) chooses **`from:{handle} ${TICKER}`** only when `resolve_x_handle(youtube_creator)` returns a handle from the small `CHANNEL_X` substring map. Most rows in `data/exports/validation/clean_auto_labeled_events.csv` use **creator names that do not match any needle**, so the script correctly emitted **`ticker-only-control`** queries for those runs. A second failure mode was **iteration order**: the driver consumed the first **N** valid CSV rows in file order; on some hosts the early slice can be dominated by one unmapped creator, yielding **zero** `x-creator-authored` runs even when mapped creators exist later in the same file.

**Creator mapping readiness verdict:** **PARTIAL PASS** — a narrow set of finance YouTubers is mapped with reasonable confidence, but **volume-weighted coverage** of the validation export is low; expanding curated mappings (or syncing `all_clean_events.csv` to RunPod for a better row mix) is required before treating checkpoint batches as creator-linked X probes.

## Top YouTube creators in `clean_auto_labeled_events.csv` (by clean event count)

Counts from `creator` column (113 rows total). **Mapped** means `resolve_x_handle` returns non-`None` using committed `CHANNEL_X` needles after removing the weak `wsb` → `TheRoaringKitty` shortcut (see script change; Roaring Kitty remains **uncertain / not used** for YouTube attribution).

| Events | YouTube `creator` | X handle mapped | Mapping basis |
|---:|---|---|---|
| 20 | Jose Najarro Stocks | **missing** | No audited handle in `CHANNEL_X`. |
| 9 | Learn to Invest - Investors Grow | **missing** | No audited handle. |
| 8 | Mark Roussin, CPA | **missing** | No audited handle. |
| 7 | Financial Education | **missing** | Common brand phrase; **do not guess** (many homonyms on X). |
| 7 | Best of Us Investors | **missing** | No audited handle. |
| 7 | Couch Investor | **missing** | No audited handle. |
| 6 | Graham Stephan | **GrahamStephan** | `graham` needle; treat as **verified-style** channel match. |
| 6 | STOCK UP! with LARRY JONES | **missing** | No audited handle. |
| 5 | Kenan Grace | **missing** | Handle not curated; **uncertain** without manual X profile confirmation. |
| 5 | Everything Money | **EverythingMoney** | `everything money` needle; **verified-style** for this channel label. |
| 5 | Chicken Genius Singapore | **missing** | No audited handle. |
| 4 | Joseph Carlson | **missing** | No audited handle. |
| 4 | Daniel Pronk | **missing** | No audited handle. |
| 3 | Dumb Money Live | **missing** | No audited handle. |
| 3 | The Investor Channel | **missing** | No audited handle. |
| 2 | Sasha Yanshin | **missing** | No audited handle. |
| 2 | Value Investing with Sven Carlin, Ph.D. | **missing** | No audited handle. |
| 2 | Dividendology | **missing** | No audited handle. |
| 2 | Parkev Tatevosian, CFA | **missing** | No audited handle; drove early-run slices when those rows lead the CSV. |
| 1 | The Plain Bagel | **ThePlainBagel** | `plain bagel` needle; **verified-style**. |
| 1 | Tom Nash | **missing** | No audited handle. |
| 1 | HyperChange | **missing** | Single-token channel name; mention-tier safely skipped. |
| 1 | Ticker Symbol: YOU | **missing** | No audited handle. |
| 1 | Meet Kevin | **realMeetKevin** | `meet kevin` needle; **verified-style**. |

**Rows with a mapped X handle (strict `CHANNEL_X`):** **13 / 113** (~11.5%).

## Event windows per mapped creator

Windows are per **clean event row** (each row is one ticker / one `event_date_utc` with ±3 day actor window in the checkpoint design). Approximate row counts from the same export:

| Mapped handle | Approx. clean rows (same export) | Notes |
|---|---:|---|
| GrahamStephan | 6 | Enough for several capped checkpoint pulls. |
| EverythingMoney | 5 | Same. |
| ThePlainBagel | 1 | Single row in this export; more rows may exist in `all_clean_events.csv`. |
| realMeetKevin | 1 | Thin in this slice. |
| StockMoe, unusual_whales, KobeissiLetter, zerohedge | 0 in validation CSV | Needles exist for **future** rows if those channels appear in event sources. |

## Which creators drove checkpoint 1 (RunPod)

Per `30_x_native_creator_checkpoint_1_audit.md`, the live batch used **`clean_auto_labeled_events.csv`** (because `all_clean_events.csv` was absent on the pod). The audit states the **first eight processed rows** were **Parkev Tatevosian, CFA** events with **no** `CHANNEL_X` mapping, so **all eight** runs were **`ticker-only-control`**.

**Local file-order note:** In the current committed `clean_auto_labeled_events.csv`, the **first** rows are not Parkev-heavy; ordering can differ if the export was regenerated or if another branch CSV was present on RunPod. The **mechanism** is unchanged: **no mapping ⇒ ticker-only**, and **unmapped-leading file order ⇒ zero authored rows**.

**Driver fix (this commit):** the checkpoint script now **sorts** eligible rows so mapped creators are scheduled first, adds **mention** and **audited panel** tiers before ticker-only, passes **per-event `date_start` / `date_end`** into `run_single_x_apify_source`, and **drops** the `wsb` → `TheRoaringKitty` substring map (weak / non-attributable to YouTube channel titles).

## Why `x-creator-authored` rows were zero

1. **Mapping coverage:** `CHANNEL_X` only encodes a handful of substring needles; dominant validation creators (Jose Najarro, Learn to Invest, Mark Roussin, Financial Education, etc.) do not match.  
2. **No fallback before ticker:** Prior behavior used **`${TICKER}`** immediately when unmapped, so **no** `from:` clause.  
3. **Selection order:** The driver walked events sequentially until `max_rows`; an unmapped block at the head of the list consumed the entire budget of runs.

## Exact changes before additional spend

1. **Deploy updated checkpoint script** that (a) **sorts** valid events so **mapped creators run first**, (b) applies **query priority**: mapped **`from:handle $TICKER`**, then optional **quoted display-name mention** (conservative, disable via env if needed), then **rotating audited X-native panel** `from:panel_handle $TICKER`, then **`$TICKER` control**.  
2. **Pass per-event `date_start` / `date_end`** into `run_single_x_apify_source` so Kaito `since_time` / `until_time` match the intended ±3 day window (previously the JSON logged window while the actor input used module-wide defaults).  
3. **Curate handles** for top unmapped YouTube names only after **manual** X profile verification; add needles + canonical casing to `CHANNEL_X` **and** document them in this audit as **verified**.  
4. **Sync `data/exports/research_expansion/all_clean_events.csv` to RunPod** when that file is the canonical event ordering for research expansion.  
5. **Do not** add guessed handles for “Financial Education”, “Kenan Grace”, “Parkev Tatevosian”, etc., without evidence — keep **missing / uncertain** in this audit.

## PASS / PARTIAL PASS / FAIL — creator mapping readiness

**Verdict: PARTIAL PASS**

- **PASS elements:** Deterministic needles exist for a **small** set of high-signal finance creators present in the export (Graham Stephan, Everything Money, The Plain Bagel, Meet Kevin).  
- **FAIL elements for full PASS:** **~88%** of validation rows lack a curated handle; top creators by count are **unmapped**; mention-based queries are **diagnostic only** and can collide with unrelated accounts if names are generic.

## Apify re-run policy (this task)

Per project instructions, **no additional Apify checkpoint** was executed from this workspace after completing the audit and code changes. A **tiny** capped run on RunPod is justified **only after** deploying the updated script and confirming a **mapped-first** row slice (or verified new mappings).

## Safety

No secrets, tokens, tweet bodies, or raw Apify payloads are recorded in this audit.
