# Event Study Robustness Table

| specification | horizon | n | mean | median | t_stat | p_value | bh_q_value | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Canonical baseline | AR_0_1 | 1516 | 0.002728 | 0.000773 | 3.251 | 0.001149 | 0.010472 | 16-ticker locked yfinance file |
| Canonical baseline | AR_0_5 | 1503 | 0.005236 | 0.000421 | 3.195 | 0.001396 | 0.010472 | 16-ticker locked yfinance file |
| Expanded all events | AR_0_1 | 1549 | 0.000016 | 0.000513 | 0.015 | 0.988189 | 0.988189 |  |
| Expanded all events | AR_0_5 | 1536 | 0.003269 | -0.000162 | 1.868 | 0.061830 | 0.103050 |  |
| Low-lookahead-risk | AR_0_1 | 510 | 0.001987 | 0.000800 | 2.098 | 0.035949 | 0.077034 | Upload bucket before_open/weekend_or_holiday |
| Low-lookahead-risk | AR_0_5 | 505 | 0.007133 | 0.002005 | 2.961 | 0.003063 | 0.011487 | Upload bucket before_open/weekend_or_holiday |
| Duplicate-collapsed | AR_0_1 | 1112 | 0.001345 | 0.000561 | 1.387 | 0.165527 | 0.206909 | First event per duplicate cluster |
| Duplicate-collapsed | AR_0_5 | 1104 | 0.004058 | -0.000057 | 2.183 | 0.029023 | 0.072558 | First event per duplicate cluster |
| High-quality A/B | AR_0_1 | 922 | -0.002039 | 0.000046 | -1.391 | 0.164168 | 0.206909 |  |
| High-quality A/B | AR_0_5 | 916 | 0.000677 | -0.001356 | 0.307 | 0.758519 | 0.812699 |  |
| Non-top-ticker | AR_0_1 | 574 | -0.006835 | -0.001864 | -3.070 | 0.002141 | 0.010704 | Excludes NVDA/TSLA/AAPL/AMD/AMZN |
| Non-top-ticker | AR_0_5 | 565 | -0.004901 | -0.005551 | -1.871 | 0.061320 | 0.103050 | Excludes NVDA/TSLA/AAPL/AMD/AMZN |
| Buy only | AR_0_5 | 1193 | 0.005375 | -0.000258 | 2.810 | 0.004947 | 0.014840 |  |
| Sell only | AR_0_5 | 343 | -0.004057 | 0.000377 | -0.983 | 0.325523 | 0.375603 |  |
| Winsorized 1/99 | AR_0_5 | 1536 | 0.002941 | -0.000162 | 1.803 | 0.071402 | 0.107102 |  |

BH q-values are Benjamini-Hochberg FDR adjustments across the rows in this table.
