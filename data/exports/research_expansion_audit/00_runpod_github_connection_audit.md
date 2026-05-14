# RunPod and GitHub Connection Audit

- Audit generated UTC: 2026-05-14T00:01:58+00:00
- SSH worked: yes. The required status command reached the RunPod host before this file was generated.
- Codex operating mode: RunPod live repo via SSH, not GitHub-only.
- Remote repo path: `/workspace/FIN496CAPSTONE`
- Current branch: `research-expansion-runpod-audit`
- Remote repo exists: True
- `.venv` exists: True
- DB exists: True (`/workspace/FIN496CAPSTONE/data/finfluencer_alpha.db`)
- Prior `data/exports/research_expansion` outputs exist: True
- Branch `research-expansion-robust-alpha-tests` exists: yes (`origin/research-expansion-robust-alpha-tests`).
- Commit `38e07428ced7cc0e32328a546d63e09a1fec1cf6` exists: True
- Commit `bffb993` exists: True
- Active tmux sessions: `no tmux sessions`
- Active finfluencer Python processes: `9937 python scripts/run_research_expansion_audit.py`
- Audit can proceed on RunPod: yes.

## Git Remotes
```text
origin	https://github.com/Scott-Switzer/finfluencer-alpha.git (fetch)
origin	https://github.com/Scott-Switzer/finfluencer-alpha.git (push)
```

## Available Branches
```text
main
  research-expansion-robust-alpha-tests
* research-expansion-runpod-audit
  remotes/origin/HEAD -> origin/main
  remotes/origin/main
  remotes/origin/research-expansion-robust-alpha-tests
```

## Latest Commits
```text
38e0742 (HEAD -> research-expansion-runpod-audit, origin/research-expansion-robust-alpha-tests, research-expansion-robust-alpha-tests) Expand alpha testing with horizons, benchmarks, portfolios, and AI classifier audit
bffb993 (origin/main, origin/HEAD) Add final event-study and statistical model outputs
bafe5d7 (main) Add statistical modeling module with event-study inference
7b802c6 Add numpy, scipy, statsmodels, scikit-learn dependencies and RunPod setup docs
2a0eeae Fix event funnel bottleneck and add parallel transcript collection
d33e0c3 Document transcript collection limits and manual import workflow
c99ac00 Push Webshare transcript collection coverage (Diagnostic: 0 imports)
0701133 Implement Webshare proxy list aggregation and rotation for transcript collection
```

## Working Tree Status at Audit Time
```text
M .gitignore
 M src/finfluencer_alpha/research_expansion.py
 M tests/test_research_expansion.py
?? data/exports/market_data/event_dates_by_ticker.csv
?? data/exports/market_data/market_data_request.csv
?? data/exports/market_data/unique_tickers.csv
?? data/exports/research_expansion_audit/
?? data/exports/validation/archive_150_sample_20260511_210553/
?? data/exports/validation/archive_150_sample_20260511_210618/
?? data/exports/validation/archive_150_sample_20260511_210659/
?? data/exports/validation/archive_150_sample_20260511_210756/
?? data/exports/validation/clean_auto_labeled_events.csv
?? data/exports/validation/clean_auto_labeled_events_exclusions.csv
?? data/exports/validation/event_classifier_evaluation.csv
?? data/exports/validation/event_classifier_evaluation.md
?? data/exports/validation/event_validation_review_needed.csv
?? data/exports/validation/event_validation_sample.csv
?? data/exports/validation/event_validation_sample_auto_labeled.csv
?? data/finfluencer_alpha.db.backup_runpod_20260513_173148
?? logs/
?? scripts/check_csv_counts.py
?? scripts/check_event_counts.py
?? scripts/check_runs.py
?? scripts/db_audit.py
?? scripts/db_audit2.py
?? scripts/db_audit3.py
?? scripts/db_audit4.py
?? scripts/rebuild_event_study.sh
?? scripts/run_research_expansion_audit.py
```
