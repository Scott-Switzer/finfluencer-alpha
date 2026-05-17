# Project status

**Last frozen research HEAD:** see `git rev-parse HEAD` on `main`

## Primary sample

- **v2 expanded** is the primary empirical sample: **2,341** accepted recommendation events.
- **v1** locked package is preserved as a historical benchmark only.

## Headline conclusion

The evidence does **not** support broad short-window YouTube alpha or a tradable finfluencer strategy. The defensible story is **heterogeneous return dynamics** driven by **ticker concentration**, **momentum selection**, and **attention**, not causal creator skill.

## Confound layers (expanded panel)

| Layer | Clean / usable | Confounded / hit | Unknown / not clean |
| --- | ---: | ---: | ---: |
| Alpha Vantage (event flags) | 98 | 586 | 1,657 |
| Multi-provider news master | 0 multi_source_clean | 1,102 official + 322 media + 118 market-implied | 799 |

- **Non-top multi_source_clean:** **n = 0** → public-news-clean robustness for non-top underperformance is **not validated**.
- **GDELT:** diagnostic only (~28% success rate).
- **Market-implied screen:** separate sensitivity layer; **not** public-news-clean.

## Completed defense passes

- Expanded Alpha Vantage metadata (partial; quota-limited)
- Calendar-time HAC factor regressions (French daily factors)
- Research-frontier mechanism modules (selection, attention, placebos, holdouts)
- **Information environment** (analyst relay + yfinance diagnostic layer, sentiment, narrative relay, originality taxonomy, incremental predictive value; Bloomberg validation planned)
- Analyst grade normalization reduces event-time alignment unknowns, but it only improves descriptive relay classification; current yfinance snapshots remain diagnostic and unknown analyst/news coverage is never clean
- Public repo audit, local asset manifest, safety audit
- Claim discipline table, primary/secondary/exploratory hierarchy, final reader guides

## What we are **not** claiming

- Broad alpha
- Causal creator skill
- Tradable strategy
- Full public-news-clean identification
- yfinance current snapshots as event-time analyst evidence
- Grade-normalized analyst relay as causal evidence
- Top-5 raw positives as creator skill rather than concentration / consensus / attention
