"""Emit gap audit artifacts for news/confound and reproducibility review."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import v2_critical_defense_utils as utils  # noqa: E402

MAC_PATH_HINT = re.compile(r"/Users/|/Volumes/|Desktop/FIN496", re.I)


def scan_repo_for_local_paths(text: str, path_label: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if MAC_PATH_HINT.search(line):
            findings.append({"category": "hardcoded_local_path", "file": path_label, "line": str(i), "note": line.strip()[:200]})
    return findings


def main() -> int:
    out = utils.OUT_DIR / "gap_audit"
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []

    targets = [
        utils.REPO_ROOT / "scripts" / "build_v2_public_news_confound_master_layer.py",
        utils.REPO_ROOT / "scripts" / "news_provider_utils.py",
        utils.REPO_ROOT / "scripts" / "build_v2_analyst_relay_layer.py",
        utils.REPO_ROOT / "scripts" / "build_v2_information_environment_batch.py",
        utils.REPO_ROOT / "README.md",
    ]
    for path in targets:
        if path.exists():
            rows.extend(scan_repo_for_local_paths(path.read_text(encoding="utf-8", errors="replace"), str(path.relative_to(utils.REPO_ROOT))))

    rows.append(
        {
            "category": "classification_rule",
            "file": "news_confound_master",
            "line": "",
            "note": "403/429/missing-key and failed provider calls must not be treated as no-news; unknown_news_coverage is never clean.",
        }
    )
    rows.append(
        {
            "category": "diagnostic_scope",
            "file": "yfinance",
            "line": "",
            "note": "Current yfinance analyst snapshots are diagnostic only unless event-time rows are explicitly present.",
        }
    )

    pd.DataFrame(rows).to_csv(out / "gap_audit_findings.csv", index=False)

    summary = f"""# Gap audit summary

## Scope

Automated scan (local-path hints) plus fixed checklist rows for conservative news/confound handling.

## Outputs

- `gap_audit_findings.csv` — structured rows ({len(rows)} findings)

## Residual limitations

- Static scans cannot prove absence of secrets; use pre-commit/staged diff greps before commit.
- Provider free tiers change; canaries and budgeted fetch log quota/permission classes only at run time.
- FNSPID covers 1999–2023; post-2023 events require live providers or remain `unknown_news_coverage` when checks fail.

## Next actions

1. Re-run `scripts/probe_news_provider_canaries.py` on RunPod after `marketdata.env` is installed.
2. Run budgeted fetch with `--execute --resume` and rebuild `build_v2_public_news_confound_master_layer.py`.
3. Re-read `docs/CLAIM_MATRIX.md` after outputs refresh.
"""
    (out / "gap_audit_summary.md").write_text(summary, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
