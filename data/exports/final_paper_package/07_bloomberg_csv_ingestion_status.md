# Bloomberg CSV Ingestion Status

No Bloomberg API was used. This validation checks only manual CSV templates/exports.

| File | Exists | Rows | Schema valid | Status |
| --- | --- | ---: | --- | --- |
| `bloomberg_price_template.csv` | True | 0 | True | template_only |
| `bloomberg_news_template.csv` | True | 0 | True | template_only |
| `bloomberg_corporate_actions_template.csv` | True | 0 | True | template_only |
| `bloomberg_earnings_template.csv` | True | 0 | True | template_only |
| `bloomberg_analyst_actions_template.csv` | True | 0 | True | template_only |

Current yfinance/free-data results are not overwritten by these files.
If manual Bloomberg CSVs are later populated, rerun this validator first,
then explicitly rerun the empirical package with a Bloomberg-source option.
