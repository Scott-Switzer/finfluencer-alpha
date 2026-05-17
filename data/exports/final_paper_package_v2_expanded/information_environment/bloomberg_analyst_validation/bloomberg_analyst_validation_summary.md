# Bloomberg Analyst Validation

# SKIPPED

No Bloomberg private exports found.

Expected optional files under `data/private/bloomberg/`:
- `analyst_recommendations_export.csv` — columns: ticker, date, recommendation, broker, target_price
- `price_target_history_export.csv` — columns: ticker, date, target_price, consensus_rating
- `earnings_estimate_revisions_export.csv` — columns: ticker, date, revision_type, eps_estimate

Future command:
```bash
.venv/bin/python3 scripts/build_v2_bloomberg_analyst_import_adapter.py
```
