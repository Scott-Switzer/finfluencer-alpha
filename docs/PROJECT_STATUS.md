# Project status

**Last frozen research HEAD:** see `git rev-parse HEAD` on `main`

## Primary sample

- **v2 expanded** is the primary empirical sample: **2,341** accepted recommendation events.
- **v1** locked package is preserved as a historical benchmark only.

## Headline conclusion

The evidence does **not** support broad short-window YouTube alpha or a tradable finfluencer strategy. The defensible story is **heterogeneous return dynamics** driven by **ticker concentration**, **momentum selection**, and **attention**, not causal creator skill.

## Confound layers (expanded panel)

| Layer | Clean | Confounded | Unknown / not clean |
| --- | ---: | ---: | ---: |
| Alpha Vantage (event flags) | 98 | 586 | 1,657 |
| Master confound (`reason_codes`, mutually exclusive) | 33 | 1,414 | 894 |

- **Non-top master-clean:** **n = 0** → public-news-clean robustness for non-top underperformance is **not validated**.
- **GDELT:** diagnostic only (~28% success rate).
- **Market-implied screen:** separate sensitivity layer; **not** public-news-clean.

## Completed defense passes

- Expanded Alpha Vantage metadata (partial; quota-limited)
- Calendar-time HAC factor regressions (French daily factors)
- Research-frontier mechanism modules (selection, attention, placebos, holdouts)
- **Information environment** (analyst relay + yfinance diagnostic layer, sentiment, narrative relay, originality taxonomy, incremental predictive value; Bloomberg validation planned)
- Public repo audit, local asset manifest, safety audit
- Claim discipline table, primary/secondary/exploratory hierarchy, final reader guides

## What we are **not** claiming

- Broad alpha
- Causal creator skill
- Tradable strategy
- Full public-news-clean identification
