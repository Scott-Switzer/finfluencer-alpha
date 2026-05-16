# Bloomberg Validation Protocol

## Scope

This protocol is the spec for the Bloomberg-day run scheduled in roughly two
days. It does *not* execute any Bloomberg call; it is the operating manual.

## Required Bloomberg Fields per Ticker

| Field | Purpose | Window |
| --- | --- | --- |
| `PX_LAST` | Closing price for return calc | event_date -60 to event_date +30 trading days |
| Adjusted close / total return equivalent (`TOT_RETURN_INDEX_GROSS_DVDS` or `DAY_TO_DAY_TOT_RETURN_GROSS_DVDS`) | Dividend-adjusted return | Same as above |
| `PX_VOLUME` | Liquidity sanity | Same |
| `CUR_MKT_CAP` | Size control | Snapshot at event_date |
| `BETA_ADJ_OVERRIDABLE` (or `BETA_RAW`) | CAPM regression | Snapshot at event_date |
| `GICS_SECTOR_NAME`, `GICS_INDUSTRY_NAME` | Industry adjustment | Snapshot |
| `EARN_ANN_DT` (next two earnings dates around event) | Earnings flag | event_date +/-5 calendar/trading days |
| `CH_LAST` company news headlines | News confound flag | event_date +/-5 calendar/trading days |
| `ANR` analyst recommendation changes | News confound flag | event_date +/-5 calendar/trading days |
| Corporate actions: `EVT_DT_DIV`, `EVT_DT_SPLIT`, `BDP("BD_SPECIAL_DIVIDEND_AMT")` | Dividend/split confound | event_date +/-5 calendar/trading days |
| Benchmark index returns: `SPY`, `QQQ`, `IWM` `PX_LAST` | Market-adjusted return | event_date -60 to event_date +30 trading days |
| Sector ETF returns: `XLK`, `XLC`, `XLY`, `XLF`, `XLI` `PX_LAST` | Industry-adjusted return | Same |

## Window Conventions

- Pre-event panel: event_date -60 trading days through event_date -1 trading
  day. Used for CAPM beta re-estimation, momentum control, and pre-trend test.
- Post-event panel: event_date through event_date +30 trading days. Used for
  AR_0_1, AR_0_5, AR_0_20, AR_5_20 recomputation.
- News search: event_date +/-5 calendar/trading days (whichever is wider). For
  flag computation use trading days; for human review use calendar days.

## Input File

- `data/exports/analysis/05_bloomberg_ticker_event_request.csv` (already
  generated in this branch with 1,554 rows; one row per event_id).

## Output Files (Bloomberg-Day Targets)

| File | Purpose |
| --- | --- |
| `data/imports/market_data/bloomberg_market_data.csv` | Replacement for yfinance import; same schema |
| `data/imports/market_data/bloomberg_dividends_corporate_actions.csv` | Dividend/split flags |
| `data/imports/market_data/bloomberg_earnings_dates.csv` | Earnings calendar |
| `data/imports/market_data/bloomberg_news_headlines.csv` | Headlines for news_overlap flagging |
| `data/imports/market_data/bloomberg_analyst_changes.csv` | Analyst rec changes |
| `data/imports/market_data/bloomberg_factor_returns.csv` (optional) | If Bloomberg-equivalent FF factors purchased |

These files are listed in `.gitignore` patterns and **must not be committed**.

## Reruns Triggered by Bloomberg Data

- `04_yfinance_event_study_results.md` -> `04_bloomberg_event_study_results.md`
  (replace numbers, leave methodology in place).
- `07_momentum_decomposition_analysis.md`: rerun all five models; report delta
  in coefficients vs yfinance baseline.
- `08_momentum_decomposition_results.csv`: rerun with Bloomberg total-return
  series; columns unchanged.
- `10_news_overlap_flags.csv`: populate every "unknown" with True/False;
  update `news_source_used` to "bloomberg".
- `11_news_overlap_summary.md`: report confound rate and confounded-excluded
  headline.
- `13_statistical_robustness_matrix.md`: rerun every cut; report Bloomberg
  vs yfinance delta in a final column.
- `14_portfolio_strategy_backtest_plan.md`: replace provisional headline
  table with Bloomberg-driven calendar-time portfolio backtest.
- `15_probability_and_calibration_plan.md`: replace Wilson intervals with
  posterior intervals; recompute calibration.

## Compliance

- Bloomberg raw exports must not be committed to git (`.gitignore` enforces
  this via `data/imports/`).
- Only derived, aggregated, anonymized statistics may be shipped in
  `data/exports/`.
- The Bloomberg license requires that any reported figures cite Bloomberg as
  the data source; this is enforced in the Bloomberg-day rerun of every
  `.md` output.

## Operator Checklist (Day-Of)

1. Confirm `05_bloomberg_ticker_event_request.csv` rowcount = 1,554.
2. Open Bloomberg Terminal, run BQuant or Excel API for each field x ticker x
   window combination.
3. Export to the `data/imports/market_data/bloomberg_*.csv` files.
4. Run the validation step (`python3 -m finfluencer_alpha validate-market-data
   --input data/imports/market_data/bloomberg_market_data.csv`).
5. Run `python3 -m finfluencer_alpha run-event-study --market-data-source bloomberg`.
6. Rerun `scripts/build_research_grade_analysis.py` after either adapting
   `bloomberg_market_data.csv` to the yfinance-compatible schema read by this
   script or adding an explicit Bloomberg source selector. Do not report
   Bloomberg-based results until the script input path is verified in code.
