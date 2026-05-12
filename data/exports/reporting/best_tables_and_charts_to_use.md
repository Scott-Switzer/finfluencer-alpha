# Best Tables and Charts to Use

## Top 3 tables for the paper (ranked)

1. **`event_study_main_table.csv`**
   - Why: Single source of headline metrics (means/medians, CAR, t-stats, p-values).
   - Caption: "Prototype event-study headline outcomes for 132 clean events (131 matched), benchmark-adjusted to SPY."

2. **`event_study_by_ticker.csv`**
   - Why: Directly discloses ticker concentration and heterogeneity; critical for interpretation.
   - Caption: "Ticker-level abnormal-return and CAR heterogeneity, highlighting concentration in TSLA/AAPL/NVDA."

3. **`event_study_by_year.csv`**
   - Why: Shows time/regime variation and supports caution around pooled estimates.
   - Caption: "Year-by-year event-study outcomes indicating temporal variation in abnormal performance."

## Top 5 charts for presentation (ranked)

1. **`mean_abnormal_return_by_window.png`**
   - Why: Fastest visual for the core 1D/5D/20D narrative.
   - Caption: "Mean abnormal return by horizon shows short-run positive and medium-run negative pattern."

2. **`abnormal_return_20d_distribution.png`**
   - Why: Supports 20D inference with distribution context rather than only mean.
   - Caption: "Distribution of 20-day abnormal returns in the matched prototype sample."

3. **`car_20d_distribution.png`**
   - Why: Confirms medium-run pattern in cumulative terms.
   - Caption: "Distribution of 20-day cumulative abnormal returns (CAR) across matched events."

4. **`events_by_ticker_top10.png`**
   - Why: Clearly communicates concentration risk to audience.
   - Caption: "Top-10 ticker event counts reveal sample concentration in a few large names."

5. **`events_by_creator_top10.png`**
   - Why: Shows creator concentration and potential compositional effects.
   - Caption: "Top-10 creator event counts show uneven creator representation in the prototype sample."

## Use in appendix (or use cautiously)

- **`event_study_by_creator.csv`**: informative, but creator subgroup sizes vary and can be noisy.
- **`event_study_by_recommendation_type.csv`** and **`event_study_by_direction.csv`**: useful robustness/context tables; keep as secondary.
- **`mean_car_20d_by_creator_top10.png`**: helpful for heterogeneity discussion, but easy to over-interpret due to subgroup noise.
- **`event_study_robustness_thresholds.csv`**: strong methodology appendix table for explaining the strict 132-event sample.
- **`event_study_match_diagnostics.csv`**: include in appendix for transparency; summarize unmatched case in main text.

## Tables/charts to avoid as primary evidence

- Avoid leading with highly disaggregated creator-level outputs as headline "effect" evidence.
- Avoid any chart/table that could imply causality without explicit caveat language.
- Avoid presenting yfinance-based outputs without the prototype-data warning on the same slide/page.
