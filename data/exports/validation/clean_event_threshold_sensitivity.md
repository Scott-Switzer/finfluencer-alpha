# Clean Event Threshold Sensitivity

- Source auto-labeled validation file: `data/exports/validation/event_validation_sample_auto_labeled.csv`
- CSV output: `data/exports/validation/clean_event_threshold_sensitivity.csv`
- Total auto-labeled rows: 524

| Min confidence | Strict included | With review | With weak evidence | Excluded | Unique tickers | Unique creators |
|---:|---:|---:|---:|---:|---:|---:|
| 0.90 | 73 | 73 | 73 | 451 | 13 | 14 |
| 0.85 | 94 | 94 | 94 | 430 | 14 | 16 |
| 0.80 | 130 | 130 | 130 | 394 | 15 | 17 |
| 0.75 | 132 | 132 | 132 | 392 | 16 | 17 |
| 0.70 | 132 | 156 | 132 | 392 | 16 | 17 |
| 0.65 | 132 | 157 | 132 | 392 | 16 | 17 |

Strict included rows require `is_true_recommendation=yes`, direction not `unclear`, strong or medium evidence, `auto_label_needs_review=false`, and confidence at or above the threshold.
