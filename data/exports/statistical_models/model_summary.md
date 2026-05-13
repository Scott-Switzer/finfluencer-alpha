# Statistical Model Summary

## Descriptive Event-Window Results

| Window | N | Mean AR% | Median AR% | Std AR% | t-stat | p-value | Win Rate% | 95% CI |
|--------|---|----------|------------|---------|--------|---------|-----------|--------|
| 1D | 131 | 0.429 | 0.269 | 4.165 | 1.18 | 0.2411 | 58.0 | [-0.28, 1.14] |
| 5D | 130 | 0.341 | 0.454 | 8.322 | 0.47 | 0.6412 | 50.8 | [-1.09, 1.77] |

## Regression Results

### intercept_only — 1D
- N = 131, R² = -0.0000, Adj R² = -0.0000
| Variable | Coef (%) | Std Err | p-value |
|----------|----------|---------|---------|
| const | 0.4285 | 0.3639 | 0.2390 |
- Notes: Heteroskedasticity-robust SE (HC1).

### recommendation_type — 1D
- N = 131, R² = 0.0782, Adj R² = 0.0490
| Variable | Coef (%) | Std Err | p-value |
|----------|----------|---------|---------|
| const | -2.1451 | 2.0190 | 0.2880 |
| rec_buy | 2.3962 | 2.0478 | 0.2419 |
| rec_portfolio_update | 2.0223 | 2.0559 | 0.3253 |
| rec_price_target | 3.9586 | 2.5406 | 0.1192 |
| rec_sell | 5.0254* | 2.7466 | 0.0673 |
- Notes: Heteroskedasticity-robust SE (HC1).

### intercept_only — 5D
- N = 130, R² = 0.0000, Adj R² = 0.0000
| Variable | Coef (%) | Std Err | p-value |
|----------|----------|---------|---------|
| const | 0.3410 | 0.7299 | 0.6404 |
- Notes: Heteroskedasticity-robust SE (HC1).

### recommendation_type — 5D
- N = 130, R² = 0.0354, Adj R² = 0.0046
| Variable | Coef (%) | Std Err | p-value |
|----------|----------|---------|---------|
| const | -2.4665 | 2.7061 | 0.3621 |
| rec_buy | 3.1341 | 2.8597 | 0.2731 |
| rec_portfolio_update | 0.4049 | 3.1262 | 0.8970 |
| rec_price_target | 1.7617 | 4.9217 | 0.7204 |
| rec_sell | 5.9512* | 3.1346 | 0.0576 |
- Notes: Heteroskedasticity-robust SE (HC1).

## Creator-Level Alpha (Top 20)

| Creator | N | Mean CAR 1D% | Mean CAR 5D% | Win Rate% | t-stat 1D | p-value 1D | Flag |
|---------|---|--------------|--------------|-----------|-----------|------------|------|
| Mark Roussin, CPA | 6 | 1.190 | 4.770 | 83.3 | 1.99 | 0.1035 |  |
| Parkev Tatevosian, CFA | 5 | 0.149 | 0.374 | 60.0 | 0.24 | 0.8228 |  |
| Couch Investor | 7 | -0.726 | -6.566 | 57.1 | -0.92 | 0.3942 | * |

## Limitations & Disclaimers

- All returns are abnormal returns relative to SPY benchmark.
- yfinance data is prototype market data, not institutional-grade.
- Classifier labels are rule-generated pseudo-labels; no human ground truth yet.
- Event timing uncertainty: recommendations may not map precisely to event dates.
- Overlapping events are not adjusted for in standard SE calculations.
- No transaction costs, slippage, or shorting constraints modeled.
