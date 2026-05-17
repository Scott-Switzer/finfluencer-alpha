"""Scan local/private vs public assets; hash paths only (no content)."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

DEF = utils.OUT_DIR / "final_defense_package"
DOCS = REPO_ROOT / "docs"

GLOBS = [
    "data/*.db",
    "data/**/*.db",
    "data/**/*.sqlite",
    "data/raw/**",
    "data/interim/**",
    "data/processed/**",
    "data/logs/**",
    "**/av_expanded_article_metadata_cache.csv",
    "**/03_av_compact_article_metadata.csv",
    "data/exports/final_paper_package_v2_expanded/**",
    "data/imports/market_data/yfinance_market_data.csv",
]


def git_tracked(rel: str) -> bool:
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def git_ignored(rel: str) -> bool:
    r = subprocess.run(
        ["git", "check-ignore", "-q", rel],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return r.returncode == 0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def categorize(rel: str) -> str:
    low = rel.lower()
    if low.endswith((".db", ".sqlite")):
        return "db_private"
    if "article_metadata_cache" in low or "03_av_compact" in low:
        return "cache_private"
    if "/raw/" in low or "/interim/" in low or "/processed/" in low:
        return "raw_private"
    if "/logs/" in low or low.endswith(".log"):
        return "log_private"
    if "final_paper_package_v2_expanded" in low and low.endswith((".csv", ".md")):
        return "final_public"
    if "imports/market_data" in low:
        return "derived_public"
    return "derived_public"


def safe_to_commit(rel: str, cat: str) -> tuple[bool, str]:
    if cat in {"db_private", "cache_private", "raw_private", "log_private"}:
        return False, "private or bulky; gitignored by policy"
    if ".env" in rel or rel.endswith(".save"):
        return False, "secret risk"
    if cat == "final_public" and git_tracked(rel):
        return True, "committed export artifact"
    if cat == "final_public":
        return True, "export artifact; may require git add -f"
    if cat == "derived_public":
        return False, "rebuild from yfinance import scripts on RunPod"
    return False, "default private"


def rebuild_cmd(rel: str) -> str:
    if "finfluencer_alpha.db" in rel:
        return "Built on RunPod from transcript pipeline (not in public repo)"
    if "yfinance_market_data" in rel:
        return "python3 scripts/import_yfinance_market_data.py (RunPod)"
    if "final_paper_package_v2_expanded" in rel:
        return "See REPRODUCTION_COMMANDS.md / scripts/build_expanded_primary_sample_package.py"
    return ""


def main() -> int:
    seen: set[Path] = set()
    rows: list[dict] = []
    for pattern in GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            rel = path.relative_to(REPO_ROOT).as_posix()
            size = path.stat().st_size
            cat = categorize(rel)
            safe, reason = safe_to_commit(rel, cat)
            rows.append(
                {
                    "relative_path": rel,
                    "exists": True,
                    "git_tracked": git_tracked(rel),
                    "git_ignored": git_ignored(rel),
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 3),
                    "sha256": sha256_file(path),
                    "category": cat,
                    "safe_to_commit": safe,
                    "reason": reason,
                    "required_for_reproduction": cat in {"db_private", "derived_public"},
                    "replacement_or_rebuild_command": rebuild_cmd(rel),
                }
            )

    rows.sort(key=lambda r: r["relative_path"])
    utils.write_csv(DEF / "LOCAL_ASSET_MANIFEST.csv", rows, list(rows[0]) if rows else ["relative_path"])
    utils.write_md(
        DEF / "LOCAL_ASSET_MANIFEST.md",
        "Local Asset Manifest",
        f"Scanned **{len(rows)}** files. Hashes only; no content exported.\n\n"
        + utils.md_table(rows[:40], limit=40)
        + ("\n\n*(truncated; see CSV)*" if len(rows) > 40 else ""),
    )

    avail = """# Data availability

## In the public GitHub repository
- Committed **CSV/MD** exports under `data/exports/final_paper_package_v2_expanded/` (tables, summaries, defense package).
- Scripts to rebuild panels when the private RunPod database and market imports exist.
- Locked v2 event manifest and return panels derived from the authoritative build.

## Not in the public repository (local / RunPod private)
- `data/finfluencer_alpha.db` — transcript and event source database.
- Raw/interim/processed transcript files under `data/raw/`, `data/interim/`, `data/processed/`.
- Alpha Vantage article metadata caches (bulky; may contain copyrighted headlines).
- `.env` / API keys — use `/root/.config/fin496/alphavantage.env` on RunPod only.

## Reproducing full results
Run on RunPod with the private DB and market CSV. See `final_defense_package/REPRODUCTION_COMMANDS.md`.
Unknown public-news states are **never** treated as clean.
"""
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "DATA_AVAILABILITY.md").write_text(avail.strip() + "\n", encoding="utf-8")
    print(f"Local asset manifest: {len(rows)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
