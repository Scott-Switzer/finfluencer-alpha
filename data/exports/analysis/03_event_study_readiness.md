# Event Study Readiness (Locked YouTube Sample)

- Locked accepted recommendation events: `1554`
- Market data source used for readiness estimation: `/Users/scottthomasswitzer/Desktop/FIN496CAPSTONE/data/imports/market_data/yfinance_market_data.csv`

## Trading-Day Adjustment Approach

- Start from event date derived from video `published_at`.
- Apply weekday adjustment for weekends (Saturday->Monday, Sunday->Monday).
- For market matching, anchor on the first available ticker trading day on or after the adjusted event date.
- Calendar windows are then evaluated in trading-day index space.

## Estimated Usable Sample by Window

- [0,+1]: `1516` (97.55% of locked events)
- [0,+3]: `1511` (97.23% of locked events)
- [0,+5]: `1503` (96.72% of locked events)
- [0,+20]: `1407` (90.54% of locked events)
- [+5,+20]: `1407` (90.54% of locked events)
- [-20,-1]: `1516` (97.55% of locked events)

## Coverage and Clustering Diagnostics

- Missing event dates: `0`
- Events with no ticker data: `38`
- Events with no trading day on/after event date: `0`
- Ticker-date groups with >1 event: `284`
- Events in clustered ticker-date groups: `818`

See `03_event_study_readiness.csv` for full window and problem-ticker breakdowns.
