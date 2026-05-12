# Limitations

This section highlights constraints that are important for interpretation of the current prototype results.

## 1) Prototype market data (yfinance) rather than final Bloomberg inputs

The current event-study outputs rely on interim yfinance/Yahoo market data. This is useful for workflow development and directional checks, but it is not a substitute for Bloomberg-grade research inputs. Final inference should be based on Bloomberg replacement and rerun outputs.

## 2) Rules-filtered sample, not full human gold-standard labeling

The 132-event clean sample is generated through strict deterministic rules. While auditable and reproducible, it is not equivalent to comprehensive manual labeling and may contain false positives/false negatives in event identification or direction tagging.

## 3) Concentration in a small number of tickers and creators

The sample is concentrated in a few high-attention names (especially TSLA, AAPL, NVDA) and selected creators. This concentration increases sensitivity to ticker-specific and creator-specific episodes and may limit generalizability to broader finfluencer content.

## 4) Transcript and coverage selection bias

Event inclusion depends on transcript availability and pipeline detection performance. Videos with missing transcripts or less explicit recommendation language are less likely to enter the event sample, potentially biasing observed distributions.

## 5) Engagement measurement timing

YouTube metadata generally reflects current cumulative engagement rather than true event-time engagement snapshots. This limits interpretation of engagement as a contemporaneous explanatory variable in event timing.

## 6) Observational design and no causal identification

The event study is observational and associational. The results do not establish causal effects of finfluencer content on returns. Unobserved confounders (news shocks, macro releases, earnings cycles, momentum) may co-move with event timing.

## 7) Overlapping windows and dependence across events

Events may cluster in time and windows can overlap, particularly for frequently discussed tickers and creators. Overlap can induce dependence across event returns and complicate interpretation of standard t-tests.

## 8) Broader market and meme-stock confounds

Parts of the sample period include unusual market regimes and meme-stock dynamics, which may amplify volatility and attention effects independent of creator recommendations. This can distort subgroup means and pooled estimates.

Overall, these constraints support cautious language: current findings are informative prototype associations, not final causal conclusions.
