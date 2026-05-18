# Analyst Coverage Missing Note

## Check Performed

- Checked `data/manual/bloomberg_validation/` for raw Bloomberg workbook files on RunPod. No workbook files were present in that path.
- Checked the repository for tracked or local `.xlsx` / `.xls` files under `data/`. None were present.
- Checked `data/exports/final_paper_package_v2_expanded/bloomberg_validation/bloomberg_field_coverage_summary.csv`. The current derived coverage summary records `Analyst_coverage` / `TOT_ANALYST_REC` as `expected_missing_analyst_coverage`.
- Checked `bloomberg_long_panel.csv`; `TOT_ANALYST_REC` is not present in the parsed long panel.

## Result

Analyst coverage count remains unavailable. No analyst coverage count claim was added, and no Bloomberg derived outputs were regenerated from raw data.

## Required Future Input

To add analyst coverage later, the raw Bloomberg workbook must contain a populated `Analyst_coverage` sheet or another usable `TOT_ANALYST_REC` field with ticker/date/value observations. The field should be parsed as missing when Bloomberg returns blanks or `#N/A` values; missing values must not be converted to zero.
