# YouTube Finfluencer Recommendations and Stock Return Dynamics

> **New readers:** start with [`final_defense_package/FINAL_READER_GUIDE.md`](data/exports/final_paper_package_v2_expanded/final_defense_package/FINAL_READER_GUIDE.md) (paper tables, claims, limits).

## Research question

Do transcript-supported YouTube stock recommendations exhibit broad, tradable abnormal returns after accounting for event timing, market benchmarks, public-information confounds, analyst relay, and execution realism?

## Abstract

This repository studies **transcript-supported YouTube stock recommendations** and subsequent abnormal returns in an expanded sample of **2,341 accepted recommendation events** (9,992 transcript-video rows). The evidence does **not** support broad, tradable finfluencer alpha. The strongest pattern is heterogeneity: salient top-name and analyst-aligned recommendations behave differently from non-top recommendations. The evidence is more consistent with attention amplification, consensus relay, ticker selection, and public-information overlap than causal creator stock-picking skill. Because the strict multi-source-clean public-news sample is empty, results are mechanism-consistent rather than public-news-clean causal evidence.

## Validated sample

- Primary package: `data/exports/final_paper_package_v2_expanded/`
- v1 locked package: `data/exports/final_paper_package/` (historical benchmark)
- Canonical v2 counts: **9,992** transcript-video rows, **2,341** accepted events, **2,322** 1D return-matched events, **2,299** 5D return-matched events
- Authoritative build: RunPod database + `locked_sample_v2/` manifests
- Final paper synthesis: `final_paper_synthesis/`
- Final defense/readout package: `final_defense_package/`
- Bloomberg validation: `bloomberg_validation/`
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
- SEC/earnings confound flags; multi-provider public-news confound master layer (FNSPID 1999–2023 backbone when cached, budgeted live provider probes with strict “unknown ≠ clean” handling)
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

- **Multi-provider news master**: `news_confound_master/`; current RunPod build has **0 multi_source_clean events**, so public-news-clean claims are not supported.
- **Alpha Vantage**: partial ticker coverage; **unknown ≠ clean**
- **GDELT**: diagnostic only (low success rate)
- **Legacy master confound panel**: `confounds_expanded/`
- **Market-implied screen**: sensitivity for pre-event activity — **not** public-news-clean (e.g. non-top + market_quiet 21D ≈ **-0.56%**)
- **Analyst relay** (FMP -> Finnhub preferred; yfinance used as a diagnostic gap-filler): improved grade mapping classifies dated analyst stances more completely, but it does not establish causality; event-time claims require dated pre-event rows; current yfinance targets/ratings are diagnostic-only snapshots; unknown analyst/news coverage is never clean; Bloomberg validation is now included as a descriptive mechanism layer, not causal identification
- Cross-ticker placebo 5D ≈ **+0.19%** (economically near zero)

## Bloomberg validation status

- Derived Bloomberg validation outputs are committed under `data/exports/final_paper_package_v2_expanded/bloomberg_validation/`.
- Bloomberg data are used as institutional mechanism/context proxies only; they do not prove causality, public-news-clean alpha, creator skill, or tradability.
- `Analyst_coverage` / `TOT_ANALYST_REC` remains unavailable in the current derived coverage summary, so no analyst coverage count claim is added.
- Raw Bloomberg workbooks belong under `data/manual/bloomberg_validation/` and are not committed.

## Data availability

Public repo contains **committed CSV/MD exports** and scripts. Private assets (DB, raw transcripts, raw Bloomberg workbooks, API keys, bulky news caches) are **not** committed. See `docs/DATA_AVAILABILITY.md` and `final_defense_package/LOCAL_ASSET_MANIFEST.md`.

## Reproducibility

```bash
python3 scripts/validate_expanded_primary_sample_package.py
python3 scripts/validate_locked_sample_manifest.py
python -m ruff check .
pytest -q
python scripts/ingest_bloomberg_validation_workbook.py --help
```

Full empirical rebuild requires RunPod with `data/finfluencer_alpha.db` and market imports. See `final_defense_package/REPRODUCTION_COMMANDS.md`.

## Not investment advice

Student research project for FIN 496. Results are descriptive and robustness-oriented; they are **not** investment advice.

## Repository safety

- Do **not** commit `.env`, `.env.*`, `marketdata.env`, logs, raw databases, raw transcripts, raw API responses, raw Bloomberg workbooks, or article metadata caches.
- Unknown news states must **never** be coded as clean.
- **504D** horizons are **diagnostic only** unless full-window support is materially proven.
