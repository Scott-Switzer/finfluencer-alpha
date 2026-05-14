# X checkpoint zero-import and normalization diagnostics

Generated for engineering audit (no secrets, no raw tweet bodies).

## Executive summary

- The **2026-05-14** capped smoke run (**255** returned, **0** imported) was **not** a data success: it exposed (1) **candidate truncation** when only the CSV head was considered before sorting, and (2) a **normalization / finance gate** path where items can return from Apify yet never reach `import_normalized_x_posts`.
- **RunPod follow-up (`9c78f0d` / `19c853b`):** candidate selection is **fixed** (e.g. **18** `x-creator-authored` runs in dry-run), but a **0.50 USD** capped paid batch still showed **270 returned / 0 imported** with **zero** `posts_with_cashtags` / `posts_with_created_at` counter movement.
- **Root cause (replay):** Apify dataset rows for those runs were **`type: mock_tweet`** placeholders (e.g. pricing / quota messaging, **`id: -1`**, no parseable tweet timestamps) — **not real X payloads**. Normalization correctly drops them; **field-alias tweaks alone cannot import mocks.** Hold **paid** Apify until datasets contain real tweets (billing / product / quota on the Kaito actor side).
- **No larger X spend** is justified until **dry-run** stays healthy **and** a **dataset replay** shows at least one row that **`normalize_apify_x_post`** can turn into a real post with cashtag + `created_at` in-window.
- **Search-plan dedupe:** identical **`(search_value, window_start, window_end)`** combinations are skipped so capped runs are not wasted on duplicate Apify calls.

## Pipeline reminder (`run_single_x_apify_source`)

1. `normalize_apify_x_post` must return a dict (post id, text, parseable `created_at`, English, etc.). Placeholder **`type: mock_tweet`** rows are rejected early.
2. Only posts passing `_is_usable_finance_post` (explicit tickers / finance vocabulary) are appended to the `normalized` list.
3. `import_normalized_x_posts` runs on that list; strict cashtag seeding can drop recommendation rows even when posts insert.

## Fixture batch (offline)

Synthetic items exercised `diagnose_apify_x_item_quality` / `summarize_apify_checkpoint_items` without Apify:

```json
{
  "items": 9,
  "reject_reason_counts": {
    "missing_text": 2,
    "missing_post_id": 1,
    "missing_created_at": 1,
    "date_parse_failed": 1,
    "non_english": 1,
    "not_finance_usable": 1,
    "normalized_ok": 1,
    "mock_or_placeholder": 1
  },
  "top_level_key_frequency": [
    [
      "id",
      8
    ],
    [
      "lang",
      8
    ],
    [
      "text",
      8
    ],
    [
      "created_at",
      6
    ],
    [
      "type",
      1
    ]
  ]
}
```

## Latest dry-run candidate plan

```json
{
  "dry_run": true,
  "event_source": "csv:data/exports/research_expansion/all_clean_events.csv",
  "total_event_rows_loaded": 2078,
  "discovery_pool_size_effective": 2078,
  "valid_event_rows": 2078,
  "mapped_event_count_in_valid": 168,
  "unmapped_event_count_in_valid": 1910,
  "final_selected_run_count": 18,
  "selected_distinct_creators": [
    "The Plain Bagel",
    "Graham Stephan",
    "Everything Money"
  ],
  "selected_distinct_tickers": [
    "AMC",
    "DIS",
    "AMZN",
    "GOOGL",
    "MSFT",
    "NVDA",
    "NFLX",
    "AMD",
    "TSLA",
    "UBER"
  ],
  "query_type_counts": {
    "x-creator-authored": 18
  },
  "x_creator_authored_candidates_in_valid_pool": 168,
  "x_creator_authored_in_selected_runs": 18,
  "top_20_selected_candidates": [
    {
      "event_id": "2001",
      "youtube_creator": "The Plain Bagel",
      "youtube_video_id": "ilwk1Dm7Yzg",
      "ticker": "TSLA",
      "event_date_utc": "2020-02-21",
      "window_start": "2020-02-18",
      "window_end": "2020-02-24",
      "since_time": 1581984000,
      "until_time": 1582588799,
      "x_handle_target": "ThePlainBagel",
      "query_type": "x-creator-authored",
      "search_value": "from:ThePlainBagel $TSLA"
    },
    {
      "event_id": "1677",
      "youtube_creator": "The Plain Bagel",
      "youtube_video_id": "AqZbO8Ojhmw",
      "ticker": "AMZN",
      "event_date_utc": "2022-11-04",
      "window_start": "2022-11-01",
      "window_end": "2022-11-07",
      "since_time": 1667260800,
      "until_time": 1667865599,
      "x_handle_target": "ThePlainBagel",
      "query_type": "x-creator-authored",
      "search_value": "from:ThePlainBagel $AMZN"
    },
    {
      "event_id": "1669",
      "youtube_creator": "The Plain Bagel",
      "youtube_video_id": "BL_L4hHBTLc",
      "ticker": "DIS",
      "event_date_utc": "2022-11-18",
      "window_start": "2022-11-15",
      "window_end": "2022-11-21",
      "since_time": 1668470400,
      "until_time": 1669075199,
      "x_handle_target": "ThePlainBagel",
      "query_type": "x-creator-authored",
      "search_value": "from:ThePlainBagel $DIS"
    },
    {
      "event_id": "1",
      "youtube_creator": "The Plain Bagel",
      "youtube_video_id": "wBjBs0VibaY",
      "ticker": "GOOGL",
      "event_date_utc": "2023-10-27",
      "window_start": "2023-10-24",
      "window_end": "2023-10-30",
      "since_time": 1698105600,
      "until_time": 1698710399,
      "x_handle_target": "ThePlainBagel",
      "query_type": "x-creator-authored",
      "search_value": "from:ThePlainBagel $GOOGL"
    },
    {
      "event_id": "1667",
      "youtube_creator": "The Plain Bagel",
      "youtube_video_id": "JooqHEF0kBo",
      "ticker": "AMC",
      "event_date_utc": "2024-05-31",
      "window_start": "2024-05-28",
      "window_end": "2024-06-03",
      "since_time": 1716854400,
      "until_time": 1717459199,
      "x_handle_target": "ThePlainBagel",
      "query_type": "x-creator-authored",
      "search_value": "from:ThePlainBagel $AMC"
    },
    {
      "event_id": "1662",
      "youtube_creator": "The Plain Bagel",
      "youtube_video_id": "nKHzfQd4lOo",
      "ticker": "NVDA",
      "event_date_utc": "2024-12-28",
      "window_start": "2024-12-25",
      "window_end": "2024-12-31",
      "since_time": 1735084800,
      "until_time": 1735689599,
      "x_handle_target": "ThePlainBagel",
      "query_type": "x-creator-authored",
      "search_value": "from:ThePlainBagel $NVDA"
    },
    {
      "event_id": "2031",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "k0rpxeieWDA",
      "ticker": "TSLA",
      "event_date_utc": "2025-02-17",
      "window_start": "2025-02-14",
      "window_end": "2025-02-20",
      "since_time": 1739491200,
      "until_time": 1740095999,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $TSLA"
    },
    {
      "event_id": "2032",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "k0rpxeieWDA",
      "ticker": "NVDA",
      "event_date_utc": "2025-02-17",
      "window_start": "2025-02-14",
      "window_end": "2025-02-20",
      "since_time": 1739491200,
      "until_time": 1740095999,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $NVDA"
    },
    {
      "event_id": "2035",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "w73gVwZQdZU",
      "ticker": "TSLA",
      "event_date_utc": "2025-03-26",
      "window_start": "2025-03-23",
      "window_end": "2025-03-29",
      "since_time": 1742688000,
      "until_time": 1743292799,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $TSLA"
    },
    {
      "event_id": "2023",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "J2ysrIiwgZE",
      "ticker": "AMZN",
      "event_date_utc": "2025-06-02",
      "window_start": "2025-05-30",
      "window_end": "2025-06-05",
      "since_time": 1748563200,
      "until_time": 1749167999,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $AMZN"
    },
    {
      "event_id": "2036",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "O9H33R9D0KA",
      "ticker": "UBER",
      "event_date_utc": "2025-08-14",
      "window_start": "2025-08-11",
      "window_end": "2025-08-17",
      "since_time": 1754870400,
      "until_time": 1755475199,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $UBER"
    },
    {
      "event_id": "1717",
      "youtube_creator": "Graham Stephan",
      "youtube_video_id": "1vMAWsYU0ng",
      "ticker": "TSLA",
      "event_date_utc": "2025-09-01",
      "window_start": "2025-08-29",
      "window_end": "2025-09-04",
      "since_time": 1756425600,
      "until_time": 1757030399,
      "x_handle_target": "GrahamStephan",
      "query_type": "x-creator-authored",
      "search_value": "from:GrahamStephan $TSLA"
    },
    {
      "event_id": "2064",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "dkit-LtWzMM",
      "ticker": "UBER",
      "event_date_utc": "2025-09-25",
      "window_start": "2025-09-22",
      "window_end": "2025-09-28",
      "since_time": 1758499200,
      "until_time": 1759103999,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $UBER"
    },
    {
      "event_id": "2065",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "dkit-LtWzMM",
      "ticker": "GOOGL",
      "event_date_utc": "2025-09-25",
      "window_start": "2025-09-22",
      "window_end": "2025-09-28",
      "since_time": 1758499200,
      "until_time": 1759103999,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $GOOGL"
    },
    {
      "event_id": "1666",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "8ZllCsuVEaM",
      "ticker": "MSFT",
      "event_date_utc": "2025-10-11",
      "window_start": "2025-10-08",
      "window_end": "2025-10-14",
      "since_time": 1759881600,
      "until_time": 1760486399,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $MSFT"
    },
    {
      "event_id": "2044",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "20PT-O46nkc",
      "ticker": "NVDA",
      "event_date_utc": "2025-10-16",
      "window_start": "2025-10-13",
      "window_end": "2025-10-19",
      "since_time": 1760313600,
      "until_time": 1760918399,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $NVDA"
    },
    {
      "event_id": "2045",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "20PT-O46nkc",
      "ticker": "AMD",
      "event_date_utc": "2025-10-16",
      "window_start": "2025-10-13",
      "window_end": "2025-10-19",
      "since_time": 1760313600,
      "until_time": 1760918399,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $AMD"
    },
    {
      "event_id": "2025",
      "youtube_creator": "Everything Money",
      "youtube_video_id": "MLMUxTWU6cg",
      "ticker": "NFLX",
      "event_date_utc": "2025-10-28",
      "window_start": "2025-10-25",
      "window_end": "2025-10-31",
      "since_time": 1761350400,
      "until_time": 1761955199,
      "x_handle_target": "EverythingMoney",
      "query_type": "x-creator-authored",
      "search_value": "from:EverythingMoney $NFLX"
    }
  ],
  "mention_tier_enabled": true,
  "panel_tier_enabled": true,
  "require_mapped_for_pool": false
}
```
