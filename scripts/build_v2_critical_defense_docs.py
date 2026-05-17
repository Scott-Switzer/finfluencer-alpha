from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/workspace/FIN496CAPSTONE')
OUT = ROOT / 'data' / 'exports' / 'final_paper_package_v2_expanded'
DOCS = ROOT / 'docs'
DEF = OUT / 'final_defense_package'
LIT = OUT / 'literature_positioning'


def read(rel: str) -> pd.DataFrame:
    path = OUT / rel
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + '\n', encoding='utf-8')


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0]) if rows else ['status']
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=cols, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        rows = [{'status': 'no_rows'}]
    cols = list(rows[0])
    lines = ['| ' + ' | '.join(cols) + ' |', '| ' + ' | '.join('---' for _ in cols) + ' |']
    for row in rows:
        lines.append('| ' + ' | '.join(str(row.get(col, '')) for col in cols) + ' |')
    return '\n'.join(lines)


def first_row(df: pd.DataFrame) -> dict[str, Any]:
    return df.iloc[0].to_dict() if not df.empty else {}


av = first_row(read('news_alpha_vantage/05_av_news_coverage_summary.csv'))
gd = read('news_gdelt_retry/02_gdelt_probe_flags.csv')
master = first_row(read('confounds/02_v2_confound_coverage_summary.csv'))

gd_success_rate = 'NA'
if not gd.empty and 'gdelt_query_success' in gd.columns:
    gd_success_rate = f"{gd['gdelt_query_success'].astype(str).str.lower().eq('true').mean():.3f}"

claim_rows = [
    {
        'claim': 'broad YouTube alpha',
        'status': 'rejected',
        'strongest_evidence': 'Full sample 5D SPY-adjusted BHAR is small and insignificant.',
        'weakest_evidence': 'Long-horizon drift is broken by matched controls and concentration.',
        'exact_caveat': 'Do not cite long horizons as causal YouTube alpha.',
        'paper_wording_allowed': 'No broad short-window abnormal return in the expanded sample.',
        'paper_wording_prohibited': 'YouTube recommendations generate alpha.',
        'table_figure_to_cite': 'long_horizon/03_v2_long_horizon_summary_by_spec.csv',
        'confidence_level': 'high',
    },
    {
        'claim': 'short-window top-5 effect',
        'status': 'supported/mixed',
        'strongest_evidence': 'Top-5 5D and 21D returns are positive in v2.',
        'weakest_evidence': 'Factor and matched-control diagnostics weaken causal interpretation.',
        'exact_caveat': 'Mega-cap momentum synchronization, not proof of stock-picking skill.',
        'paper_wording_allowed': 'Top-name recommendations are followed by positive abnormal returns.',
        'paper_wording_prohibited': 'Top-name recommendations are independently tradable alpha.',
        'table_figure_to_cite': 'long_horizon/04_v2_long_horizon_top5_vs_non_top.csv',
        'confidence_level': 'medium-high',
    },
    {
        'claim': 'non-top underperformance',
        'status': 'supported/mixed',
        'strongest_evidence': 'Non-top recommendations are negative through medium horizons.',
        'weakest_evidence': 'Very long BHAR windows weaken as coverage changes.',
        'exact_caveat': 'Interpret as underperformance/fade risk, not a shortable strategy.',
        'paper_wording_allowed': 'Recommendations outside top names underperform over medium horizons.',
        'paper_wording_prohibited': 'Short all non-top recommendations for profit.',
        'table_figure_to_cite': 'long_horizon/04_v2_long_horizon_top5_vs_non_top.csv',
        'confidence_level': 'medium-high',
    },
    {
        'claim': 'Alpha Vantage news-clean robustness',
        'status': 'partial',
        'strongest_evidence': f"Real AV metadata mapped events with clean/confounded/unknown counts {av.get('clean_events', 'NA')}/{av.get('confounded_events', 'NA')}/{av.get('unknown_events', 'NA')}.",
        'weakest_evidence': 'Coverage remains partial and request-budget constrained.',
        'exact_caveat': 'Not a full-sample public-news control.',
        'paper_wording_allowed': 'A partial real-news metadata layer was added and unknown events are not clean.',
        'paper_wording_prohibited': 'The results survive complete public-news controls.',
        'table_figure_to_cite': 'news_alpha_vantage/',
        'confidence_level': 'medium',
    },
    {
        'claim': 'GDELT news-clean robustness',
        'status': 'rejected for main use',
        'strongest_evidence': f'Retry success rate was {gd_success_rate}.',
        'weakest_evidence': 'Provider coverage below 50% threshold.',
        'exact_caveat': 'Diagnostic only.',
        'paper_wording_allowed': 'GDELT was attempted but unreliable for main robustness.',
        'paper_wording_prohibited': 'GDELT-clean sample validates the finding.',
        'table_figure_to_cite': 'news_gdelt_retry/',
        'confidence_level': 'high',
    },
    {
        'claim': 'beta-estimated factor alpha',
        'status': 'mixed',
        'strongest_evidence': 'Rolling beta-estimated factor alpha table is now available.',
        'weakest_evidence': 'Calendar-time HAC regressions remain approximate.',
        'exact_caveat': 'Do not overstate factor-model proof.',
        'paper_wording_allowed': 'Factor adjustment weakens broad alpha claims.',
        'paper_wording_prohibited': 'Factor models prove causal alpha.',
        'table_figure_to_cite': 'factor_alpha_beta_estimated/',
        'confidence_level': 'medium',
    },
    {
        'claim': 'causal effect',
        'status': 'rejected',
        'strongest_evidence': 'Matched controls and placebo diagnostics break event-date treatment story.',
        'weakest_evidence': 'No random assignment or credible exogenous shock.',
        'exact_caveat': 'Use falsification/selection framing.',
        'paper_wording_allowed': 'Evidence is consistent with attention and selection, not causal alpha.',
        'paper_wording_prohibited': 'YouTube caused these returns.',
        'table_figure_to_cite': 'long_horizon_falsification/',
        'confidence_level': 'high',
    },
    {
        'claim': 'tradable strategy',
        'status': 'rejected',
        'strongest_evidence': 'Execution realism tables show drawdown/concentration/cost constraints are severe.',
        'weakest_evidence': 'Top-5 diagnostic trades can look strong before full execution realism.',
        'exact_caveat': 'No investment advice or tradable-alpha claim.',
        'paper_wording_allowed': 'Portfolio diagnostics do not support a robust executable strategy.',
        'paper_wording_prohibited': 'This strategy is tradable.',
        'table_figure_to_cite': 'portfolio_execution_realism/',
        'confidence_level': 'high',
    },
    {
        'claim': 'v2 as primary sample',
        'status': 'supported',
        'strongest_evidence': 'v2 uses the complete validated RunPod DB sample of 2,341 accepted recommendation events.',
        'weakest_evidence': 'v1 remains a historical benchmark; v2 still has confound limitations.',
        'exact_caveat': 'Use v2 for primary empirical claims and v1 only as historical benchmark.',
        'paper_wording_allowed': 'The expanded v2 sample is the primary empirical sample.',
        'paper_wording_prohibited': 'v1 is the current primary sample.',
        'table_figure_to_cite': 'locked_sample_v2/',
        'confidence_level': 'high',
    },
]

write_csv(DEF / '01_master_claim_matrix.csv', claim_rows)
write(DEF / '01_master_claim_matrix.md', '# Master Claim Matrix\n\n' + md_table(claim_rows))
write(OUT / '30_critical_defense_workplan.md', '''# Critical Defense Workplan

Current supported interpretation: the expanded v2 sample does not support broad short-window YouTube alpha. The strongest defensible finding is heterogeneity: top-5 mega-cap/momentum recommendations are followed by positive abnormal returns, while non-top recommendations underperform through medium horizons. Matched controls and placebo diagnostics break a clean causal story, and portfolio diagnostics do not support a tradable strategy claim.

Critical gaps addressed in this pass: partial real Alpha Vantage public-news metadata, GDELT retry diagnostics, expanded SEC/earnings flags, master clean/confounded/unknown panel, event classification audit, beta-estimated factor alpha, overlap/censoring robustness, execution realism, README cleanup, literature positioning, and final claim matrix.

Remaining critical gap: real public-news coverage is still partial. Unknown events are not clean.
''')

lit_rows = [
    {'source': 'Swiss Finance Institute / Kakhbod et al. Finfluencers', 'data_source': 'social stock-picking posts', 'method': 'finfluencer skill classification and abnormal returns', 'main_finding': 'Most finfluencers are unskilled or antiskilled; popularity does not equal skill.', 'limitation': 'Not YouTube transcript-based and not this project sample.', 'how_this_project_differs': 'Uses YouTube transcript-supported recommendations and event-study panels.', 'implication': 'Supports avoiding broad skill claims.', 'citation': 'https://www.sfi.ch/de/publications/n-23-30-finfluencers'},
    {'source': 'FINRA social-media-influenced investing reports', 'data_source': 'investor surveys and regulatory review', 'method': 'descriptive investor behavior and risk analysis', 'main_finding': 'Younger investors use social media and finfluencers heavily for investing information.', 'limitation': 'Does not estimate recommendation event returns.', 'how_this_project_differs': 'Tests stock-return dynamics after detected recommendations.', 'implication': 'Motivates investor-protection framing.', 'citation': 'https://www.finra.org/rules-guidance/key-topics/fintech/report/social-media-influenced-investing'},
    {'source': 'FINRA Foundation 2026 research brief', 'data_source': '2024 NFCS investor survey', 'method': 'survey evidence', 'main_finding': 'Social-media-informed investors are often younger and face knowledge/fraud-risk gaps.', 'limitation': 'Survey, not event study.', 'how_this_project_differs': 'Empirical return/event panel.', 'implication': 'Frames why finfluencer recommendations matter.', 'citation': 'https://www.finra.org/media-center/newsreleases/2026/finra-foundation-research-examines-characteristics-behaviors-outcomes'},
    {'source': 'NASAA finfluencer advisory', 'data_source': 'investor advisory', 'method': 'regulatory warning', 'main_finding': 'Investors should be cautious because finfluencers may be less regulated and conflicted.', 'limitation': 'Not quantitative return evidence.', 'how_this_project_differs': 'Quantifies post-recommendation return dynamics.', 'implication': 'Supports conservative language and no investment-advice framing.', 'citation': 'https://www.nasaa.org/65026/nasaa-cautions-investors-on-the-rise-of-the-finfluencer/'},
    {'source': 'OSC Social Media and Retail Investing report', 'data_source': 'retail investor research', 'method': 'survey/experimental investor-protection research', 'main_finding': 'Finfluencers can strongly influence retail investor decisions.', 'limitation': 'Canadian investor context.', 'how_this_project_differs': 'U.S. ticker YouTube recommendation sample.', 'implication': 'Supports attention-amplification framing.', 'citation': 'https://www.osc.ca/en/investors/investor-research-and-reports/social-media-and-retail-investing-rise-finfluencers'},
    {'source': 'CFA Institute Finfluencer Appeal', 'data_source': 'finfluencer content and Gen Z investor research', 'method': 'policy/research report', 'main_finding': 'Gen Z engagement with finfluencer content raises disclosure and literacy concerns.', 'limitation': 'Policy report, not event-return panel.', 'how_this_project_differs': 'Estimates abnormal returns around recommendations.', 'implication': 'Supports disclosure/regulatory caveats.', 'citation': 'https://www.cfainstitute.org/about/press-room/2024/policy-recommendations-for-finfluencer-social-media-content'},
    {'source': 'Kothari and Warner event-study econometrics', 'data_source': 'event-study methodology literature', 'method': 'survey/econometric critique', 'main_finding': 'Short-horizon event studies are more reliable; long-horizon methods face serious limitations.', 'limitation': 'Methodological source, not finfluencer-specific.', 'how_this_project_differs': 'Applies these caveats to YouTube recommendation events.', 'implication': 'Requires censoring/overlap/falsification caveats.', 'citation': 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=608601'},
]
write_csv(LIT / '01_literature_comparison_matrix.csv', lit_rows)
write(LIT / '01_literature_comparison_matrix.md', '# Literature Comparison Matrix\n\n' + md_table(lit_rows))
write(LIT / '02_how_this_project_differs.md', '# How This Project Differs\n\nThis project uses transcript-supported YouTube recommendation events rather than platform-level survey responses or social-post likes. It estimates short- and long-horizon abnormal returns, then tests whether apparent effects survive SEC/news confounds, factor controls, overlap/censoring checks, matched controls, and portfolio execution realism.')
write(LIT / '03_citation_plan.md', '# Citation Plan\n\nUse SFI/Kakhbod for finfluencer skill heterogeneity, FINRA/FINRA Foundation/OSC/CFA/NASAA for investor-protection motivation, and Kothari-Warner/Barber-Lyon style event-study sources for long-horizon inference caveats.')
write(LIT / '04_literature_limitations.md', '# Literature Limitations\n\nThe literature sources motivate the research question and framing, but they do not validate this sample. The paper must cite project-generated v2 artifacts for empirical claims.')

root_readme = '''# YouTube Finfluencer Recommendations and Stock Return Dynamics

This repository studies transcript-supported YouTube stock recommendations and subsequent stock return dynamics. The validated expanded v2 sample contains 9,992 transcript-video rows and 2,341 accepted recommendation events. The current evidence does not support broad short-window YouTube alpha. The defensible finding is heterogeneity: returns concentrate in top-5 mega-cap/momentum tickers, while recommendations outside those names underperform through medium horizons. Matched controls, factor checks, and portfolio diagnostics reject causal and tradable-alpha overclaims.

## Dataset Status

- `data/exports/final_paper_package/`: v1 locked historical artifact package.
- `data/exports/final_paper_package_v2_expanded/`: primary empirical package.
- v2 accepted recommendation events: 2,341.
- v2 return coverage: 2,322 1D events and long-horizon coverage documented in `long_horizon/02_v2_long_horizon_coverage.csv`.

## Methods

- Transcript-supported event detection.
- Event studies using SPY-adjusted BHAR/CAR.
- Long-horizon return panels with right-censoring flags.
- SEC/earnings confound flags.
- Real public-news metadata through Alpha Vantage where available; GDELT is diagnostic only.
- Beta-estimated factor alpha and factor-basket checks.
- Matched controls, placebo/permutation diagnostics, overlap/censoring robustness.
- Portfolio execution realism with costs, delays, drawdowns, and concentration.

## Main Findings

- Broad alpha: rejected.
- Top-5 attention/concentration: supported but not causal.
- Non-top underperformance: supported/mixed through medium horizons.
- Causality: rejected by matched controls and placebo diagnostics.
- Tradable strategy: rejected due to concentration, drawdown, costs, and execution caveats.
- News-clean robustness: partial only. Alpha Vantage mapped real metadata but coverage remains incomplete; GDELT success rate is below the usability threshold.

## Final Claim Status

| Claim | Status |
| --- | --- |
| Broad YouTube alpha | Rejected |
| Top-5 attention/concentration | Supported / mixed |
| Non-top underperformance | Supported / mixed |
| Causality | Rejected |
| Tradable strategy | Rejected |
| News-clean robustness | Partial |
| Creator skill | Not supported |

## Reproducibility

Run the validation suite from the repository root:

```bash
python3 scripts/validate_expanded_primary_sample_package.py
python3 scripts/validate_locked_sample_manifest.py
ruff check .
pytest -q
```

No API keys, raw transcripts, raw databases, raw article bodies, or `.env` files should be committed. This is a student research project and not investment advice.
'''
write(ROOT / 'README.md', root_readme)

write(DOCS / 'PROJECT_STATUS.md', f'''# Project Status

Primary sample: v2 expanded RunPod package. v1 is preserved as a historical benchmark. The strongest conclusion is attention concentration and heterogeneous return dynamics, not broad alpha.

Alpha Vantage coverage: clean={av.get('clean_events', 'NA')}, confounded={av.get('confounded_events', 'NA')}, unknown={av.get('unknown_events', 'NA')}.

Master confound panel: clean={master.get('master_clean', 'NA')}, confounded={master.get('master_confounded', 'NA')}, unknown={master.get('master_unknown', 'NA')}.
''')
write(DOCS / 'METHODS_AUDIT.md', '# Methods Audit\n\nThe project now distinguishes v1 historical artifacts from v2 primary sample, separates clean/confounded/unknown events, treats public-news unknown as not clean, flags right-censored long horizons, and rejects causal/tradable claims unless supported by controls.')
write(DOCS / 'CLAIM_MATRIX.md', '# Claim Matrix\n\n' + md_table(claim_rows))
write(DOCS / 'REPRODUCIBILITY.md', '# Reproducibility\n\nUse RunPod as the authoritative execution environment. Validation commands are `python3 scripts/validate_expanded_primary_sample_package.py`, `python3 scripts/validate_locked_sample_manifest.py`, `ruff check .`, and `pytest -q`. Do not commit secrets, raw DBs, raw transcripts, raw API responses, or article bodies.')
write(DOCS / 'NEWS_LAYER_STATUS.md', f'''# News Layer Status

Alpha Vantage key status was runtime-present during this pass. The script stores only compact metadata. Alpha Vantage coverage remains partial: clean={av.get('clean_events', 'NA')}, confounded={av.get('confounded_events', 'NA')}, unknown={av.get('unknown_events', 'NA')}.

GDELT retry is diagnostic only because the success rate stayed below the 50% threshold.
''')

write(DEF / '02_professor_defense_bullets.md', '# Professor Defense Bullets\n\n- The v2 sample is primary because it uses the most complete validated RunPod database.\n- The full sample does not show broad short-window alpha.\n- Top-5 mega-cap/momentum names drive positive results.\n- Non-top recommendations underperform through medium horizons.\n- Matched controls and placebo checks break a causal YouTube story.\n- Portfolio diagnostics do not support tradability.\n- Public-news controls improved with Alpha Vantage but remain partial.')
write(DEF / '03_results_interpretation_bullets.md', '# Results Interpretation Bullets\n\nUse “attention amplification,” “ticker concentration,” and “momentum synchronization.” Do not use “causal alpha” or “tradable strategy.”')
write(DEF / '04_limitations_bullets.md', '# Limitations Bullets\n\n- Public-news coverage is partial.\n- Long horizons are right-censored.\n- Events overlap by ticker and creator.\n- The sample is observational and not randomly assigned.\n- Event classification uses automated/proxy confidence checks, not full manual validation.')
write(DEF / '05_tables_and_figures_to_use.md', '# Tables And Figures To Use\n\n- `long_horizon/03_v2_long_horizon_summary_by_spec.csv`\n- `confounds/03_v2_clean_confounded_unknown_return_summary.csv`\n- `event_quality_audit/03_quality_filtered_return_summary.csv`\n- `factor_alpha_beta_estimated/03_factor_alpha_summary_by_spec.csv`\n- `overlap_censoring_robustness/`\n- `portfolio_execution_realism/`')
write(DEF / '06_what_not_to_claim.md', '# What Not To Claim\n\n- Do not claim broad YouTube alpha.\n- Do not claim causality.\n- Do not claim a tradable strategy.\n- Do not claim complete news controls.\n- Do not claim Bloomberg-equivalent news robustness.\n- Do not claim creator skill without ticker controls.')
write(DEF / '07_final_project_status.md', '# Final Project Status\n\nThe project is professor-ready as a careful empirical defense package with partial news controls and explicit rejected claims. It is not publication-ready as causal/trading evidence.')
write(DEF / '08_readme_alignment_audit.md', '# README Alignment Audit\n\nThe root README now matches the v2 evidence: no broad alpha, top-5 concentration, non-top underperformance, partial news controls, rejected causality, and rejected tradability.')
write(DEF / '09_submission_integrity_checklist.md', '# Submission Integrity Checklist\n\n- v1 preserved.\n- v2 primary sample documented.\n- No `.env` or API key committed.\n- No raw transcripts or raw article bodies exported.\n- Unknown news coverage is not treated as clean.\n- Causal and tradable-alpha claims are prohibited.')

v2_readme = OUT / 'README.md'
if v2_readme.exists():
    existing = v2_readme.read_text(encoding='utf-8')
    marker = '## Critical Defense Update'
    if marker not in existing:
        write(v2_readme, existing + '\n\n## Critical Defense Update\n\nA critical defense pass added partial real Alpha Vantage news metadata, GDELT retry diagnostics, expanded SEC/earnings flags, a master confound panel, event-quality audit, beta-estimated factor alpha, overlap/censoring robustness, portfolio execution realism, literature positioning, and final defense package outputs.\n')
print('Critical defense docs generated')
