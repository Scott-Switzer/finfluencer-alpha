# Bloomberg Validation Derived Outputs

- Source workbook read: `data/manual/bloomberg_validation/FIN496_BLOOMBERG_ALL TICKERS_STATIC.xlsx`
- Output directory: `data/exports/final_paper_package_v2_expanded/bloomberg_validation`
- Long valid observations: 848,776
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
- Analyst coverage counts are not included yet because the `Analyst_coverage` sheet is blank.
- News Heat and News Sentiment are Bloomberg news-flow proxies, not manual headline audits.

## Parser Notes

- Legacy BDH/BDX sheets use row 12 ticker blocks and row 15 onward observations.
- Incremental BDH sheets use row 8 ticker blocks and row 10 onward observations.
- Excel serial dates are converted from the 1899-12-30 epoch.
- Bloomberg errors, blanks, and `#N/A N/A` values are treated as missing, never zero.
- Tickers are standardized from Bloomberg securities and the repo ticker alias file; no unsupported manual aliases are applied.

## Skipped Sheet Status

- expected_missing_analyst_coverage
