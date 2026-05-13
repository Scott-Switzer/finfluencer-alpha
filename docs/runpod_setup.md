# RunPod Environment Setup

This guide documents the reproducible Python environment setup for the RunPod workspace.

## Paths

- **Repository**: `/workspace/FIN496CAPSTONE`
- **Virtual environment**: `/workspace/FIN496CAPSTONE/.venv`
- **Pip cache**: `/workspace/.pip-cache`

## One-Time Setup

```bash
cd /workspace/FIN496CAPSTONE
mkdir -p /workspace/.pip-cache
python3 -m venv /workspace/FIN496CAPSTONE/.venv
. /workspace/FIN496CAPSTONE/.venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
PIP_CACHE_DIR=/workspace/.pip-cache pip install -e ".[dev]"
```

## Activate Environment

```bash
. /workspace/FIN496CAPSTONE/.venv/bin/activate
```

## Validation

```bash
cd /workspace/FIN496CAPSTONE
ruff check .
pytest tests/
```

## Hard Rules

- **Do not commit `.env`** — it contains secrets.
- **Do not commit `*.db`** — databases are local artifacts.
- **Do not commit raw data, backups, logs, or caches.**
- Use `--only-missing-transcripts` for collection to avoid overwriting existing transcripts.
- Use cost caps (`--max-total-charge-usd`, `--total-cost-cap-usd`) on every Apify run.
