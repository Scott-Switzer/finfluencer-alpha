# FNSPID News Layer Summary

## Access

- **Mode**: Hugging Face Dataset Server **probe** (`/is-valid`, `/splits`, `/first-rows`) plus **stream-filter** of Hub CSV (no full raw file committed).
- **Server capabilities** (from `/is-valid): preview=True, viewer=False, filter=False, search=False.
- **Note**: Zihan1004/FNSPID currently has **filter/viewer/search disabled** and `/rows` may error on conversion; substantive coverage requires **CSV streaming**, not paginated API slices.
- **Primary CSV**: `nasdaq_exteral_data.csv`
- **Primary rows read (this run or spine reuse metadata)**: 15,549,299
- **Secondary rows read (All_external.csv)**: 13,057,514
- **Reuse primary spine**: False
- **Chunks**: 285
- **Stream status**: success

## Rows + source mix

See `fnspid_source_comparison.csv` for primary vs secondary row counts, hit overlap, and **news_clean_status** baselines captured before this run.

## API canary (first 100 preview rows)

```json
{
"canary_tickers_seen_in_first_preview": {},
"preview_row_count": 100
}
```

## Results

- **Events checked**: 2341
- **FN-SPID events with ≥1 article (±7d, cross-file deduped)**: 340
- **Hits primary-only / secondary-only / both**: 340 / 0 / 0
- **Tickers with ≥1 hit**: 10

## Year table

| year | events | events_with_fnspid_hit |
| --- | --- | --- |
| 2020 | 20 | 9 |
| 2021 | 29 | 0 |
| 2022 | 91 | 55 |
| 2023 | 345 | 276 |
| 2024 | 590 | 0 |
| 2025 | 707 | 0 |
| 2026 | 559 | 0 |

## Panel baselines (before this run)

- unknown_news_coverage: **710**
- media_confounded: **419**
- multi_source_clean: **0**

`unknown_news_coverage_after`, `media_confounded_after`, and `multi_source_clean_after` refresh when `build_v2_public_news_confound_master_layer.py` completes (see appended section in this file).
## After news master rebuild (panel)

- unknown_news_coverage: **710**
- media_confounded: **419**
- multi_source_clean: **0**

