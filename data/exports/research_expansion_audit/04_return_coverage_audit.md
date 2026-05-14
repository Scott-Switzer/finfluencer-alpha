# Market Data and Return Coverage Audit

- 1D valid SPY-adjusted returns: **471**.
- 1W valid SPY-adjusted returns: **465**.
- 1M valid SPY-adjusted returns: **430**.
- 3M valid SPY-adjusted returns: **367**.
- 6M valid SPY-adjusted returns: **277**.
- 1Y valid SPY-adjusted returns: **196**.
- 2Y valid SPY-adjusted returns: **101**.
- END_OF_SAMPLE valid SPY-adjusted returns: **471**.
- PRE_1W valid SPY-adjusted returns: **471**.
- PRE_1M valid SPY-adjusted returns: **471**.
- PRE_3M valid SPY-adjusted returns: **471**.

- Weekend/holiday events are mapped to the next available ticker trading day.
- Return horizons use trading-day offsets, not calendar-day offsets.
- Duplicate price rows are collapsed by ticker/date before return calculation.
- Missing benchmark endpoints leave that benchmark-adjusted return invalid.
