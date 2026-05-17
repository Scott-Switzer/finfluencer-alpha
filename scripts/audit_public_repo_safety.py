"""Audit tracked files for size, secrets, and policy violations."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

DEF = utils.OUT_DIR / "final_defense_package"
SECRET_RE = re.compile(
    r"(ALPHAVANTAGE_API_KEY\s*=\s*[A-Z0-9]{8,}|apikey=[A-Z0-9]{8,}|BEGIN PRIVATE KEY)",
    re.I,
)
FAKE_MARKERS = ("REDACTED", "fake", "fixture", "test_", "BEUALTZC89CXIMHA")  # last is test-only redaction target


def tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def main() -> int:
    rows: list[dict] = []
    for rel in tracked_files():
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        size = path.stat().st_size
        issue = []
        if size > 100 * 1024 * 1024:
            issue.append("size>100MB")
        elif size > 50 * 1024 * 1024:
            issue.append("size>50MB")
        elif size > 25 * 1024 * 1024:
            issue.append("size>25MB")
        low = rel.lower()
        if (".env" in low or low.endswith(".save")) and "example" not in low:
            issue.append("env_like")
        if low.endswith(".log"):
            issue.append("log")
        if low.endswith((".db", ".sqlite")):
            issue.append("database")
        if "article_metadata_cache" in low or "raw/api" in low:
            issue.append("bulky_cache_or_api")
        if "transcript" in low and low.endswith((".json", ".csv", ".txt")) and size > 5_000_000:
            issue.append("large_transcript_like")

        secret_hit = False
        if path.suffix in {".py", ".md", ".csv", ".json", ".yml", ".yaml", ".sh"} and size < 5_000_000:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if SECRET_RE.search(text):
                    if "test_" in low or "REDACTED" in text or "fake" in text.lower():
                        issue.append("secret_pattern_test_or_redacted")
                    else:
                        issue.append("secret_pattern_REAL_RISK")
                        secret_hit = True
            except OSError:
                pass

        rows.append(
            {
                "path": rel,
                "size_mb": round(size / (1024 * 1024), 3),
                "issues": ";".join(issue) if issue else "ok",
                "real_risk": secret_hit
                or ("env_like" in issue and "example" not in rel.lower())
                or "database" in issue,
            }
        )

    risks = [r for r in rows if r.get("real_risk") or (r["issues"] != "ok" and "test_or_redacted" not in r["issues"])]
    utils.write_csv(DEF / "PUBLIC_REPO_SAFETY_AUDIT.csv", rows, list(rows[0]) if rows else ["path"])
    utils.write_md(
        DEF / "PUBLIC_REPO_SAFETY_AUDIT.md",
        "Public Repo Safety Audit",
        f"Tracked files: **{len(rows)}**. Flagged: **{len(risks)}**.\n\n"
        + utils.md_table(risks[:50] if risks else [{"status": "no_material_risks"}]),
    )
    real = [r for r in rows if r.get("real_risk")]
    print(f"Safety audit: {len(rows)} tracked, {len(real)} real risks")
    return 1 if real else 0


if __name__ == "__main__":
    raise SystemExit(main())
