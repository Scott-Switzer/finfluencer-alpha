# Finfluencer Alpha or Attention Spillover? A Cross-Platform Study of X and YouTube Stock Recommendations

## Research Question

Do finfluencer stock recommendations on X and YouTube generate abnormal risk-adjusted returns for retail investors, or do they mostly amplify attention toward stocks that were already moving?

## Motivation

Prior thesis evidence suggests that YouTube finfluencer videos did not show significant positive abnormal returns after posting, while abnormal returns appeared before videos were posted. This project tests whether X functions as a faster upstream attention layer and YouTube functions as slower amplification.

## Hypotheses

H1: X stock recommendations are associated with abnormal short-term attention and trading volume.

H2: YouTube recommendations often lag prior X attention or prior price movement.

H3: Stocks mentioned on both X and YouTube show stronger abnormal volume and volatility than stocks mentioned on only one platform.

H4: After controlling for size, sector, beta, liquidity, and prior momentum, finfluencer recommendations do not generate persistent alpha.

H5: Some creators may show skill, but average creator recommendations are not statistically distinguishable from noise.

## Feasibility

- X recent search enables forward collection now.
- X full archive can be added if access is available.
- YouTube historical metadata is feasible through Data API.
- Bloomberg Terminal will provide clean price, volume, market cap, beta, sector, and benchmark data.
- MVP can be built with 10-20 X accounts and 5-10 YouTube channels.

## MVP Deliverables

- Candidate creator database for X and YouTube.
- Raw API audit trail saved as JSON.
- Normalized SQLite tables for posts, videos, ticker mentions, recommendation candidates, and creator scores.
- CSV exports for professor review.
- Documented limitations around API access, retrospective bias, and manual validation.
