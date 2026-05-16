# V2 SEC Event Flags

| event_id | ticker | company_name | event_date | window_pm1 | window_pm3 | window_pm5 | filing_count_pm1 | filing_count_pm3 | filing_count_pm5 | material_filing_flag_pm1 | material_filing_flag_pm3 | material_filing_flag_pm5 | material_form_types | nearest_filing_date | nearest_form_type | sec_confounded_flag | sec_clean_flag | query_status | reason_codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TSLA | Tesla | 2023-10-13 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 2 | 3 | False | True | True | 8-K;8-K/A | 2023-10-11 | 4 | True | False | ok | material_filing_pm5 |
| 2 | GOOGL | Alphabet | 2023-10-13 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 2 | 2 | False | False | False |  | 2023-10-10 | 4 | False | True | ok |  |
| 3 | AMZN | Amazon | 2023-06-23 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 2 | 3 | 3 | False | False | False |  | 2023-06-23 | 4 | False | True | ok |  |
| 4 | NVDA | Nvidia | 2023-06-23 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 6 | 8 | 21 | False | False | True | 8-K | 2023-06-23 | 4 | True | False | ok | material_filing_pm5 |
| 5 | TSLA | Tesla | 2023-06-23 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 1 | False | False | False |  | 2023-06-27 | 144 | False | True | ok |  |
| 6 | PYPL | PayPal | 2026-03-07 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 3 | 14 | False | False | False |  | 2026-03-04 | 4 | False | True | ok |  |
| 7 | MSFT | Microsoft | 2026-02-06 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 11 | 11 | False | False | False |  | 2026-02-03 | 4 | False | True | ok |  |
| 8 | UBER | Uber | 2026-02-06 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 2 | 2 | False | True | True | 8-K | 2026-02-04 | 8-K | True | False | ok | material_filing_pm5 |
| 9 | NVDA | Nvidia | 2026-02-06 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 1 | 1 | 1 | False | False | False |  | 2026-02-06 | 4 | False | True | ok |  |
| 10 | NFLX | Netflix | 2026-02-06 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 3 | 23 | 31 | False | False | False |  | 2026-02-06 | 4 | False | True | ok |  |
| 11 | NFLX | Netflix | 2023-02-10 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 0 | False | False | False |  | 2023-03-02 | 4 | False | True | ok |  |
| 12 | AMZN | Amazon | 2023-06-16 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 1 | False | False | False |  | 2023-06-21 | 144 | False | True | ok |  |
| 13 | NFLX | Netflix | 2023-06-16 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 0 | False | False | False |  | 2023-06-09 | 4 | False | True | ok |  |
| 14 | NVDA | Nvidia | 2023-06-16 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 4 | 8 | 10 | False | False | False |  | 2023-06-16 | 144 | False | True | ok |  |
| 15 | TSLA | Tesla | 2023-06-16 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 1 | 3 | 3 | False | False | False |  | 2023-06-16 | 4 | False | True | ok |  |
| 16 | GOOGL | Alphabet | 2024-01-08 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 3 | 9 | False | False | False |  | 2024-01-10 | 4 | False | True | ok |  |
| 17 | TSLA | Tesla | 2024-01-08 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 0 | False | False | False |  | 2024-01-02 | 8-K | False | True | ok |  |
| 18 | TSLA | Tesla | 2023-08-18 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 0 | False | False | False |  | 2023-08-28 | 144 | False | True | ok |  |
| 19 | AAPL | Apple | 2023-08-18 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 0 | False | False | False |  | 2023-08-08 | 4 | False | True | ok |  |
| 20 | AMZN | Amazon | 2023-03-03 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 3 | 3 | 3 | False | False | False |  | 2023-03-03 | 4 | False | True | ok |  |
| 21 | NVDA | Nvidia | 2025-08-27 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 2 | 4 | 4 | True | True | True | 10-Q;8-K | 2025-08-27 | 10-Q | True | False | ok | material_filing_pm5 |
| 22 | NVDA | Nvidia | 2025-08-27 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 2 | 4 | 4 | True | True | True | 10-Q;8-K | 2025-08-27 | 10-Q | True | False | ok | material_filing_pm5 |
| 23 | DIS | Disney | 2023-10-06 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 10 | 10 | False | False | False |  | 2023-10-03 | 4 | False | True | ok |  |
| 24 | AMD |  | 2023-10-06 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 1 | 1 | False | False | False |  | 2023-10-04 | CORRESP | False | True | ok |  |
| 25 | MSFT | Microsoft | 2023-10-06 | [-1,+1] calendar days | [-3,+3] calendar days | [-5,+5] calendar days | 0 | 0 | 1 | False | False | True | 8-K | 2023-10-11 | 8-K | True | False | ok | material_filing_pm5 |

Preview only; full compact metadata is in the CSV.
