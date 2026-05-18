# Claim Discipline Table

| Claim area | Allowed wording | Prohibited wording |
| --- | --- | --- |
| Analyst relay | Dated pre-event analyst records support exploratory relay classifications | Analyst evidence proves creator causality |
| yfinance | yfinance improves diagnostic coverage; dated pre-event rows may be event-time usable | Current yfinance snapshots are historical event-time proof |
| Grade normalization | Normalized grade strings reduce analyst_unknown classifications | Grade mapping establishes skill, causality, or tradability |
| Unknown coverage | Unknown analyst/news coverage is unresolved and not clean | Unknown means no confounding information |
| Bloomberg | Bloomberg validation is included as a descriptive mechanism/context layer; `TOT_ANALYST_REC` remains unavailable | Bloomberg proves causality, public-news-clean alpha, creator skill, or tradability |
| Public-news-clean | Multi-provider clean status is unavailable in the current RunPod build | Non-top weakness survives clean-news controls |
| Top-5 positives | Top-5 raw positives are consistent with concentration, consensus, and attention | Top-5 results prove creator skill |
| Non-top weakness | Non-top weakness is a medium-horizon descriptive pattern | Non-top weakness is automatically public-news-clean |

## May 2026 — news layer and claim discipline (RunPod)

- **No broad tradable YouTube alpha**; heterogeneity and salience matter more than uniform creator skill.
- **Top-5 raw positives** reflect concentration, consensus relay, and attention—not causal creator skill.
- **Non-top weakness** is **not** automatically public-news-clean; **unknown_news_coverage is never clean**.
- **multi_source_clean** is strict (may be zero); provider failures, **403/429**, missing keys, and shallow history are **not** “no news.”
- **FNSPID** adds historical *media* coverage (not official disclosure) through about 2023 but does not cover every recent event window.
- **Marketaux, EODHD, Alpaca/Benzinga, Massive/Polygon, NewsAPI** are free-tier **diagnostic** supplements; **NewsAPI** developer tiers are not a historical backbone.
- **yfinance** analyst snapshots in this repo are **diagnostic only** unless dated pre-event rows exist; they are **not** Bloomberg-grade validation.
- Report **news sensitivity bounds** because public-news identification remains incomplete; frame conclusions as **mechanism-consistent**, not causal.


