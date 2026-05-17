# Data availability

## What is in the public GitHub repository

The public repo is designed for **reproducible tables and defensible claims**, not for redistributing raw proprietary content.

| Category | Location | Notes |
| --- | --- | --- |
| Primary empirical exports | `data/exports/final_paper_package_v2_expanded/` | CSV/MD summaries (force-added where gitignored) |
| Locked v2 manifests | `locked_sample_v2/` | Event manifest, transcript manifest |
| Defense package | `final_defense_package/` | Claim matrix, reader guide, reproduction commands |
| Scripts | `scripts/` | Rebuild pipelines (require private inputs) |
| Historical v1 package | `data/exports/final_paper_package/` | Benchmark only; not primary sample |

## What is **not** in the public repository

| Asset | Why withheld |
| --- | --- |
| `data/finfluencer_alpha.db` | Private transcript/event database |
| Raw / interim / processed transcripts | Copyright and size |
| `.env`, API keys | Security |
| Alpha Vantage article metadata caches | Bulky; may contain copyrighted headlines |
| RunPod-only logs and checkpoints | Operational artifacts |

See `final_defense_package/LOCAL_ASSET_MANIFEST.md` for a hashed inventory (no file contents).

## Authoritative build environment

Full regeneration of all panels requires:

- RunPod workspace: `/workspace/FIN496CAPSTONE`
- Private SQLite database on the pod
- Market import CSV under `data/imports/market_data/`
- Alpha Vantage key in `/root/.config/fin496/alphavantage.env` only (never commit)

## Policy reminders

- **Unknown** public-news coverage is **never** coded as clean.
- **504D** horizons are **diagnostic only** unless full-window support is materially proven.
- Results are **not** investment advice.
