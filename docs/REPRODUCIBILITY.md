# Reproducibility

Authoritative builds: RunPod at `/workspace/FIN496CAPSTONE` with Alpha Vantage key only in `/root/.config/fin496/alphavantage.env`.

Core checks: `python3 scripts/validate_expanded_primary_sample_package.py`, `python3 scripts/validate_locked_sample_manifest.py`, `ruff check .`, `pytest -q`.

New defense scripts: `build_v2_alpha_vantage_news_expanded.py`, `build_v2_master_confound_panel_expanded.py`, `build_v2_calendar_time_factor_regressions.py`, `audit_v2_recommendation_event_quality_deep.py`, `build_v2_long_horizon_claim_controls.py`, `build_v2_critical_defense_docs.py`.

Do not commit secrets, raw DBs, raw transcripts, raw API responses, or article bodies.
