# Probability and Calibration Plan

## Headline Conditional Probabilities

(95% CIs are Wilson intervals.)

| Statement | n | hits | probability | 95% CI lo | 95% CI hi |
| --- | --- | --- | --- | --- | --- |
| P(positive 1D AR | buy) | 1206 | 619 | 0.5133 | 0.4851 | 0.5414 |
| P(positive 5D AR | buy) | 1193 | 594 | 0.4979 | 0.4696 | 0.5262 |
| P(negative 5D AR | sell) | 343 | 171 | 0.4985 | 0.4459 | 0.5512 |
| P(reversal +5,+20 | positive 1D reaction) | 749 | 371 | 0.4953 | 0.4596 | 0.5311 |
| P(positive 5D AR | buy, tier A/B) | 734 | 363 | 0.4946 | 0.4585 | 0.5307 |
| P(negative 5D AR | sell, tier A/B) | 182 | 99 | 0.5440 | 0.4714 | 0.6147 |
| P(positive 5D AR | buy, top-5 creator) | 667 | 325 | 0.4873 | 0.4495 | 0.5252 |
| P(positive 5D AR | buy, non-top-5 creator) | 526 | 269 | 0.5114 | 0.4688 | 0.5539 |
| P(positive 5D AR | buy, ticker in NVDA/TSLA/AAPL) | 486 | 247 | 0.5082 | 0.4639 | 0.5524 |
| P(positive 5D AR | buy, ticker not in NVDA/TSLA/AAPL) | 707 | 347 | 0.4908 | 0.4541 | 0.5276 |

## Calibration by Event Quality Tier (Buys, P(positive 5D AR))

| Tier | n | hits | probability | 95% CI lo | 95% CI hi |
| --- | --- | --- | --- | --- | --- |
| A | 55 | 33 | 0.6000 | 0.4681 | 0.7188 |
| B | 679 | 330 | 0.4860 | 0.4486 | 0.5236 |
| C | 454 | 229 | 0.5044 | 0.4586 | 0.5502 |
| D | 5 | 2 | 0.4000 | 0.1176 | 0.7693 |


## Posterior Intervals (Bloomberg-Day Plan)

After Bloomberg-day rerun:

- For each conditional probability above, draw 5,000 Beta-binomial posterior
  samples with `alpha = 1 + hits`, `beta = 1 + (n - hits)`.
- Report posterior mean and 90%/95% credible intervals; this is the
  Bayesian counterpart to the Wilson interval table above.

## Calibration Methodology

- Bin events by `event_quality_score` quartile (within tier) and report the
  hit rate vs the predicted probability from a logistic regression
  `P(positive AR_0_5 | event_quality_score, recommendation_type)`. A
  well-calibrated quality score will produce near-monotone hit-rate ladders.
- Brier score on the same probabilistic predictions.
- Reliability diagram with 95% CIs per bin.

## Reported Variables

Each probability statement reports:

- `n`: number of events satisfying the conditioning set.
- `hits`: number of events meeting the outcome predicate.
- `probability`: point estimate (hits / n).
- 95% Wilson CI.
- After Bloomberg-day: posterior 5%/50%/95% quantiles.

## Acceptance Criteria

- Buy hit rate > 50% at 5D for high-quality tier with CI strictly above 50%.
- Sell hit rate > 50% (i.e., negative 5D AR for sells) at high quality.
- Non-top creator hit rate is within 5 percentage points of top-creator hit
  rate (otherwise the result is concentrated and not generalizable).
- Non-big-3 ticker hit rate within 5 percentage points of big-3 hit rate.
