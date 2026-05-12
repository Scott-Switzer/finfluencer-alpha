# Plain-English Results Walkthrough (FIN 496 Prototype)

## What each major file is for

- `data/exports/validation/clean_auto_labeled_events.csv`: the strict cleaned event sample used for event-study inputs (132 events).
- `data/imports/market_data/yfinance_market_data.csv`: interim prototype market data (yfinance/Yahoo), with benchmark-adjusted fields against SPY.
- `data/exports/event_study/event_study_results.csv`: event-level matched return outputs from the prototype event study.
- `data/exports/event_study/event_study_match_diagnostics.csv`: event-by-event match audit that explains why any clean event did not match.
- `data/exports/reporting/event_study_main_table.csv`: one-row summary of core return/CAR metrics and t-tests.
- `data/exports/reporting/event_study_by_*.csv`: grouped breakdowns (creator, ticker, year, recommendation type, direction).
- `data/exports/reporting/event_study_robustness_thresholds.csv`: threshold sensitivity context from earlier filtering stage.
- `data/exports/reporting/charts/*.png`: visual summaries of distributions/composition.
- `data/exports/reporting/methodology_note_yfinance_prototype.md`: concise caveat note for paper/report use.

## Pipeline in plain English

1. Video transcript evidence and metadata were used to identify recommendation-like events.
2. Rules-based filtering produced the clean sample used for returns analysis.
3. Market data was joined to each clean event date/ticker using interim yfinance prototype data.
4. Event returns and benchmark-adjusted abnormal returns were computed for 1D/5D/20D windows.
5. Reporting aggregated those results and produced grouped tables/charts.

## How many records made it through each stage

From the current outputs:

- Clean event sample: **132 events** (`clean_auto_labeled_events.csv`).
- Event-study processed: **132** events (`event_study_summary.md`).
- Event-study matched: **131** events (`event_study_summary.md`, `event_study_main_table.csv`).
- Unmatched: **1** event (`event_study_match_diagnostics.csv`).

Why 132 clean events are used:

- In `event_study_robustness_thresholds.csv`, the strict rule-based row at `min_confidence=0.75` has `included_strict_count=132`.
- This aligns with the clean file and is the strict sample carried into event study.

## Why 131 matched (and the unmatched event)

- Diagnostics report: `matched_events=131`, `unmatched_events=1`.
- Unmatched event is:
  - `event_id=420`
  - `ticker=SQ`
  - `data_ticker=SQ`
  - `creator=Chicken Genius Singapore`
  - `published_at=2020-12-07T14:00:11Z`
  - `missing_market_data_reason=no ticker data`

Interpretation:

- The one unmatched row does **not** invalidate the sample; match rate is `131/132 = 99.24%`.
- The issue appears to be missing market coverage for that specific old `SQ` event date under current mapping/data, not a broad pipeline failure.

## What yfinance means here (and why Bloomberg still matters)

- Current market data is **prototype-only** (yfinance/Yahoo), useful for method testing and interim directional signals.
- It is **not Bloomberg-grade** for final thesis claims.
- Safe statement: "This is an interim prototype estimate pending Bloomberg replacement."
- Unsafe statement: "These are final production-quality market-inference results."

## What SQ -> XYZ means and why aliasing was needed

- Block changed ticker from `SQ` to `XYZ`; alias mapping exists so modern market-data pulls can resolve to current ticker where needed.
- Reporting confirms alias mappings are present in fetch summary.
- This protects join logic from ticker renames while preserving original event ticker for auditability.

## Key concepts in plain English

- **Abnormal return**: stock return minus benchmark (SPY) return over the same window.
- **CAR (Cumulative Abnormal Return)**: sum of daily abnormal returns across the window.
- **1D / 5D / 20D windows**:
  - 1D: immediate next-trading-day effect.
  - 5D: short-run effect (about one week).
  - 20D: medium-run effect (about one month).

## Verified main results (from `event_study_main_table.csv`)

- `event_count=132`
- `matched_count=131`
- `mean_abnormal_return_1d=0.004285` (about +0.43%)
- `mean_abnormal_return_5d=0.003410` (about +0.34%)
- `mean_abnormal_return_20d=-0.026388` (about -2.64%)
- `mean_car_5d=0.002668` (about +0.27%)
- `mean_car_20d=-0.026894` (about -2.69%)
- `abnormal_return_20d: t=-2.044981, p=0.042973`
- `car_20d: t=-2.139741, p=0.034335`

Plain-English read:

- Short windows (1D/5D) are mildly positive on average.
- 20D average is negative.
- 20D t-stats are statistically significant at ~5% level in this sample.
- This pattern is consistent with "short-run pop, weaker medium-run follow-through," but it does **not** prove causation.

## What grouped tables suggest

### By ticker (`event_study_by_ticker.csv`)

- Concentration is real:
  - `TSLA` = 41 events
  - `AAPL` = 20
  - `NVDA` = 18
  - `AMD` = 14
- This concentration means results are heavily influenced by a few mega-cap names.

### By creator (`event_study_by_creator.csv`)

- Largest creator exposure:
  - `HyperChange` = 31 events
  - `Joseph Carlson` = 16
  - `Sasha Yanshin` = 13
  - `Financial Education` = 11
- Creator-level means vary substantially, so pooled averages mask heterogeneity.

### By year (`event_study_by_year.csv`)

- Event counts: 2024 is largest (47), then 2025 (23), 2023 (23), 2026 (18), 2022 (17), 2021 (3), 2020 (1 unmatched).
- Year-specific means differ, indicating regime/timing sensitivity.

### By recommendation type (`event_study_by_recommendation_type.csv`)

- `buy` dominates volume (84 events, 83 matched).
- `sell` bucket has positive average 20D in this sample (counterintuitive, suggests context/regime effects).
- Smaller categories can be noisy.

### By direction (`event_study_by_direction.csv`)

- `positive`: 108 events (107 matched)
- `negative`: 24 events (24 matched)
- 20D averages are negative for both buckets in this run.

## What charts show

- Distribution charts (`abnormal_return_*`, `car_*`) show spread/outliers and why means alone are insufficient.
- `mean_abnormal_return_by_window.png` summarizes horizon pattern: short-horizon mild positives, 20D negative.
- `events_by_year`, `events_by_creator_top10`, `events_by_ticker_top10` show sample concentration.
- `mean_car_20d_by_creator_top10` highlights creator-level variation and instability of creator claims.

## What is strong vs weak

Strong:

- High match coverage (131/132).
- Transparent diagnostic trail for unmatched event.
- Consistent caveat handling for prototype data.
- Clear grouped outputs and reproducible reporting artifacts.

Weak:

- Interim yfinance source (not final-quality inference base).
- Rules-filtered sample, not full hand-labeled gold standard.
- Concentrated ticker/creator mix (possible selection and composition bias).
- Observational design: cannot identify causal treatment effect.

## Statistical tests: how to present carefully

- 20D abnormal/CAR p-values are below 0.05 in this sample.
- 1D and 5D tests are not statistically significant here.
- Safe framing: "Evidence of negative medium-horizon association in this prototype sample."
- Overstated framing to avoid: "Finfluencers cause long-run losses."

## Safe claims for paper/presentation

- "In this prototype sample, short-window abnormal returns are slightly positive, while medium-window (20D) abnormal returns are negative on average."
- "The event-study join quality is high (99% matched), with one documented unmatched event."
- "Results are provisional because market data is yfinance prototype data and sample construction is rules-based."

## Claims that would be overstated

- Any statement of causal proof.
- Any broad normative claim ("finfluencers are good/bad overall") from this prototype alone.
- Any final inference without Bloomberg replacement and additional robustness checks.

## What to do next before final submission

1. Replace yfinance market data with Bloomberg-formatted import.
2. Rerun validation, event study, diagnostics, reporting, and chart commands.
3. Compare pre/post Bloomberg result shifts at headline and grouped levels.
4. Add robustness checks for concentration (e.g., excluding top ticker/creator, winsorization, duplicate controls).
5. Tighten thesis language to associational claims unless causal identification is added.
