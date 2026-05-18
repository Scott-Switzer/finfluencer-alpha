# FNSPID News Layer Summary

## Access

- **Mode**: Hugging Face Dataset Server **probe** (`/is-valid`, `/splits`, `/first-rows`) plus **stream-filter** of Hub CSV (no full raw file committed).
- **Server capabilities** (from `/is-valid): preview=True, viewer=False, filter=False, search=False.
- **Note**: Zihan1004/FNSPID currently has **filter/viewer/search disabled** and `/rows` may error on conversion; substantive coverage requires **CSV streaming**, not paginated API slices.
- **Primary CSV**: `nasdaq_exteral_data.csv`
- **Rows scanned (streaming)**: 15,549,299
- **Chunks**: 155
- **Stream status**: success

## API canary (first 100 preview rows)

```json
{
"canary_tickers_seen_in_first_preview": {},
"preview_row_count": 100
}
```

## Results

- **Events checked**: 2341
- **FN-SPID article hits (±7d window, deduped)**: 340
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
