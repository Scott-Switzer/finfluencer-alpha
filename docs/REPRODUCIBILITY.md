# Reproducibility

Use RunPod as the authoritative execution environment. Validation commands are `python3 scripts/validate_expanded_primary_sample_package.py`, `python3 scripts/validate_locked_sample_manifest.py`, `ruff check .`, and `pytest -q`. Do not commit secrets, raw DBs, raw transcripts, raw API responses, or article bodies.
