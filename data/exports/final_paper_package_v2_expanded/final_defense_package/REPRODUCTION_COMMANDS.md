# Reproduction commands (RunPod authoritative)

```bash
cd /workspace/FIN496CAPSTONE
.venv/bin/python3 scripts/validate_expanded_primary_sample_package.py
.venv/bin/python3 scripts/build_v2_public_repo_audit.py
.venv/bin/python3 scripts/build_v2_local_asset_manifest.py
.venv/bin/python3 scripts/audit_public_repo_safety.py
.venv/bin/python3 scripts/build_v2_market_implied_confound_screen.py
.venv/bin/python3 scripts/build_v2_holdout_predictive_validity.py
.venv/bin/python3 scripts/build_v2_multiple_testing_and_inference_audit.py
.venv/bin/python3 scripts/build_v2_placebo_matched_control_expansion.py
.venv/bin/python3 scripts/build_v2_finalize_public_package.py
```

Alpha Vantage key: `/root/.config/fin496/alphavantage.env` only — never commit.
