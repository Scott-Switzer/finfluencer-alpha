# Gap audit summary

## Scope

Automated scan (local-path hints) plus fixed checklist rows for conservative news/confound handling.

## Outputs

- `gap_audit_findings.csv` — structured rows (2 findings)

## Residual limitations

- Static scans cannot prove absence of secrets; use pre-commit/staged diff greps before commit.
- Provider free tiers change; canaries and budgeted fetch log quota/permission classes only at run time.
- FNSPID covers 1999–2023; post-2023 events require live providers or remain `unknown_news_coverage` when checks fail.

## Next actions

1. Re-run `scripts/probe_news_provider_canaries.py` on RunPod after `marketdata.env` is installed.
2. Run budgeted fetch with `--execute --resume` and rebuild `build_v2_public_news_confound_master_layer.py`.
3. Re-read `docs/CLAIM_MATRIX.md` after outputs refresh.
