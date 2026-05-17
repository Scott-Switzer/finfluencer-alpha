# Reproduction commands

```bash
ruff check .
pytest -q
python3 scripts/build_v2_alpha_vantage_news_expanded.py --resume   # RunPod w/ AV key
python3 scripts/build_v2_master_confound_panel_expanded.py
python3 scripts/build_v2_calendar_time_factor_regressions.py
python3 scripts/audit_v2_recommendation_event_quality_deep.py
python3 scripts/build_v2_long_horizon_claim_controls.py
python3 scripts/build_v2_critical_defense_docs.py
python3 scripts/validate_expanded_primary_sample_package.py
```

Alpha Vantage key must never be committed; on RunPod use `/root/.config/fin496/alphavantage.env` only.
