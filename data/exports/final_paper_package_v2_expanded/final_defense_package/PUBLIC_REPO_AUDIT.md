# Public repository audit

| Item | Value |
| --- | --- |
| Local branch | `x-youtube-full-research-expansion` |
| Local HEAD | `94241e2672e18beb8feafbf89f66aae940a2c64c` |
| Origin `x-youtube-full-research-expansion` | `94241e2672e18beb8feafbf89f66aae940a2c64c` |
| Origin `main` | `bffb993dae4de25e5687c56a98c0c88fecf2c405` |
| Main stale vs research | **True** |
| README on research branch current | **True** |
| README on origin/main current | **False** |
| `docs/` present | **True** |
| Final defense package present | **True** |
| Risky tracked paths (env/db/cache) | **1** |
| **Promote research → main recommended** | **False** |

## Tracked risk sample
- `.env.example`

## Notes
- Public repo should expose **committed CSV/MD exports** under `data/exports/final_paper_package_v2_expanded/` (force-added where gitignored).
- Private assets: DB, raw transcripts, API keys, article caches — **not** in git (see `LOCAL_ASSET_MANIFEST.md`).
- Unknown news coverage must **never** be coded as clean.
