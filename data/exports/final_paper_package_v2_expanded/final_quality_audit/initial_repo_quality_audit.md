# Initial Repo Quality Audit

Audit date: 2026-05-18
Environment: RunPod `/workspace/FIN496CAPSTONE`
Starting commit: `435d35560246d87b5dd8b209852e49853c636eac`

This note records the repository state before fixes in the final quality audit pass.

## Start-State Verification

- Branch: `main`
- `HEAD`: `435d35560246d87b5dd8b209852e49853c636eac`
- `origin/main`: `435d35560246d87b5dd8b209852e49853c636eac`
- RunPod worktree at start: clean

## Main Package and Entry Points

- Main Python package: `src/finfluencer_alpha/`
- Package CLI entry point: `finfluencer-alpha = finfluencer_alpha.cli:main`
- Python module entry point: `src/finfluencer_alpha/__main__.py`
- Main research CLI surface: `src/finfluencer_alpha/cli.py`
- Script-based research builders: `scripts/build_v2_*.py`, `scripts/validate_*.py`, `scripts/ingest_bloomberg_validation_workbook.py`, and supporting audit/probe scripts.

## Tests and Tooling

- Test suite: `tests/`
- Tooling configured in `pyproject.toml`:
  - `pytest` with `pythonpath = ["src", "."]`
  - `ruff` with `E`, `F`, `I`, `UP`, and `B` lint rules, line length 100, target `py311`
- Local RunPod virtual environment detected at `.venv/`.

## Final Export Folders

- Primary final package: `data/exports/final_paper_package_v2_expanded/`
- Historical benchmark package: `data/exports/final_paper_package/`
- Final defense package: `data/exports/final_paper_package_v2_expanded/final_defense_package/`
- Final exhibits: `data/exports/final_paper_package_v2_expanded/final_exhibits/`
- Final paper synthesis: `data/exports/final_paper_package_v2_expanded/final_paper_synthesis/`
- Bloomberg validation: `data/exports/final_paper_package_v2_expanded/bloomberg_validation/`
- Public-news/confound outputs: `data/exports/final_paper_package_v2_expanded/news_confound_master/`, `confounds/`, `confounds_expanded/`
- Long-horizon, portfolio, factor, causal, and research-frontier outputs are under the corresponding subfolders of the v2 expanded package.

## Data Outputs Used in Final Paper

- Locked sample manifests: `locked_sample_v2/01_v2_transcript_manifest.csv`, `locked_sample_v2/02_v2_event_manifest.csv`, `locked_sample_v2/04_v2_sample_construction.*`
- Core event-study and robustness tables: `02_v2_event_study_robustness_table.*`, `03_v2_timing_lookahead_table.*`, `04_v2_duplicate_cluster_analysis.*`, `05_v2_sec_clean_analysis.*`, `06_v2_top5_vs_non_top_analysis.*`, `07_v2_buy_vs_sell_analysis.*`
- Factor and portfolio outputs: `factors/`, `factor_alpha_beta_estimated/`, `calendar_time_factor_regressions/`, `portfolio/`, `long_horizon_alpha/`
- Claim-control outputs: `news_confound_master/`, `causal_diagnostics/`, `long_horizon_claim_controls/`, `final_defense_package/01_master_claim_matrix.*`
- Bloomberg validation outputs: `bloomberg_validation/bloomberg_*`, `Table_Bloomberg_Coverage.md`, `Table_Bloomberg_Event_Mechanisms.md`, and `final_paper_synthesis/bloomberg_validation_section.md`

## Bloomberg Validation Status Before Fixes

- The current derived Bloomberg outputs include market, analyst consensus, estimate, liquidity, news-proxy, total-return, and short-interest fields.
- `bloomberg_field_coverage_summary.csv` reports `Analyst_coverage` / `TOT_ANALYST_REC` as skipped with status `expected_missing_analyst_coverage` and reason `blank_sheet`.
- `data/manual/bloomberg_validation/` was not present in the current RunPod filesystem during the initial inventory scan, and no raw `.xlsx` Bloomberg workbook was found under `data/` outside backups/derived docs.
- No analyst coverage count should be claimed unless a populated raw workbook becomes available and is parsed.

## Documentation and Claim-Sensitivity Risks

- The root README already uses the conservative v2 thesis: no broad YouTube alpha, no causal creator skill, no tradable strategy, and `multi_source_clean = 0` for public-news-clean claims.
- The root README still describes Bloomberg as the planned higher-quality validation layer in the analyst-relay bullet, while the Bloomberg validation folder now exists. This is stale and should be refreshed.
- Older scripts and historical docs still contain yfinance-prototype language. Some of this is accurate for legacy package outputs, but final-facing docs should point readers to the v2 and Bloomberg-derived outputs.
- Claim-sensitive terms such as causal, skill, proves/proven, and tradable alpha appear mostly in guardrail contexts. These should be checked in final-facing docs for overclaiming.
- The generated script `scripts/build_v2_final_paper_synthesis.py` still says Bloomberg-grade validation remains out-of-sample and has a pre-Bloomberg remaining-work file. This may now be stale relative to the committed Bloomberg validation synthesis.

## Reproducibility and Path Risks

- Most repo paths are relative to the repo root or configured data directories.
- The repo contains large ignored local assets on RunPod (`data/finfluencer_alpha.db`, `data/backups/`, raw imports, logs). These must not be staged.
- Largest tracked file observed: `data/exports/final_paper_package_v2_expanded/bloomberg_validation/bloomberg_long_panel.csv` at about 65 MB. This is below GitHub's 100 MB hard limit but is a repository-size risk.
- No tracked raw Bloomberg workbooks were detected by `git ls-files`.
- No tracked `.env`, `.db`, `.sqlite`, workbook, bundle, log, or obvious raw-data files were detected by the tracked-file extension scan.

## Initial Fix Priorities

1. Run the configured compile, test, lint, import, CLI, and validation smoke checks.
2. Verify whether `TOT_ANALYST_REC` can be parsed from the current RunPod raw workbook; if no workbook/sheet exists, document that it remains unavailable and do not add a claim.
3. Audit final-facing docs and generated synthesis for stale Bloomberg/yfinance-only wording and overclaims.
4. Fix only real broken tests, scripts, empirical correctness issues, or final-facing documentation inconsistencies.
5. Keep raw data, secrets, backups, local databases, logs, and unrelated outputs untouched and unstaged.
