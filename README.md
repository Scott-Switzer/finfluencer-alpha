# YouTube Finfluencer Recommendations and Stock Return Dynamics

This repository studies transcript-supported YouTube stock recommendations and subsequent stock return dynamics. The validated expanded v2 sample contains 9,992 transcript-video rows and 2,341 accepted recommendation events. The current evidence does not support broad short-window YouTube alpha. The defensible finding is heterogeneity: returns concentrate in top-5 mega-cap/momentum tickers, while recommendations outside those names underperform through medium horizons. Matched controls, factor checks, and portfolio diagnostics reject causal and tradable-alpha overclaims.

## Dataset Status

- `data/exports/final_paper_package/`: v1 locked historical artifact package.
- `data/exports/final_paper_package_v2_expanded/`: primary empirical package.
- v2 accepted recommendation events: 2,341.
- v2 return coverage: 2,322 1D events and long-horizon coverage documented in `long_horizon/02_v2_long_horizon_coverage.csv`.

## Methods

- Transcript-supported event detection.
- Event studies using SPY-adjusted BHAR/CAR.
- Long-horizon return panels with right-censoring flags.
- SEC/earnings confound flags.
- Real public-news metadata through Alpha Vantage where available; GDELT is diagnostic only.
- Beta-estimated factor alpha and factor-basket checks.
- Matched controls, placebo/permutation diagnostics, overlap/censoring robustness.
- Portfolio execution realism with costs, delays, drawdowns, and concentration.

## Main Findings

- Broad alpha: rejected.
- Top-5 attention/concentration: supported but not causal.
- Non-top underperformance: supported/mixed through medium horizons.
- Causality: rejected by matched controls and placebo diagnostics.
- Tradable strategy: rejected due to concentration, drawdown, costs, and execution caveats.
- News-clean robustness: partial only. Alpha Vantage mapped real metadata but coverage remains incomplete; GDELT success rate is below the usability threshold.

## Final Claim Status

| Claim | Status |
| --- | --- |
| Broad YouTube alpha | Rejected |
| Top-5 attention/concentration | Supported / mixed |
| Non-top underperformance | Supported / mixed |
| Causality | Rejected |
| Tradable strategy | Rejected |
| News-clean robustness | Partial |
| Creator skill | Not supported |

## Reproducibility

Run the validation suite from the repository root:

```bash
python3 scripts/validate_expanded_primary_sample_package.py
python3 scripts/validate_locked_sample_manifest.py
ruff check .
pytest -q
```

No API keys, raw transcripts, raw databases, raw article bodies, or `.env` files should be committed. This is a student research project and not investment advice.
