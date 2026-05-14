# X provider canary results

Started (UTC): `2026-05-14T21:39:36Z`
Dry-run: **True**
Session cap USD: **0.25**
Max items per run: **5**

## Providers

```json
[
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

## Provider `apidojo_v2` (`apidojo/tweet-scraper`)

- Canary query label: `realMeetKevin_TSLA_2021w1`

### Actor input (no secrets)

```json
{
  "searchTerms": [
    "from:realMeetKevin $TSLA since:2021-01-01 until:2021-01-08 lang:en"
  ],
  "maxItems": 5,
  "sort": "Latest",
  "tweetLanguage": "en",
  "start": "2021-01-01",
  "end": "2021-01-08"
}
```

## Overall verdict

**FAIL** (at least one provider PASS: False)
