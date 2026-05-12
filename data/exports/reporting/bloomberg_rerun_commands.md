# Bloomberg Rerun Commands

## Where to save Bloomberg file

Save the Bloomberg-formatted market data CSV to:

`data/imports/market_data/bloomberg_market_data.csv`

Keep the yfinance prototype file for comparison, but use the Bloomberg file as the event-study input.

## Exact rerun command sequence

1. Validate Bloomberg import

```bash
python3 -m finfluencer_alpha validate-market-data-import --input data/imports/market_data/bloomberg_market_data.csv
```

2. Rerun event study on Bloomberg

```bash
python3 -m finfluencer_alpha run-event-study --input-market-data data/imports/market_data/bloomberg_market_data.csv
```

3. Regenerate match diagnostics using Bloomberg input

```bash
python3 -m finfluencer_alpha diagnose-event-study-matches --input-market-data data/imports/market_data/bloomberg_market_data.csv
```

4. Rebuild reporting tables using Bloomberg input

```bash
python3 -m finfluencer_alpha build-event-study-reporting --input-market-data data/imports/market_data/bloomberg_market_data.csv
```

5. Rebuild charts using Bloomberg input

```bash
python3 -m finfluencer_alpha build-event-study-charts --input-market-data data/imports/market_data/bloomberg_market_data.csv
```

## Files to compare before vs after Bloomberg

Compare these outputs against the current yfinance-prototype versions:

- `data/exports/event_study/event_study_results.csv`
- `data/exports/event_study/event_study_match_diagnostics.csv`
- `data/exports/reporting/event_study_main_table.csv`
- `data/exports/reporting/event_study_by_creator.csv`
- `data/exports/reporting/event_study_by_ticker.csv`
- `data/exports/reporting/event_study_by_year.csv`
- `data/exports/reporting/event_study_by_recommendation_type.csv`
- `data/exports/reporting/event_study_by_direction.csv`
- `data/exports/reporting/event_study_robustness_thresholds.csv`
- `data/exports/reporting/charts/mean_abnormal_return_by_window.png`
- `data/exports/reporting/charts/abnormal_return_20d_distribution.png`
- `data/exports/reporting/charts/car_20d_distribution.png`

## What to check in comparison

- Match coverage and unmatched reasons
- Sign and magnitude of 1D/5D/20D abnormal returns and CARs
- T-stat and p-value changes (especially 20D metrics)
- Whether subgroup patterns (creator/ticker/year/type/direction) materially shift
- Whether core narrative (short-run mild positive, medium-run negative) persists or changes
