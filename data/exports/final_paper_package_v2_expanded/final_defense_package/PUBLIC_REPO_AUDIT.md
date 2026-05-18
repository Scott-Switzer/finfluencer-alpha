# Public repository audit

| Item | Value |
| --- | --- |
| Local branch | `main` |
| Local HEAD | `435d35560246d87b5dd8b209852e49853c636eac` |
| Origin `x-youtube-full-research-expansion` | `3c607642fa3386843829ea9cc27bb0cdb615b54a` |
| Origin `main` | `435d35560246d87b5dd8b209852e49853c636eac` |
| Main stale vs research | **True** |
| README on research branch current | **True** |
| README on origin/main current | **True** |
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
