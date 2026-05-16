# Bloomberg-Day Task List (T+2)

## Goal

In a single Bloomberg session, replace yfinance with Bloomberg in every
headline statistic and populate the news-confound flag.

## Sequence

### Step 1: Pre-flight (15 minutes)

- `git pull` on `x-youtube-full-research-expansion`.
- Confirm `data/exports/analysis/05_bloomberg_ticker_event_request.csv` is
  still the canonical request file (rowcount = 1,554).
- Open Bloomberg Terminal; verify license entitlements for daily history,
  earnings dates, headlines, analyst rec changes, and corporate actions.
- Open `data/exports/research_grade_analysis/18_bloomberg_validation_protocol.md`
  for the field-by-field spec.

### Step 2: Pull market data (60-90 minutes)

For each unique ticker in the request file:

1. Pull `PX_LAST` for event_date -60 to event_date +30 trading days.
2. Pull `TOT_RETURN_INDEX_GROSS_DVDS` (or `DAY_TO_DAY_TOT_RETURN_GROSS_DVDS`)
   for the same window.
3. Pull `PX_VOLUME`, `CUR_MKT_CAP`, `BETA_ADJ_OVERRIDABLE`,
   `GICS_SECTOR_NAME`, `GICS_INDUSTRY_NAME`.

Also pull benchmark series (SPY, QQQ, IWM) and sector ETFs (XLK, XLC, XLY,
XLF, XLI) over the full event-date range minus 60 days through max +30 days.

Save to `data/imports/market_data/bloomberg_market_data.csv` with the same
column schema as `yfinance_market_data.csv` so the existing event-study runner
accepts it.

### Step 3: Pull news / earnings / analyst data (30-60 minutes)

- `EARN_ANN_DT` for two earnings dates straddling each event ->
  `bloomberg_earnings_dates.csv`.
- `CH_LAST` company headlines, event_date +/-5 calendar days ->
  `bloomberg_news_headlines.csv` (headline text + source + timestamp).
- `ANR` analyst rating changes within event_date +/-5 calendar days ->
  `bloomberg_analyst_changes.csv`.
- `EVT_DT_DIV`, `EVT_DT_SPLIT` corporate actions within +/-5 calendar days
  -> `bloomberg_dividends_corporate_actions.csv`.

### Step 4: Fetch French factors (15 minutes, offline)

- Download FF3 daily, FF Momentum daily, FF5 daily ZIPs from
  `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html`.
- Extract to `data/imports/french_factors/` (gitignored).

### Step 5: Re-run analytical pipeline (10 minutes)

```bash
python3 -m finfluencer_alpha validate-market-data --input data/imports/market_data/bloomberg_market_data.csv
python3 -m finfluencer_alpha run-event-study --market-data-source bloomberg
python3 scripts/build_research_grade_analysis.py
```

Expected output: all `data/exports/research_grade_analysis/*.md` files refresh
with Bloomberg numbers only after the market-data input path has been verified
or adapted for the Bloomberg file; `10_news_overlap_flags.csv` switches every
"unknown" to True/False; `news_source_used = bloomberg`.

### Step 6: Populate news flags (45 minutes)

Run a one-off Python script that joins:

- `bloomberg_earnings_dates.csv` -> `earnings_near_event_flag`
- `bloomberg_news_headlines.csv` headline count -> `major_news_near_event_flag`
- `bloomberg_analyst_changes.csv` -> additional flag column
- Tighten same-day / +/-1 / +/-3 / +/-5 windows from these joined tables.

### Step 7: Robustness rerun (30 minutes)

- Rerun `13_statistical_robustness_matrix.md` with Bloomberg series; specifically
  add `news_confounded_excluded` and `pre_trend_test` rows now populated.
- Rerun calendar-time portfolio backtest (`14_portfolio_strategy_backtest_plan.md`)
  and report cost-adjusted Sharpe.
- Rerun calibration (`15_probability_and_calibration_plan.md`) with posterior
  intervals.

### Step 8: Sanity checks (30 minutes)

- Compare top-3 events by Bloomberg AR_0_5 to top-3 by yfinance AR_0_5. If
  any event flipped sign, investigate the ticker's adjusted close on
  event_date.
- Verify pre-trend test mean is within +/- 0.5 standard errors of 0.
- Verify news_confounded_event_flag covers at least 15% of events
  (otherwise the flagger is likely too restrictive).

### Step 9: Reporting (30 minutes)

- Update `19_linkedin_and_research_positioning_memo.md` to move
  "Provisional" items to "Robust" where applicable.
- Update `06_preliminary_findings_memo.md` headline numbers.
- Do **not** commit Bloomberg raw CSVs. Only commit refreshed
  `data/exports/research_grade_analysis/*.md` outputs.

## Total Expected Wall-Clock

- 4-5 hours hands-on for a single operator including pulls, reruns, and
  reporting.

## Hard No-Go Conditions

- If `bloomberg_market_data.csv` has > 5% missing rows vs the request, halt
  and document missing-ticker rationale before rerunning the event study.
- If 5D AR sign flips on the headline (positive -> negative) after Bloomberg,
  flag for project-meeting discussion before publishing.
- If news_confounded_event_flag covers > 60% of events, the news lexicon
  is too loose; tune before rerunning robustness cuts.
