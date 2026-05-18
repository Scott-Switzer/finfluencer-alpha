"""Draft final-defense prose from fixed thesis + empirical caveats."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "final_paper_synthesis"
THESIS = (
    "In a large transcript-supported sample of YouTube stock recommendations, I do not find evidence of broad, tradable "
    "finfluencer alpha. The strongest pattern is heterogeneity: highly salient top-name recommendations, especially those "
    "aligned with analyst consensus, show stronger medium-horizon returns than non-top names. This is more consistent "
    "with attention amplification, consensus relay, and ticker selection than with causal creator skill. Extended FNSPID "
    "Hub coverage (Nasdaq + All_external CSV streams) improves historical *media* detection for older windows but does not "
    "complete live public-news identification; conclusions remain mechanism-consistent rather than public-news-clean causal evidence."
)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lim = """## Limitations\n\n- Unknown news coverage is never classified as clean.\n- Multi-source clean is strict and currently empty.\n- FNSPID improves pre-2024 history but does not replace live disclosure feeds.\n- Bloomberg validation is included as an institutional mechanism layer, but it is not causal identification and does not create public-news-clean alpha, creator-skill, or tradability evidence.\n- Bloomberg `Analyst_coverage` is blank, so analyst coverage counts are not included yet.\n- Bloomberg short-interest coverage is partial and should be treated only as optional speculative-pressure evidence.\n- Bloomberg News Heat and News Sentiment are news-flow proxies, not manual headline audits.\n- yfinance snapshots are diagnostic only for analyst stance unless dated pre-event rows are proven.\n"""
    (OUT / "final_results_section_draft.md").write_text(
        "# Results (draft)\n\n"
        "_Empirical numbers belong in exhibits; this file holds framing only._\n\n"
        "For the final paper, include the Bloomberg validation insert from `bloomberg_validation_section.md` after the core return/news-confound results. Frame it as an institutional mechanism check that supports analyst-relay, public-information-overlap, liquidity, total-return, and estimate-revision interpretation without making causal, public-news-clean alpha, creator-skill, or tradability claims.\n",
        encoding="utf-8",
    )
    (OUT / "final_methodology_section_draft.md").write_text(
        "# Methodology (draft)\n\nConservative multi-provider news confound handling, FNSPID historical coverage, budgeted live probes, and matched/robustness diagnostics.\n",
        encoding="utf-8",
    )
    (OUT / "final_limitations_section_draft.md").write_text("# Limitations (draft)\n\n" + lim, encoding="utf-8")
    (OUT / "final_abstract_draft.md").write_text("# Abstract (draft)\n\n" + THESIS + "\n", encoding="utf-8")
    (OUT / "final_intro_thesis_paragraph.md").write_text("# Intro thesis paragraph\n\n" + THESIS + "\n", encoding="utf-8")
    (OUT / "final_professor_defense_qna.md").write_text(
        "# Defense Q&A (draft)\n\n**Q: Is this causal alpha?** No — relay + incomplete public news ID block causal claims.\n\n"
        "**Q: Why do top names look better?** Attention, liquidity, consensus correlation — not proven creator skill.\n",
        encoding="utf-8",
    )
    (OUT / "final_claim_discipline_table.md").write_text(
        "# Claim discipline\n\n| Prohibited | Notes |\n|---|---|\n| Broad tradable YouTube alpha | Not supported |\n| Causal creator skill | Not identified |\n| Non-top weakness as public-news-clean | Requires multi-source clean n |\n",
        encoding="utf-8",
    )
    (OUT / "final_remaining_work_before_bloomberg.md").write_text(
        "# Remaining Bloomberg Follow-up\n\n- Add corporate event timestamp exports only if a separate raw Bloomberg or news-audit source is available.\n- Do not add an analyst coverage count unless `Analyst_coverage` / `TOT_ANALYST_REC` is populated.\n- Cross-check multi_source_clean events if future provider coverage changes.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
