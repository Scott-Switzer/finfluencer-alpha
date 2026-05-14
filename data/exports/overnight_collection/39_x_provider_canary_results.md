# X provider canary results

Started (UTC): `2026-05-14T22:09:13Z`
Dry-run: **True**
Session cap USD: **0.25**
Max items per run: **5**
``X_PROVIDER_CANARY_QUERY_MODE``: **both**
Sanity query enabled: **True**

## Providers

```json
[
  "apidojo_lite",
  "scweet"
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

## Provider `apidojo_lite` (`apidojo/twitter-scraper-lite`) — `strict` / `research_strict`

- Canary query label: `realMeetKevin_TSLA_2021w1`

### Actor input (no secrets)

```json
{
  "searchTerms": [
    "from:realMeetKevin $TSLA since:2021-01-01 until:2021-01-08 lang:en"
  ],
  "sort": "Latest",
  "maxItems": 5,
  "includeSearchTerms": true
}
```

## Provider `apidojo_lite` (`apidojo/twitter-scraper-lite`) — `broad` / `schema_probe_not_research_sample`

- Canary query label: `realMeetKevin_TSLA_2021w1`

### Actor input (no secrets)

```json
{
  "searchTerms": [
    "from:realMeetKevin TSLA since:2021-01-01 until:2021-01-08 lang:en"
  ],
  "sort": "Latest",
  "maxItems": 5,
  "includeSearchTerms": true
}
```

## Provider `scweet` (`altimis/scweet`) — `strict` / `research_strict`

- Canary query label: `GrahamStephan_AAPL_2020w1`

### Actor input (no secrets)

```json
{
  "source_mode": "search",
  "search_query": "from:GrahamStephan $AAPL lang:en",
  "since": "2020-08-01",
  "until": "2020-08-08",
  "max_items": 5
}
```

## Provider `scweet` (`altimis/scweet`) — `broad` / `schema_probe_not_research_sample`

- Canary query label: `GrahamStephan_AAPL_2020w1`

### Actor input (no secrets)

```json
{
  "source_mode": "search",
  "search_query": "from:GrahamStephan AAPL lang:en",
  "since": "2020-08-01",
  "until": "2020-08-08",
  "max_items": 5
}
```

## Provider `apidojo_lite` (`apidojo/twitter-scraper-lite`) — `sanity` / `schema_sanity_control`

- Canary query label: `schema_sanity_control`

### Actor input (no secrets)

```json
{
  "searchTerms": [
    "AAPL since:2021-01-01 until:2021-01-08 lang:en"
  ],
  "sort": "Latest",
  "maxItems": 5,
  "includeSearchTerms": true
}
```

## Overall verdict

**FAIL** (research_strict overnight-eligible PASS: False)
**Classification:** `FAIL`

Broad probes and `schema_sanity_control` runs never satisfy the overnight canary gate, even if numeric rates look strong.
