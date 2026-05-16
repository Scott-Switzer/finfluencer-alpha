# Final Paper Package

This directory is the paper-facing empirical-defense package for the locked
YouTube transcript sample, with a current reconciliation caveat. See
`40_runpod_count_reconciliation_audit.md` and `locked_sample/README.md` before
citing sample counts. The manifest-supported final event panel has 1,554 events;
the 8,994 transcript count is a historical locked-package count that is not
reconstructible from the current live RunPod DB. Bloomberg is treated as a
future manual-CSV validation layer, not a current dependency.

| File | Meaning | Paper ready? |
| --- | --- | --- |
| 00_repo_and_sample_audit.md | repo/sample audit | Needs sample-lock caveat |
| 01_sample_construction_table.csv | sample construction | Yes |
| 01_sample_construction_table.md | sample construction | Needs sample-lock caveat |
| 02_event_study_robustness_table.csv | event-study robustness | Yes |
| 02_event_study_robustness_table.md | event-study robustness | Yes |
| 03_leave_one_out_tables.csv | leave-one-out robustness | Yes |
| 03_leave_one_out_tables.md | leave-one-out robustness | Yes |
| 04_timing_lookahead_methodology.md | timing/lookahead defense | Yes |
| 04_timing_lookahead_table.csv | timing/lookahead defense | Yes |
| 04_timing_lookahead_table.md | timing/lookahead defense | Yes |
| 05_duplicate_cluster_analysis.csv | duplicate-cluster defense | Yes |
| 05_duplicate_cluster_analysis.md | duplicate-cluster defense | Yes |
| 06_sec_news_excluded_event_study_table.csv | SEC/free metadata confounds | Yes |
| 06_sec_news_excluded_event_study_table.md | SEC/free metadata confounds | Yes |
| 06_sec_news_overlap_flags.csv | SEC/free metadata confounds | Yes |
| 06_sec_news_overlap_summary.md | SEC/free metadata confounds | Yes |
| 06b_free_metadata_confounds.csv | SEC/free metadata confounds | Yes |
| 06b_free_metadata_confounds_summary.md | SEC/free metadata confounds | Yes |
| 07_bloomberg_csv_ingestion_status.csv | Bloomberg manual-CSV scaffold | Diagnostic/scaffold |
| 07_bloomberg_csv_ingestion_status.md | Bloomberg manual-CSV scaffold | Diagnostic/scaffold |
| 07_bloomberg_manual_pull_instructions.md | Bloomberg manual-CSV scaffold | Diagnostic/scaffold |
| 07_bloomberg_required_fields_checklist.md | Bloomberg manual-CSV scaffold | Diagnostic/scaffold |
| 08_factor_adjusted_alpha_table.csv | factor adjustment | Yes |
| 08_factor_adjusted_alpha_table.md | factor adjustment | Yes |
| 08_factor_download_status.csv | factor adjustment | Yes |
| 08_factor_download_status.md | factor adjustment | Yes |
| 08_factor_methodology.md | factor adjustment | Yes |
| 09_intraday_coverage_report.csv | intraday diagnostic | Diagnostic/scaffold |
| 09_intraday_coverage_report.md | intraday diagnostic | Diagnostic/scaffold |
| 09_intraday_event_reactions.csv | intraday diagnostic | Diagnostic/scaffold |
| 09_intraday_event_reactions.md | intraday diagnostic | Diagnostic/scaffold |
| 09_intraday_methodology_and_limitations.md | intraday diagnostic | Diagnostic/scaffold |
| 10_momentum_decomposition_table.csv | momentum decomposition | Yes |
| 10_momentum_decomposition_table.md | momentum decomposition | Yes |
| 10_momentum_interpretation.md | momentum decomposition | Yes |
| 11_calendar_time_portfolio_methodology.md | calendar-time portfolio | Yes |
| 11_calendar_time_portfolio_results.csv | calendar-time portfolio | Yes |
| 11_calendar_time_portfolio_results.md | calendar-time portfolio | Yes |
| 12_defensible_claim_matrix.csv | defensible claim matrix | Yes |
| 12_defensible_claim_matrix.md | defensible claim matrix | Yes |
| 13_final_results_section_draft.md | results narrative | Yes |
| 14_final_methodology_section_draft.md | methodology narrative | Yes |
| 15_final_limitations_section.md | limitations | Yes |
| 16_professor_one_page_update.md | professor update | Yes |
| 17_transcript_count_reconciliation.csv | package artifact | Yes |
| 17_transcript_count_reconciliation.md | package artifact | Historical/reconciled caveat |
| 18_runpod_sync_status.md | package artifact | Yes |
| 19_final_result_hierarchy.csv | package artifact | Yes |
| 19_final_result_hierarchy.md | package artifact | Yes |
| 20_factor_result_interpretation.md | package artifact | Yes |
| 21_sec_clean_interpretation.md | package artifact | Yes |
| 22_calendar_time_interpretation.md | package artifact | Yes |
| 23_final_methodology_section_clean.md | package artifact | Yes |
| 24_final_results_section_clean.md | package artifact | Yes |
| 25_final_limitations_section_clean.md | package artifact | Yes |
| 26_final_conclusion_clean.md | package artifact | Yes |
| 27_professor_one_page_clean.md | package artifact | Yes |
| 28_metadata_patch_log.md | package artifact | Yes |
| 29_sec_language_audit.md | package artifact | Yes |
| 30_final_visual_exhibit_plan.md | package artifact | Yes |
| 31_final_abstract_draft.md | package artifact | Yes |
| 32_final_introduction_draft.md | package artifact | Yes |
| 33_final_data_section_draft.md | package artifact | Yes |
| 34_final_methods_section_draft.md | package artifact | Yes |
| 35_final_results_section_draft_v2.md | package artifact | Yes |
| 36_final_discussion_section_draft.md | package artifact | Yes |
| 37_final_limitations_section_draft_v2.md | package artifact | Yes |
| 38_final_conclusion_draft_v2.md | package artifact | Yes |
| 39_presentation_defense_talking_points.md | package artifact | Needs reconciliation caveat |
| 40_runpod_count_reconciliation_audit.csv | RunPod sample-count reconciliation | Yes |
| 40_runpod_count_reconciliation_audit.md | RunPod sample-count reconciliation | Yes |
| 99_final_codex_verification_summary.md | verification summary | Yes |
| deep_dive | package artifact | Yes |
| figures_data | package artifact | Yes |
| final_tables | package artifact | Yes |
| free_news | package artifact | Yes |
| locked_sample | manifest-supported locked-sample files | Yes with caveat |

## Exact Next Bloomberg Step

At school, fill the CSV templates under `data/imports/bloomberg/manual_csv/`,
run `python3 scripts/validate_bloomberg_csv_imports.py`, then rerun the
final package with an explicit Bloomberg-source extension after validation.
