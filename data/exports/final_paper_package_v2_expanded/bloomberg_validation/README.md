# Bloomberg Validation Derived Outputs

- Source workbook read: `data/manual/bloomberg_validation/FIN496_BLOOMBERG_ALL TICKERS_STATIC.xlsx`
- Supplemental analyst coverage workbook: `data/manual/bloomberg_validation/analyst_coverage.xlsx` (supplemental_workbook)
- Output directory: `data/exports/final_paper_package_v2_expanded/bloomberg_validation`
- Long valid observations: 861,811
- Daily market panel rows: 87,375
- Weekly analyst/estimate panel rows: 13,937
- Accepted events matched: 2,341

## Scope

This folder is a derived Bloomberg validation layer for final-paper work. It is not a broad rebuild of project outputs.

## Interpretation Rules

- Bloomberg data are an institutional validation and mechanism layer.
- Do not claim causality.
- Do not claim public-news-clean alpha.
- Do not claim creator skill.
- Do not claim tradability.
- Analyst coverage is institutional-following context, not proof that creators copied analysts.
- News Heat and News Sentiment are Bloomberg news-flow proxies, not manual headline audits.

## Parser Notes

- Legacy BDH/BDX sheets use row 12 ticker blocks and row 15 onward observations.
- Incremental BDH sheets use row 8 ticker blocks and row 10 onward observations.
- Excel serial dates are converted from the 1899-12-30 epoch.
- Bloomberg errors, blanks, and `#N/A N/A` values are treated as missing, never zero.
- Tickers are standardized from Bloomberg securities and the repo ticker alias file; no unsupported manual aliases are applied.
