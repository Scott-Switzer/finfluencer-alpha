# X provider canary results

Started (UTC): `2026-05-14T21:47:00Z`
Dry-run: **False**
Session cap USD: **0.25**
Max items per run: **5**

## Providers

```json
[
  "xquik",
  "scrapebadger",
  "apidojo_v2"
]
```

## Canary queries (audited CHANNEL_X handles)

```json
[
  {
    "label": "realMeetKevin_TSLA_2021w1",
    "ticker": "TSLA",
    "since": "2021-01-01",
    "until": "2021-01-08",
    "handle_audit": "CHANNEL_X: meet kevin -> realMeetKevin"
  },
  {
    "label": "GrahamStephan_AAPL_2020w1",
    "ticker": "AAPL",
    "since": "2020-08-01",
    "until": "2020-08-08",
    "handle_audit": "CHANNEL_X: graham -> GrahamStephan"
  },
  {
    "label": "StockMoe_NIO_2021w1",
    "ticker": "NIO",
    "since": "2021-02-01",
    "until": "2021-02-08",
    "handle_audit": "CHANNEL_X: stock moe -> StockMoe"
  },
  {
    "label": "ThePlainBagel_PYPL_2022w1",
    "ticker": "PYPL",
    "since": "2022-02-01",
    "until": "2022-02-08",
    "handle_audit": "CHANNEL_X: plain bagel -> ThePlainBagel"
  }
]
```

## Provider `xquik` (`xquik/x-tweet-scraper`)

- Canary query label: `realMeetKevin_TSLA_2021w1`

### Actor input (no secrets)

```json
{
  "searchQueries": [
    "from:realMeetKevin $TSLA since:2021-01-01 until:2021-01-08 lang:en"
  ],
  "maxItems": 5,
  "lang": "en"
}
```

### Metrics (aggregated; no raw tweet text)

```json
{
  "returned_rows": 1,
  "mock_rows": 0,
  "non_mock_rows": 1,
  "normalizable_rows": 0,
  "real_id_rows": 0,
  "created_at_parse_rows": 1,
  "explicit_cashtag_rows": 0,
  "inside_window_rows": 1,
  "importable_rows": 0,
  "same_day_today_collapse": true,
  "mock_dominance": false
}
```

- **PASS gate:** `FAIL` (suspect_same_utc_today_collapse)

## Provider `scrapebadger` (`scrape.badger/twitter-tweets-scraper`)

- Canary query label: `GrahamStephan_AAPL_2020w1`

### Actor input (no secrets)

```json
{
  "query": "from:GrahamStephan $AAPL since:2020-08-01 until:2020-08-08 lang:en",
  "maxItems": 5,
  "startDate": "2020-08-01",
  "endDate": "2020-08-08",
  "lang": "en"
}
```

### Metrics (aggregated; no raw tweet text)

```json
{
  "returned_rows": 0,
  "mock_rows": 0,
  "non_mock_rows": 0,
  "normalizable_rows": 0,
  "real_id_rows": 0,
  "created_at_parse_rows": 0,
  "explicit_cashtag_rows": 0,
  "inside_window_rows": 0,
  "importable_rows": 0,
  "same_day_today_collapse": false,
  "mock_dominance": false
}
```

- **PASS gate:** `FAIL` (no_returned_rows)

## Provider `apidojo_v2` (`apidojo/tweet-scraper`)

- Canary query label: `StockMoe_NIO_2021w1`

### Actor input (no secrets)

```json
{
  "searchTerms": [
    "from:StockMoe $NIO since:2021-02-01 until:2021-02-08 lang:en"
  ],
  "maxItems": 5,
  "sort": "Latest",
  "tweetLanguage": "en",
  "start": "2021-02-01",
  "end": "2021-02-08"
}
```

### Metrics (aggregated; no raw tweet text)

```json
{
  "returned_rows": 2,
  "mock_rows": 0,
  "non_mock_rows": 2,
  "normalizable_rows": 0,
  "real_id_rows": 0,
  "created_at_parse_rows": 0,
  "explicit_cashtag_rows": 0,
  "inside_window_rows": 0,
  "importable_rows": 0,
  "same_day_today_collapse": false,
  "mock_dominance": false
}
```

- **PASS gate:** `FAIL` (real_id_rate_below_threshold)

## Overall verdict

**FAIL** (at least one provider PASS: False)
