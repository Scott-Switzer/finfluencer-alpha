# Research and LinkedIn Positioning Memo

## Reframe

We are not (yet) claiming causal alpha. The defensible framing is:

> YouTube finfluencer recommendations are associated with short-window abnormal
> returns in a locked transcript-supported event sample, but robustness evidence
> suggests the effect is concentrated in major mega-cap names and may reflect
> attention/momentum amplification rather than broad, tradable causal alpha.

The primary contribution is the **pipeline** + **dataset** + **robustness
matrix**, not a published trading strategy.

## What Is Novel

- Locked, reproducible sample of 1,554 accepted creator recommendations
  derived from 9,992 collected YouTube transcripts across 35 finance
  creators and 23 large-cap tickers.
- Event derivation requires same-window co-occurrence of a ticker mention and
  a directional recommendation phrase, not just title/description scraping.
- Per-event quality scoring with auditable reason codes (Tier A/B/C/D)
  enabling robustness cuts without manual audit.
- Momentum decomposition layered on top of the event-study (most public
  finfluencer claims do not pre-test for momentum overlap).
- News confound protocol that ships with explicit placeholder schema rather
  than ad-hoc skipping.

## What Is Preliminary

- yfinance prices are interim; CAPM/FF3/Carhart/FF5 alphas are not yet computed
  with French factor data.
- News confound flags are "unknown" pending Bloomberg-day rerun.
- Portfolio backtest is event-aggregated, not calendar-time, and ignores
  trading costs.

## What Is Robust Now

- 1D and 5D market-adjusted abnormal returns are positive at p < 0.005 on the
  locked canonical yfinance sample (`mean_1D = 0.00273, mean_5D ~ 0.005`).
- Buy/sell direction split: buys clearly positive; sells noisy.
- Year-by-year cuts show 2024 and 2025 driving the headline, with 2022
  negative (creators were bearish into a falling market).
- Result survives top-creator and top-ticker LOCO with mean still positive, but
  the non-top-ticker cut weakens materially and can flip negative.

## What Is Provisional

- The 5D mean is sensitive to event-day and execution conventions
  (same-day event-study window vs next-day executable entry); Bloomberg
  total-return series will tighten this.
- The result is *not* yet robust to news confounds because the news flag is
  protocol-only.
- The result is not robust to FF3/Carhart alpha until French factors arrive.

## What Bloomberg Validates

- Replaces yfinance prices with dividend-adjusted total return.
- Provides earnings/news/analyst-change timestamps to populate
  `news_confounded_event_flag`.
- Enables CAPM/FF3/Carhart/FF5 alpha with HC/cluster SEs (via downloaded
  French factors, which the Bloomberg-day run also schedules).
- Provides market cap and beta snapshots for matched-control construction.

## Honest LinkedIn Claims

Use:

- "Built a reproducible NLP + event-study pipeline that converts 9,992
  YouTube finance transcripts into 1,554 ticker-level recommendation events
  across 23 large-cap tickers."
- "Provisional results suggest buy-rated YouTube recommendations are associated
  with small positive short-horizon abnormal returns on a locked sample, pending
  licensed Bloomberg validation."
- "Designed a per-event quality scoring system with auditable reason codes
  that enables robustness cuts without manual labeling."

Avoid:

- Anything about "alpha", "trading strategy", or "outperformance".
- Annualized Sharpe figures (the backtest is provisional and not calendar-time).
- Any framing that implies causal influence of creators on prices; the
  honest framing is "attention-linked abnormal returns" until news confounds
  are excluded.

## Undergraduate Journal Version (e.g., Issues in Political Economy, SURJ)

Required additions before submission:

- Bloomberg rerun of every headline statistic.
- Populated news-confound flags with confounded-excluded headline reported.
- Matched-control return model (FF3 alpha minimum).
- Pre-trend test reported as a table row in the robustness matrix.
- Spot-check audit with disagreement rate documented.
- Single-paragraph data-availability statement that points to the locked
  sample artifacts and the script.

## SSRN Working Paper Version

Required additions on top of journal version:

- Full calendar-time portfolio backtest with FF5 + Carhart alphas, costs,
  Sharpe, max drawdown, turnover.
- Cross-sectional regression of post-event AR_0_5 on transcript features
  from `16_transcript_feature_engineering_plan.md`.
- Bayesian posteriors for headline probabilities.
- Replication appendix with exact commit hash and frozen environment file
  (`uv.lock` or `requirements.lock`).
- "Limitations" section explicitly listing the X-exclusion rationale, the
  ambiguous-ticker risk, and the 23-ticker concentration.
