# Limitations and threats

## Public news and analyst data

- Partial Alpha Vantage metadata (~4 tickers under quota); **1,657+ events unknown** — **unknown is never clean**.
- **Non-top master-clean n = 0** — cannot claim public-news-clean non-top robustness.
- GDELT is **diagnostic only** (~28% success); not confirmatory.
- **Analyst relay:** FMP/Finnhub optional; undated consensus is **diagnostic_current_only** only.
- **Analyst unknown ≠ clean** — same discipline as news unknown.

## Market-implied vs news-clean

- `market_quiet` flags low pre-event return/volume — **not** absence of Bloomberg/analyst/earnings news.
- Non-top + market_quiet 21D ≈ **-0.56%** is a **sensitivity** slice, not identification.

## Sample and methods

- Overlapping events by ticker/creator; automated classification with proxy QA only.
- Long horizons overlap-prone and right-censored; **504D diagnostic only** when thin.
- yfinance / French factors are student-grade — not a Bloomberg replication.
- Evidence-window language scores are **snippet-based** — not full transcript audit.

## Inference

- Exploratory predictive AUCs (including non-top underperform) can be **ticker-driven** under ticker-out holdouts.
- BH FDR survival (57/73) does **not** upgrade exploratory modules to primary claims — see `PRIMARY_SECONDARY_EXPLORATORY_HIERARCHY.md`.

## Threats to interpretation

- **Repackaging hypothesis:** finfluencer content may relay visible analyst/macro narratives.
- **Attention/noise:** hype/urgency language may attract views without incremental information.
- **Salience:** top-5 concentration drives much of the raw short-window signal.
