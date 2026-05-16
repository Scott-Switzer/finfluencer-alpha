# Bloomberg Data Pull Plan (Locked YouTube Sample)

## Request File

- Output CSV: `data/exports/analysis/05_bloomberg_ticker_event_request.csv`
- Required columns: `ticker,event_date,creator,video_id,recommendation_type,event_id,start_date,end_date`
- Date window policy in this request: `start_date = event_date - 60 calendar days`, `end_date = event_date + 30 calendar days`.

## Desired Bloomberg Fields

- Prices/returns: adjusted close, open, high, low, total return fields, split/dividend adjustments.
- Liquidity: volume, turnover, average dollar volume proxies.
- Risk controls: beta, sector, industry, market cap, benchmark index returns.
- Optional controls: short interest, analyst revisions, realized volatility proxies.

## Join Rules

- Join on `(ticker, trading_date)` after applying trading-day alignment from event date.
- Keep original event identifiers (`event_id`, `video_id`, `creator`) to preserve audit trail.
- Preserve recommendation-type slices for subgroup tables in final reporting.
