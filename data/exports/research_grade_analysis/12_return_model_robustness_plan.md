# Return Model Robustness Plan

## Status

- Baseline: market-adjusted abnormal returns vs SPY (computed in this pass for
  all 1,554 events with available local market data).
- Plan: extend to a layered set of return models against the same locked
  sample, with explicit reruns scheduled at Bloomberg-day.

## Layered Models

| # | Model | What it adds | Computed in this pass | Required data |
| --- | --- | --- | --- | --- |
| 1 | Raw returns | None | Yes | Local yfinance prices |
| 2 | Market-adjusted | Subtract SPY return | Yes | Local SPY series |
| 3 | CAPM alpha | Regress on SPY excess; report alpha | Plan | Risk-free rate (FRED DGS3MO), or treat as zero |
| 4 | Fama-French 3 factor | Add SMB, HML | Plan | Kenneth French Data Library |
| 5 | Carhart 4 factor | Add MOM | Plan | Kenneth French Data Library |
| 6 | Fama-French 5 factor | Add RMW, CMA | Plan | Kenneth French Data Library |
| 7 | Industry-adjusted | Subtract sector ETF (XLK/XLC/XLY/XLF/XLI) | Plan (sector mapping already exists) | Local sector ETF series in expanded file |
| 8 | Matched-control | Build size/momentum matched control firm; AR = event - control | Plan | Tradeable universe + market-cap snapshot |

## Implementation Sketch

```python
import pandas as pd
import statsmodels.api as sm
import requests
from io import BytesIO
from zipfile import ZipFile

def fetch_french_factors(url: str) -> pd.DataFrame:
    r = requests.get(url, headers={"User-Agent": "fin496-capstone (educational)"}, timeout=30)
    r.raise_for_status()
    with ZipFile(BytesIO(r.content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".CSV"))
        with zf.open(name) as f:
            df = pd.read_csv(f, skiprows=3, skipfooter=2, engine="python")
    df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"].astype(str).str.zfill(8), format="%Y%m%d", errors="coerce")
    return df.dropna(subset=["date"]).set_index("date").apply(pd.to_numeric, errors="coerce") / 100.0

FF3 = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
MOM = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip"
FF5 = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
```

For each model and each event-window definition (1D, 5D, 20D), report:

- alpha, t-stat, p-value, n,
- mean and median return,
- subsample cuts by buy/sell, by top-vs-non-top ticker, by quality tier A vs C/D,
- comparison vs the market-adjusted baseline (delta in alpha and t-stat).

## Implementation Order (Bloomberg-Day Plan)

1. Fetch French data daily files (FF3, MOM, FF5) into
   `data/imports/french_factors/`. This is allowed because the Kenneth French
   data library is free and explicitly cite-able.
   Expected extracted files:
   - `data/imports/french_factors/F-F_Research_Data_Factors_daily.CSV`
   - `data/imports/french_factors/F-F_Momentum_Factor_daily.CSV`
   - `data/imports/french_factors/F-F_Research_Data_5_Factors_2x3_daily.CSV`
2. Build `event_factor_panel.csv`: event_id x window x daily return contributions
   (ticker excess, SPY excess, factor returns aligned to trading days).
3. Run CAPM via `statsmodels.OLS(y, X)` with HC0 standard errors.
4. Run FF3, Carhart, FF5 via the same scaffolding (only the X matrix grows).
5. Run industry-adjusted by replacing SPY with the mapped sector ETF.
6. Build matched-control: nearest-neighbor on (market cap decile, momentum
   decile, SPY beta). With only 23 tickers in the sample, matched control should
   use a *cross-section* of S&P 500 universe constructed once.
7. Report a consolidated `return_model_alpha_table.csv` with one row per
   (model, window, sample cut).

## Acceptance Criteria

- Headline 5D abnormal return is positive and significant under at least three
  of {raw, market-adj, CAPM, FF3, Carhart, FF5, industry-adj}.
- Headline result survives matched-control (delta in alpha within 2 standard
  errors of the market-adjusted baseline).
- Sign and direction stable across buy and sell cuts.
- No single creator or single ticker drives more than 25% of the headline
  point estimate (this is also a robustness cut in `13_statistical_robustness_matrix.md`).
