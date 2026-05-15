#!/usr/bin/env python3
"""Prepare a local backup bundle before RunPod shutdown."""
from __future__ import annotations

import os
import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = ROOT / "data" / "backups"
DEFAULT_MAX_MB = 50


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _collect_candidates() -> list[Path]:
    candidates: list[Path] = []
    db = ROOT / "data" / "finfluencer_alpha.db"
    if db.exists():
        candidates.append(db)

    export_patterns = [
        "data/exports/overnight_collection/*.md",
        "data/exports/overnight_collection/*.csv",
        "data/exports/overnight_collection/*.json",
        "data/exports/transcript_*",
        "data/exports/reporting/*.md",
        "data/exports/reporting/*.csv",
    ]
    for pat in export_patterns:
        candidates.extend(p for p in ROOT.glob(pat) if p.is_file())

    ledger = ROOT / "data" / "exports" / "overnight_collection" / "apify_key_usage_ledger.csv"
    if ledger.exists():
        candidates.append(ledger)

    logs_dir = ROOT / "data" / "logs"
    if logs_dir.exists():
        candidates.extend(p for p in logs_dir.glob("*.log") if p.is_file())

    blocked_names = {".env"}
    unique: dict[str, Path] = {}
    for p in candidates:
        if p.name in blocked_names:
            continue
        unique[str(p.resolve())] = p
    return sorted(unique.values(), key=lambda p: _rel(p))


def _copy_file(src: Path, dst_root: Path, max_bytes: int) -> tuple[bool, str]:
    size = src.stat().st_size
    if size > max_bytes:
        return False, f"skipped_too_large:{size}"
    rel = src.relative_to(ROOT)
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True, f"copied:{size}"


def main() -> None:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _ts()
    backup_root = BACKUPS_DIR / f"runpod_shutdown_{stamp}"
    files_root = backup_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    max_mb = int(os.getenv("RUNPOD_BACKUP_MAX_FILE_MB", str(DEFAULT_MAX_MB)) or DEFAULT_MAX_MB)
    max_bytes = max_mb * 1024 * 1024

    manifest_rows: list[str] = []
    copied = 0
    skipped = 0
    for src in _collect_candidates():
        ok, note = _copy_file(src, files_root, max_bytes)
        if ok:
            copied += 1
        else:
            skipped += 1
        manifest_rows.append(f"- `{_rel(src)}` -> `{note}`")

    manifest = [
        "# RunPod shutdown backup manifest",
        "",
        f"Generated UTC: `{datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}`",
        f"Backup root: `{_rel(backup_root)}`",
        f"Copied files: `{copied}`",
        f"Skipped files: `{skipped}`",
        f"Per-file cap MB: `{max_mb}`",
        "",
        "## File entries",
        "",
        *manifest_rows,
        "",
        "## Exclusions",
        "",
        "- `.env` and any secret files",
        "- raw transcript dumps / huge raw payloads above configured cap",
        "- virtual environments, caches, `.git`, `__pycache__`",
        "",
    ]
    (backup_root / "MANIFEST.md").write_text("\n".join(manifest), encoding="utf-8")

    restore = [
        "# Restore notes",
        "",
        "1. Copy `files/` contents back to the same repo-relative paths.",
        "2. Reinstall dependencies and confirm environment variables are set locally.",
        "3. Resume with the latest commit and run status markdown/JSON from overnight collection.",
        "",
        "Do not commit DB or full transcript raw content to GitHub.",
    ]
    (backup_root / "RESTORE_NOTES.md").write_text("\n".join(restore), encoding="utf-8")

    tar_path = BACKUPS_DIR / f"runpod_shutdown_{stamp}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(backup_root, arcname=backup_root.name)

    print(f"BACKUP_DIR={_rel(backup_root)}")
    print(f"BACKUP_TAR={_rel(tar_path)}")


if __name__ == "__main__":
    main()
