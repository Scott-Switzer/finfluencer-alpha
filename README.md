# YouTube Finfluencer Recommendations and Stock Return Dynamics

> **New readers:** start with [`final_defense_package/FINAL_READER_GUIDE.md`](data/exports/final_paper_package_v2_expanded/final_defense_package/FINAL_READER_GUIDE.md) (paper tables, claims, limits).

## Abstract

This repository studies **transcript-supported YouTube stock recommendations** and subsequent abnormal returns in an expanded sample of **2,341 accepted recommendation events** (9,992 transcript-video rows). The evidence does **not** support broad short-window YouTube alpha. Results are **heterogeneous**: top mega-cap names show positive raw dynamics consistent with **concentration and momentum exposure**, while **non-top** recommendations tend to underperform over medium horizons. Matched controls, factor adjustments, portfolio realism, and partial public-news layers **reject causal skill and tradability** claims.

## Validated sample

- Primary package: `data/exports/final_paper_package_v2_expanded/`
- v1 locked package: `data/exports/final_paper_package/` (historical benchmark)
- Authoritative build: RunPod database + `locked_sample_v2/` manifests
- Return coverage: documented in `long_horizon/02_v2_long_horizon_coverage.csv`

## Main findings

- **Heterogeneous return dynamics** — not a uniform finfluencer premium.
- **Top-5** names: positive short-window raw abnormal returns that **weaken** under factor and placebo checks.
- **Non-top** names: weaker medium-horizon performance; **not** validated on a public-news-clean subsample (non-top master-clean **n = 0**).
- **Mechanism-consistent patterns**: pre-event momentum concentration (especially top-5), attention/volume amplification, partial reversal after short pops.
- **Creator taxonomy**: mostly momentum-rider or noisy; not uniform skill.

## Claims rejected

| Claim | Status |
| --- | --- |
| Broad YouTube alpha | **Rejected** |
| Causal creator skill | **Rejected** |
| Tradable strategy | **Rejected** |
| Full public-news-clean robustness | **Rejected / partial** |
| GDELT as confirmatory news control | **Rejected** (diagnostic only) |

## Methods

- Transcript-supported event detection and quality scoring
- SPY-adjusted BHAR/CAR event studies with right-censoring flags
- SEC/earnings confound flags; Alpha Vantage compact news metadata (partial coverage)
- Kenneth French daily factor models and calendar-time HAC portfolios
- Matched controls, date-shift placebos, creator cross-ticker placebos
- Market-implied activity screen (**not** equivalent to news-clean)
- **Information environment** layer: analyst relay, market sentiment regimes, transcript narrative relay, originality taxonomy, incremental predictive value (`information_environment/`)
- Research-frontier mechanism modules (selection, attention, reversal, predictive holdouts)
- Multiple-testing audit (BH FDR, Holm) on reported p-values; see `PRIMARY_SECONDARY_EXPLORATORY_HIERARCHY.md`

## Research-frontier robustness extensions

Under `data/exports/final_paper_package_v2_expanded/research_frontier/`:

- Recommendation selection / momentum chasing
- Attention amplification
- Reversal / overreaction
- Creator skill-like taxonomy (non-causal labels)
- Transcript language scores (evidence snippets only)
- Expanded placebos and predictive validity
- Holdouts: creator-out, ticker-out, year-out

See `research_frontier/00_research_frontier_workplan.md`.

## News and confound status

- **Alpha Vantage**: partial ticker coverage (~4 tickers under free-tier limits); **unknown ≠ clean**
- **GDELT**: diagnostic only (low success rate)
- **Master confound panel**: `confounds_expanded/`
- **Market-implied screen**: sensitivity for pre-event activity — **not** public-news-clean (e.g. non-top + market_quiet 21D ≈ **-0.56%**)
- **Analyst relay** (FMP → Finnhub preferred; **yfinance used more aggressively** as diagnostic gap-filler): improves coverage but not causal identification; event-time claims require dated pre-event rows; current yfinance targets/ratings are diagnostic-only; Bloomberg remains planned validation
- Cross-ticker placebo 5D ≈ **+0.19%** (economically near zero)

## Data availability

Public repo contains **committed CSV/MD exports** and scripts. Private assets (DB, raw transcripts, API keys, bulky news caches) are **not** committed. See `docs/DATA_AVAILABILITY.md` and `final_defense_package/LOCAL_ASSET_MANIFEST.md`.

## Reproducibility

```bash
python3 scripts/validate_expanded_primary_sample_package.py
python3 scripts/validate_locked_sample_manifest.py
python -m ruff check .
pytest -q
```

Full empirical rebuild requires RunPod with `data/finfluencer_alpha.db` and market imports. See `final_defense_package/REPRODUCTION_COMMANDS.md`.

## Not investment advice

Student research project for FIN 496. Results are descriptive and robustness-oriented; they are **not** investment advice.

## Repository safety

- Do **not** commit `.env`, `.save`, logs, raw databases, raw transcripts, raw API responses, or article metadata caches.
- Unknown news states must **never** be coded as clean.
- **504D** horizons are **diagnostic only** unless full-window support is materially proven.
