# Reproducibility

## Quick validation (public clone)

```bash
python3 scripts/validate_expanded_primary_sample_package.py
python3 scripts/validate_locked_sample_manifest.py
python -m ruff check .
pytest -q
```

Expected: expanded sample validator **PASS**; locked manifest may show **PARTIAL** warnings for v1 artifacts.

## Authoritative environment

| Item | Location |
| --- | --- |
| Workspace | `/workspace/FIN496CAPSTONE` (RunPod) |
| Database | `data/finfluencer_alpha.db` (private, not in git) |
| Alpha Vantage key | `/root/.config/fin496/alphavantage.env` (never commit) |

## Full rebuild command list

See `data/exports/final_paper_package_v2_expanded/final_defense_package/REPRODUCTION_COMMANDS.md`.

Core defense builders include:

- `build_v2_alpha_vantage_news_expanded.py`
- `build_v2_master_confound_panel_expanded.py`
- `build_v2_calendar_time_factor_regressions.py`
- `build_v2_placebo_matched_control_expansion.py`
- `build_v2_finalize_public_package.py`

## Public vs private

- **Public repo:** scripts + committed CSV/MD exports
- **Private:** DB, raw transcripts, API keys, bulky news caches

See `docs/DATA_AVAILABILITY.md` and `LOCAL_ASSET_MANIFEST.md`.

## Safety

Do not commit secrets, raw databases, raw transcripts, raw API responses, or article bodies.
