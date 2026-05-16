# yfinance Event Study Results (Provisional)

- This is provisional prototype evidence from local yfinance data and is not causal inference.
- Canonical command used: `python3 -m finfluencer_alpha run-event-study ...` with locked-sample input and existing local market-data CSV.
- Events processed: `1516`
- Events matched by runner: `1516`

## Overall Statistics

- abnormal_return_1d: n=1516, mean=0.002728, median=0.000773, t=3.251377, p=0.001174
- abnormal_return_5d: n=1503, mean=0.005236, median=0.000422, t=3.195439, p=0.001425

## Cuts by Creator (5D, n>=15)

- Jose Najarro Stocks: n=286, mean=0.006166, median=0.004639, t=1.825323, p=0.068999
- Mark Roussin, CPA: n=226, mean=0.005932, median=0.001935, t=1.966183, p=0.050507
- The Investor Channel: n=124, mean=0.010472, median=-0.001323, t=1.762945, p=0.080393
- Couch Investor: n=108, mean=-0.006485, median=-0.011736, t=-1.025286, p=0.307541
- HyperChange: n=76, mean=-0.008080, median=-0.021035, t=-0.616459, p=0.539459
- Daniel Pronk: n=68, mean=-0.002204, median=-0.003952, t=-0.344020, p=0.731909
- Ticker Symbol: YOU: n=66, mean=-0.001736, median=-0.002057, t=-0.255688, p=0.798999
- Financial Education: n=61, mean=0.033855, median=-0.005071, t=3.209962, p=0.002133

## Cuts by Year (5D, n>=15)

- 2020: n=32, mean=0.022557, median=0.015019, t=1.447092, p=0.157909
- 2021: n=16, mean=-0.025546, median=-0.039652, t=-2.106688, p=0.052391
- 2022: n=70, mean=-0.051679, median=-0.031767, t=-5.461008, p=0.000001
- 2023: n=160, mean=0.007717, median=0.008851, t=2.609062, p=0.009945
- 2024: n=373, mean=0.016921, median=0.001898, t=4.393246, p=0.000015
- 2025: n=466, mean=0.004642, median=-0.003001, t=1.959194, p=0.050687
- 2026: n=386, mean=0.003793, median=0.003208, t=1.174607, p=0.240878

## Cuts by Recommendation Type (5D, n>=15)

- buy: n=1177, mean=0.005549, median=0.000145, t=2.958664, p=0.003152
- sell: n=326, mean=0.004105, median=0.003466, t=1.224084, p=0.221807

## Interpretation Guardrail

- Results are descriptive/associational and sensitive to interim market-data quality and event clustering.
- Bloomberg replacement remains required before final inferential claims.
