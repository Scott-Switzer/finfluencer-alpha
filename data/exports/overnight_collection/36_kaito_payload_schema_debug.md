# Kaito / Apify dataset payload schema debug

Generated for **FIN496CAPSTONE** X checkpoint investigation (no Apify Actor starts in this document, no secrets, no full tweet bodies).

## Runs / datasets inspected (smoke replay)

| Kind | Value |
|------|--------|
| Example Apify `run_id` (successful smoke) | `5Xu4Ewz3PUUXHLoWe` |
| Resolved `defaultDatasetId` (same run, Apify API) | `YMMkeF7w3fiV1Lj4S` |

Additional run IDs can be passed to `scripts/debug_kaito_dataset_schema.py` via `--run-id` or `KAITO_DEBUG_RUN_IDS`.

## Sample row shape (first items via `GET /v2/actor-runs/{runId}/dataset/items`)

- **Top-level keys observed:** `type`, `id`, `text` (and occasionally empty-looking extensions — still placeholder-class rows).
- **`type` value:** consistently **`mock_tweet`** in the inspected smoke sample.
- **`id`:** numeric **`-1`** (not a real status id).
- **`text`:** short marketing / pricing / quota style message (not user-generated finance content); **length** on the order of **10²** characters, not a full tweet payload.
- **`created_at` / nested tweet objects:** **absent** in these rows — so **`normalize_apify_x_post`** returns **`None`** (required `created_at` missing after field resolution).

## `diagnose_apify_x_item_quality` outcome

- **`reject_reason`:** **`mock_or_placeholder`** for each inspected row.
- **`normalize_apify_x_post`:** **0** successes on the same sample (by design: mocks rejected early).

## Interpretation (why **270** returned, **0** imported)

1. **Candidate selection is fixed** — dry-run showed non-zero **`x-creator-authored`** selected runs.
2. The **paid smoke was not a data success**: Apify reported **SUCCEEDED** and **non-empty** datasets, but **row content was KaitoEasyAPI-style placeholder data**, not real tweets.
3. **This was primarily a schema / product issue (`mock_tweet`), not a missing text-field alias** on genuine tweet JSON. Expanding `_nested` paths helps **real** payloads but **cannot** manufacture tweet ids or timestamps from mocks.
4. **`posts_with_cashtags` / `posts_with_created_at` stayed at 0** in the checkpoint counters because **no row ever became a normalized post** — counters are computed only after **`normalize_apify_x_post`** returns a dict.

## Code changes tied to this audit

- **`normalize_apify_x_post`** rejects **`type == mock_tweet`** early (documented).
- **`run_single_x_apify_source`** sets run **`notes`** to **`all_dataset_rows_mock_tweet_kaito_placeholder`** when **every** fetched row is a **`mock_tweet`**, to make ledger / SQLite review obvious without saving raw JSON.

## Research verdict

- **FAIL** as a paid data collection outcome (zero importable posts).
- **More X / Kaito Apify spend is not justified** until a **dataset replay** shows at least one **non-mock** row with a real tweet id, parseable timestamp, and query-relevant text (then re-check cashtag + window rules).

## Next step (operational)

- On Apify / Kaito: confirm **billing**, **quota**, and **actor configuration** so pay-per-result charges return **real** `tweet`-shaped items (or official actor docs for required input flags). Re-run **`scripts/debug_kaito_dataset_schema.py`** after any change; only then consider a **≤ 0.25 USD** capped smoke.
