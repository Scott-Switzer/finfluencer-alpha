"""Refresh claim matrix and docs with research-frontier robustness extensions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

FRONTIER = utils.OUT_DIR / "research_frontier"
DEF = utils.OUT_DIR / "final_defense_package"
DOCS = REPO_ROOT / "docs"


def read_summary(rel: str) -> str:
    path = FRONTIER / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    subprocess.run([sys.executable, str(SCRIPT_DIR / "build_v2_critical_defense_docs.py")], check=False)
    sel = read_summary("recommendation_selection/recommendation_selection_summary.md")
    att = read_summary("attention_amplification/attention_amplification_summary.md")
    rev = read_summary("reversal_overreaction/reversal_overreaction_summary.md")
    cre = read_summary("creator_skill_taxonomy/creator_skill_taxonomy_summary.md")
    pred_path = FRONTIER / "predictive_validity/predictive_validity_results.csv"
    pred_note = ""
    if pred_path.exists():
        pred = pd.read_csv(pred_path)
        pred_note = pred.to_string(index=False)[:1200]

    frontier_section = f"""
## Research-frontier robustness extensions

| Finding | Status |
| --- | --- |
| Broad short-window alpha | **Rejected** (unchanged) |
| Pre-event momentum / volume selection | **Supported** — recommendations tilt toward prior winners & elevated volume |
| Attention amplification (vol/volatility post-event) | **Supported / diagnostic** — attention proxies rise; alpha not durable |
| Medium-horizon reversal after 5D pop | **Supported / mixed** — stronger fade outside top-5 |
| Creator skill homogeneity | **Rejected** — taxonomy shows momentum-riders & antiskilled-like creators |
| Transcript hype/disclosure gradients | **Diagnostic** — language scores tested on evidence snippets only |
| Placebo date falsification | **Supported** — event-date effects shrink vs shifted same-ticker controls |
| OOS predictability of broad alpha | **Weakened / limited** — time-split models do not support easy exploitation |
| Non-top underperformance predictability | **Mixed** — check predictive_validity_results.csv |
| Public-news-clean non-top robustness | **Unresolved** — non-top master-clean n=0 |
| Tradable strategy | **Rejected** |
| Causal creator skill | **Rejected** |

### Selection excerpt
{sel[:800] if sel else 'Run build_v2_recommendation_selection_tests.py'}

### Attention / reversal / creator excerpts
{att[:400] if att else ''}
{rev[:400] if rev else ''}
{cre[:400] if cre else ''}

### Predictive validity excerpt
{pred_note}
"""

    claim_path = DEF / "FINAL_CLAIM_MATRIX.md"
    if claim_path.exists():
        text = claim_path.read_text(encoding="utf-8")
        if "Research-frontier robustness" not in text:
            claim_path.write_text(text + "\n" + frontier_section, encoding="utf-8")

    for name, body in [
        ("RESULTS_NARRATIVE_SAFE.md", "Results remain heterogeneous. Frontier tests add **mechanism** evidence: momentum selection, attention amplification, and placebo falsification. Non-top weakness is more defensible than broad alpha."),
        ("LIMITATIONS_AND_THREATS.md", "Remaining gaps: partial AV news coverage (4 tickers), non-top master-clean n=0, creator/ticker holdout predictive tests not run, 504D diagnostic only."),
    ]:
        p = DEF / name
        if p.exists():
            t = p.read_text(encoding="utf-8")
            if "Research-frontier" not in t:
                p.write_text(t + "\n\n### Research-frontier extensions\n\n" + body + "\n", encoding="utf-8")

    proj = DOCS / "PROJECT_STATUS.md"
    if proj.exists():
        t = proj.read_text(encoding="utf-8")
        if "research_frontier" not in t:
            proj.write_text(
                t + "\n\n## Research-frontier robustness extensions\n\n"
                "Added mechanism modules under `data/exports/final_paper_package_v2_expanded/research_frontier/`. "
                "See `00_research_frontier_workplan.md`.\n",
                encoding="utf-8",
            )

    methods = DOCS / "METHODS_AUDIT.md"
    if methods.exists():
        t = methods.read_text(encoding="utf-8")
        if "research_frontier" not in t:
            methods.write_text(
                t + "\n\nFrontier pass: pre-event selection regressions, attention amplification, "
                "reversal panels, creator taxonomy, transcript language scores (evidence_window only), "
                "expanded placebos, and time-split predictive validity.\n",
                encoding="utf-8",
            )

    claim_doc = DOCS / "CLAIM_MATRIX.md"
    if claim_doc.exists():
        t = claim_doc.read_text(encoding="utf-8")
        if "momentum selection" not in t.lower():
            claim_doc.write_text(
                t + "\n\n- **Momentum selection:** supported (pre-event return/volume gaps).\n"
                "- **Causal skill:** rejected (placebos + taxonomy).\n"
                "- **Non-top public-news-clean:** unresolved (n=0).\n",
                encoding="utf-8",
            )

    readme = REPO_ROOT / "README.md"
    if readme.exists():
        t = readme.read_text(encoding="utf-8")
        if "Research-frontier" not in t:
            readme.write_text(
                t.replace(
                    "## Reproducibility",
                    "## Research-frontier robustness extensions\n\n"
                    "Mechanism and falsification modules live under "
                    "`data/exports/final_paper_package_v2_expanded/research_frontier/`. "
                    "They test momentum selection, attention amplification, reversals, creator taxonomy, "
                    "language scores, expanded placebos, and out-of-sample predictability—without claiming broad alpha.\n\n"
                    "## Reproducibility",
                ),
                encoding="utf-8",
            )

    print("Research frontier docs updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
