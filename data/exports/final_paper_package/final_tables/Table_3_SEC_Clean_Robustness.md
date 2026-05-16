# SEC-Filing-Excluded Event Study Table

| specification | horizon | n | mean | median | t_stat | p_value | bh_q_value | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-clean expanded | AR_0_1 | 716 | 0.001457 | 0.000169 | 1.764 | 0.077677 | 0.097096 |  |
| SEC-clean expanded | AR_0_5 | 715 | 0.008007 | 0.004653 | 3.746 | 0.000180 | 0.000300 |  |
| SEC-clean low-lookahead | AR_0_1 | 257 | 0.001320 | 0.000046 | 1.098 | 0.272033 | 0.272033 |  |
| SEC-clean low-lookahead | AR_0_5 | 257 | 0.012487 | 0.005151 | 4.025 | 0.000057 | 0.000143 |  |
| SEC-clean duplicate-collapsed | AR_0_5 | 533 | 0.009260 | 0.005151 | 4.163 | 0.000031 | 0.000143 |  |

Rows exclude events with material SEC filings flagged within a ±5-day window. This specification provides SEC-only robustness and does not cover Bloomberg headlines, analyst actions, earnings timestamps, press releases, or macro/sector news.
