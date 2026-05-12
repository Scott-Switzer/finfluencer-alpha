# Bloomberg Replacement Checklist

## 1) Which file Bloomberg should replace

- Replace: `data/imports/market_data/yfinance_market_data.csv`
- Preferred Bloomberg import target path:
  - `data/imports/market_data/bloomberg_market_data.csv`

Keep the yfinance file for prototype comparison, but run event study using the Bloomberg file as input.

## 2) Required columns in Bloomberg CSV

Use the same schema expected by the event-study importer:

- `ticker`
- `date` (YYYY-MM-DD)
- `adjusted_close`
- `volume`
- `benchmark_ticker` (SPY or chosen benchmark)
- `benchmark_adjusted_close`
- `market_cap`
- `sector`
- `industry`
- `beta`
- `average_dollar_volume`
- `data_source`
- `downloaded_at_utc`

Notes:

- If available, include `original_ticker` as an additional column for alias/audit continuity.
- Ensure unique `ticker` + `date` rows and no malformed dates.

## 3) Where to save Bloomberg CSV

- Save to: `data/imports/market_data/bloomberg_market_data.csv`
- Do not overwrite raw yfinance prototype unless you intentionally want a single-file workflow.

## 4) Commands to rerun after Bloomberg replacement

1. Validate import
   - `python3 -m finfluencer_alpha validate-market-data-import --input data/imports/market_data/bloomberg_market_data.csv`
2. Rerun event study on Bloomberg
   - `python3 -m finfluencer_alpha run-event-study --input-market-data data/imports/market_data/bloomberg_market_data.csv`
3. Regenerate diagnostics
   - `python3 -m finfluencer_alpha diagnose-event-study-matches --input-market-data data/imports/market_data/bloomberg_market_data.csv`
4. Rebuild reporting tables
   - `python3 -m finfluencer_alpha build-event-study-reporting --input-market-data data/imports/market_data/bloomberg_market_data.csv`
5. Rebuild charts
   - `python3 -m finfluencer_alpha build-event-study-charts --input-market-data data/imports/market_data/bloomberg_market_data.csv`

## 5) What outputs to compare before vs after Bloomberg

Compare these side-by-side between prototype and Bloomberg runs:

- Match diagnostics:
  - `data/exports/event_study/event_study_match_diagnostics.csv`
  - Focus on unmatched count and reasons
- Main table:
  - `data/exports/reporting/event_study_main_table.csv`
  - Focus on mean/median abnormal returns, CARs, and t-stats
- Grouped tables:
  - by creator/ticker/year/type/direction
  - Check sign/magnitude changes and concentration effects
- Charts:
  - return/CAR distributions and by-window mean chart
  - Verify whether medium-run negative pattern persists

Final rule:

- Use Bloomberg-based outputs as the final inference set.
- Keep yfinance outputs clearly labeled as prototype for reproducibility/audit.
