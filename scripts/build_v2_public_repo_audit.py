"""Generate PUBLIC_REPO_AUDIT.md for research vs main branch posture."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEF = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded" / "final_defense_package"


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def tracked_files() -> set[str]:
    out = run(["git", "ls-files"])
    return set(out.splitlines()) if out else set()


def main() -> int:
    local_head = run(["git", "rev-parse", "HEAD"])
    branch = run(["git", "branch", "--show-current"])
    research_head = run(["git", "ls-remote", "origin", "x-youtube-full-research-expansion"]).split()[0]
    main_head = run(["git", "ls-remote", "origin", "main"]).split()[0]
    main_stale = main_head != research_head

    readme_main = ""
    try:
        readme_main = run(["git", "show", "origin/main:README.md"])
    except Exception:
        readme_main = ""

    readme_branch = (REPO_ROOT / "README.md").read_text(encoding="utf-8") if (REPO_ROOT / "README.md").exists() else ""
    readme_current = "Research-frontier" in readme_branch and "2,341" in readme_branch
    readme_main_stale = "2,341" not in readme_main if readme_main else True

    tracked = tracked_files()
    risky = [p for p in tracked if any(x in p.lower() for x in (".env", ".db", ".sqlite", ".save", "article_metadata_cache"))]
    docs_ok = all((REPO_ROOT / f"docs/{d}").exists() for d in ["PROJECT_STATUS.md", "CLAIM_MATRIX.md", "REPRODUCIBILITY.md"])
    defense_ok = DEF.exists() and (DEF / "FINAL_CLAIM_MATRIX.md").exists()

    promote = main_stale and readme_current and not risky and defense_ok

    body = f"""# Public repository audit

| Item | Value |
| --- | --- |
| Local branch | `{branch}` |
| Local HEAD | `{local_head}` |
| Origin `x-youtube-full-research-expansion` | `{research_head}` |
| Origin `main` | `{main_head}` |
| Main stale vs research | **{main_stale}** |
| README on research branch current | **{readme_current}** |
| README on origin/main current | **{not readme_main_stale}** |
| `docs/` present | **{docs_ok}** |
| Final defense package present | **{defense_ok}** |
| Risky tracked paths (env/db/cache) | **{len(risky)}** |
| **Promote research → main recommended** | **{promote}** |

## Tracked risk sample
{chr(10).join(f'- `{p}`' for p in risky[:20]) or '- none detected'}

## Notes
- Public repo should expose **committed CSV/MD exports** under `data/exports/final_paper_package_v2_expanded/` (force-added where gitignored).
- Private assets: DB, raw transcripts, API keys, article caches — **not** in git (see `LOCAL_ASSET_MANIFEST.md`).
- Unknown news coverage must **never** be coded as clean.
"""
    DEF.mkdir(parents=True, exist_ok=True)
    (DEF / "PUBLIC_REPO_AUDIT.md").write_text(body, encoding="utf-8")
    print("PUBLIC_REPO_AUDIT.md written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
