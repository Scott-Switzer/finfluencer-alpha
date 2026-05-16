# Timing and Lookahead Methodology

The event timestamp is the YouTube upload timestamp, not a tradeable release
timestamp. `before_open` and `weekend_or_holiday` observations are treated as
lower lookahead risk because the next available trading day is less likely to
contain price moves known before upload. `during_market` and `after_close`
observations are retained but flagged because same-day event-study windows can
include price movement that already occurred before the video was public.

Time buckets use the same fixed UTC-to-Eastern approximation documented in the
research-grade package. This is a defensible filter, not exact intraday causal
identification.
