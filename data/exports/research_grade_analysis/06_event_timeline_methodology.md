# Event Timeline Methodology

## Inputs

- Locked sample of 1,554 accepted YouTube recommendation events
  (`transcript_recommendation_events` joined to `raw_youtube_videos`).
- `published_at` is the YouTube upload timestamp in UTC.
- Evidence offset within the video is taken from
  `transcript_recommendation_events.evidence_start_seconds`.
- Trading calendars are reconstructed from local yfinance market-data CSVs
  (`yfinance_expanded_market_data.csv` and `yfinance_market_data.csv`).

## Definitions

- `calendar_event_date`: UTC calendar date of the YouTube upload timestamp.
- `weekday_adjusted_date`: Saturday -> Monday, Sunday -> Monday, weekday
  preserved. Conservative because actual holiday calendars are not used.
- `effective_trading_event_date`: first available ticker trading day on or after
  `weekday_adjusted_date`. If the ticker has no row on or after that date,
  the field is blank and all window endpoints become blank.
- `transcript_evidence_timestamp`: `published_at + evidence_start_seconds`.
  This is a viewer-sequential timestamp proxy, not a market-release timestamp:
  the whole video can become publicly available at `published_at`, and the
  recording may have occurred before upload. It is retained only to locate the
  evidence span inside the video.
- `timing_bucket`: `before_open`, `during_market`, `after_close`,
  `weekend_or_holiday`, `unknown`. Uses a fixed UTC -> ET offset of -5 hours
  and ignores DST; this is a conservative approximation.
- `lookahead_risk_flag`: `True` for `during_market` or `after_close` events.
  Those events can be uploaded *after* the intraday move, so any same-day
  abnormal return that we attribute to the event window already contains some
  reaction the creator may have been responding to.

## Trading-Day Window Conventions

For each event, with `base_idx` defined as the trading-day index of
`effective_trading_event_date` for that ticker, the seven windows are computed
on trading-day offsets relative to `base_idx`:

| Window | Start offset | End offset | Use |
| --- | --- | --- | --- |
| [-20,-1] | -20 | -1 | Pre-event momentum |
| [-5,-1] | -5 | -1 | Short pre-event momentum |
| [0,+1] | 0 | +1 | Event-day reaction |
| [0,+3] | 0 | +3 | Reaction extension |
| [0,+5] | 0 | +5 | Headline 5D post-event window |
| [+5,+20] | +5 | +20 | Reversal vs continuation horizon |
| [0,+20] | 0 | +20 | Full post-event window |

When intraday timestamps are not granular enough to resolve the recommendation
to a market session (the only timestamp available is the upload time), we adopt
the conservative convention: the next available trading day on or after the
calendar event date is `trading_day_0`. This avoids backdating the
recommendation onto a day whose intraday moves the creator may have observed
before uploading. Events uploaded `before_open` therefore share the same
trading day index as events uploaded `during_market` or `after_close` on the
same calendar day, but the `lookahead_risk_flag` lets downstream consumers
isolate `before_open` events for cleanest inference.

## Duplicate Clustering

A cluster is identified by `(creator, ticker, weekday_adjusted_date)`.
`duplicate_cluster_id` is a deterministic integer (insertion order),
`duplicate_cluster_size` counts how many events share that key. Robust
inference should collapse clusters with `size >= 2` to a single observation or
cluster the standard errors on this key (see
`13_statistical_robustness_matrix.md`).

## Known Limitations

- Holiday-aware trading calendars are inferred only through the presence of a
  row in the ticker's market-data file; explicit NYSE/NASDAQ holiday tables
  would improve `effective_trading_event_date` for sparse tickers.
- DST-aware time-zone conversion is not applied; `timing_bucket` is a
  conservative approximation.
- For SQ historic events before 2025-01-21 the data ticker stays `SQ`; for
  events after the ticker change the data ticker is resolved to `XYZ`.
