# FNSPID processing audit

## A. Event / date coverage
| metric | value |
| --- | --- |
| events_before_2024 | 482 |
| events_2024_2026 | 1855 |
| share_outside_expected_fnspid_era | 79.4% |

| year | events | unknown_news_coverage | fnspid_hits | fnspid_misses |
| --- | --- | --- | --- | --- |
| 2020 | 18 | 1 | 9 | 9 |
| 2021 | 28 | 12 | 0 | 28 |
| 2022 | 91 | 16 | 55 | 36 |
| 2023 | 345 | 40 | 276 | 69 |
| 2024 | 589 | 150 | 0 | 589 |
| 2025 | 707 | 292 | 0 | 707 |
| 2026 | 559 | 195 | 0 | 559 |

## D. Window sensitivity (from compact spine)
| window | days_each_side | events_hit_primary | events_hit_secondary | events_hit_either | events_hit_both | n_events |
| --- | --- | --- | --- | --- | --- | --- |
| pm1 | 1 | 331 | 0 | 331 | 0 | 2337 |
| pm3 | 3 | 335 | 0 | 335 | 0 | 2337 |
| pm7 | 7 | 340 | 0 | 340 | 0 | 2337 |
| pm14 | 14 | 340 | 0 | 340 | 0 | 2337 |
| pm30 | 30 | 340 | 0 | 340 | 0 | 2337 |
| pm60 | 60 | 340 | 0 | 340 | 0 | 2337 |

## B. Ticker overlap
| metric | value |
| --- | --- |
| unique_event_tickers | 25 |
| unique_tickers_in_primary_csv | (use --scan-primary to refresh) |
| unique_tickers_in_secondary_csv | 6619 |
| event_tickers_in_primary | 0 |
| event_tickers_in_secondary | 4 |
| event_tickers_absent_both | 21 |

## E. Secondary dedupe
| metric | value |
| --- | --- |
| window_match_rows | 644 |
| new_keys_vs_primary | 0 |
| dup_keys_vs_primary | 644 |
| no_window_match | 0 |
| sym_in_universe_no_window | 20070 |
| interpretation | dup_keys_vs_primary>0 with new_keys≈0 implies All_external overlap deduped by primary keys |

## Verdict
- If `events_hit_secondary` stays 0 across windows on the spine, secondary never contributed articles to stored hits.
- If dedupe shows large `dup_keys_vs_primary` with ~0 `new_keys_vs_primary`, All_external rows overlap primary content and were correctly deduped.
- Events in 2024+ cannot receive FNSPID hits by construction if article max date ends ~2023.
- **unknown_news_coverage is never clean**; **multi_source_clean** may remain 0.

