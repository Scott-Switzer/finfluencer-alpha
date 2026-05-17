"""Refresh final defense docs, claim discipline table, indexes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

DEF = utils.OUT_DIR / "final_defense_package"
DOCS = REPO_ROOT / "docs"


def main() -> int:
    subprocess.run([sys.executable, str(SCRIPT_DIR / "build_v2_critical_defense_docs.py")], check=False)

    discipline = [
        {
            "claim": "Broad YouTube alpha",
            "evidence_for": "Short-window raw means occasionally positive in subsamples",
            "evidence_against": "Full-sample insignificance; calendar-time FF5; placebos",
            "status": "rejected",
            "allowed_wording": "No broad short-window abnormal return in the expanded sample",
            "prohibited_wording": "YouTube recommendations generate alpha",
        },
        {
            "claim": "Top-5 positive dynamics",
            "evidence_for": "Positive 5D/21D raw BHAR in top names",
            "evidence_against": "Factor adjustment; momentum selection; placebos",
            "status": "supported_mixed",
            "allowed_wording": "Mega-cap recommendations coincide with positive raw abnormal returns",
            "prohibited_wording": "Creators pick top stocks skillfully",
        },
        {
            "claim": "Non-top underperformance",
            "evidence_for": "Negative medium-horizon patterns; predictive holdouts",
            "evidence_against": "Non-top master-clean n=0; ticker-out may absorb signal",
            "status": "supported_mixed",
            "allowed_wording": "Non-top recommendations show weaker medium-horizon performance",
            "prohibited_wording": "Short all non-top recommendations profitably",
        },
        {
            "claim": "Public-news-clean robustness",
            "evidence_for": "Partial AV metadata on 4 tickers",
            "evidence_against": "1657+ AV-unknown; non-top clean n=0",
            "status": "partial_unresolved",
            "allowed_wording": "Partial news metadata; unknown is not clean",
            "prohibited_wording": "Results survive full public-news controls",
        },
        {
            "claim": "Causal creator skill",
            "evidence_for": "Creator taxonomy dispersion",
            "evidence_against": "Placebos; cross-ticker placebo; no skill homogeneity",
            "status": "rejected",
            "allowed_wording": "Heterogeneous creator ex-post outcomes",
            "prohibited_wording": "Finfluencers cause returns",
        },
        {
            "claim": "Tradable strategy",
            "evidence_for": "In-sample classification AUC for non-top underperform",
            "evidence_against": "Portfolio realism; costs; concentration",
            "status": "rejected",
            "allowed_wording": "Diagnostics do not support tradability",
            "prohibited_wording": "Investable strategy",
        },
        {
            "claim": "504D long-horizon alpha",
            "evidence_for": "Some long-window means in uncensored slices",
            "evidence_against": "Censoring; thin full-window n; multiple-testing",
            "status": "diagnostic_only",
            "allowed_wording": "504D reported only with censoring caveats",
            "prohibited_wording": "Two-year finfluencer alpha",
        },
    ]
    utils.write_csv(DEF / "CLAIM_DISCIPLINE_TABLE.csv", discipline, list(discipline[0]))
    utils.write_md(DEF / "CLAIM_DISCIPLINE_TABLE.md", "Claim Discipline", utils.md_table(discipline))

    tables = [
        "confounds_expanded/",
        "market_implied_confounds/",
        "calendar_time_factor_regressions/",
        "research_frontier/",
        "inference_robustness/",
        "news_alpha_vantage_expanded/",
        "long_horizon_claim_controls/",
    ]
    (DEF / "TABLE_INDEX.md").write_text(
        "# Table index\n\n" + "\n".join(f"- `{t}`" for t in tables) + "\n",
        encoding="utf-8",
    )
    (DEF / "FIGURE_INDEX.md").write_text(
        "# Figure index\n\nFigures under `figures_data/` and long-horizon exports. Prefer committed CSV series for paper charts.\n",
        encoding="utf-8",
    )

    repro = """# Reproduction commands (RunPod authoritative)

```bash
cd /workspace/FIN496CAPSTONE
.venv/bin/python3 scripts/validate_expanded_primary_sample_package.py
.venv/bin/python3 scripts/build_v2_public_repo_audit.py
.venv/bin/python3 scripts/build_v2_local_asset_manifest.py
.venv/bin/python3 scripts/audit_public_repo_safety.py
.venv/bin/python3 scripts/build_v2_market_implied_confound_screen.py
.venv/bin/python3 scripts/build_v2_holdout_predictive_validity.py
.venv/bin/python3 scripts/build_v2_multiple_testing_and_inference_audit.py
.venv/bin/python3 scripts/build_v2_placebo_matched_control_expansion.py
.venv/bin/python3 scripts/build_v2_finalize_public_package.py
```

Alpha Vantage key: `/root/.config/fin496/alphavantage.env` only — never commit.
"""
    (DEF / "REPRODUCTION_COMMANDS.md").write_text(repro.strip() + "\n", encoding="utf-8")

    for doc, extra in [
        ("PROJECT_STATUS.md", "Final public-package hardening: asset manifest, safety audit, market-implied confounds, holdouts, inference audit."),
        ("METHODS_AUDIT.md", "Added market-implied screen (not news-clean), holdout predictive validity, multiple-testing audit, creator cross-ticker placebo."),
        ("CLAIM_MATRIX.md", "See CLAIM_DISCIPLINE_TABLE in final_defense_package."),
        ("NEWS_LAYER_STATUS.md", "AV partial; unknown never clean; market-implied is separate sensitivity layer."),
        ("REPRODUCIBILITY.md", "Public repo = exports + scripts; private DB on RunPod."),
    ]:
        p = DOCS / doc
        if p.exists() and extra.split()[0] not in p.read_text(encoding="utf-8"):
            p.write_text(p.read_text(encoding="utf-8").rstrip() + f"\n\n{extra}\n", encoding="utf-8")

    print("Finalize public package complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
