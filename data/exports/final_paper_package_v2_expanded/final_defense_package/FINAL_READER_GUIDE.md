# Final reader guide

**Start here** if you are grading, replicating, or writing the FIN 496 paper from this repository.

Frozen research HEAD: `5858d69`

---

## Where to start (5-minute path)

1. Read `PROFESSOR_DEFENSE_60_SECOND.md` and `CLAIM_DISCIPLINE_TABLE.md`
2. Skim `FINAL_CLAIM_MATRIX.md` or `docs/CLAIM_MATRIX.md`
3. Open `locked_sample_v2/02_v2_event_manifest.csv` (2,341 events)
4. Review `long_horizon/04_v2_long_horizon_top5_vs_non_top.csv`
5. Read `LIMITATIONS_AND_THREATS.md`

For the full paper draft structure, see `FINAL_PAPER_OUTLINE.md`.

---

## Core sample files

| File | Purpose |
| --- | --- |
| `locked_sample_v2/02_v2_event_manifest.csv` | Primary event universe |
| `locked_sample_v2/01_v2_transcript_manifest.csv` | Transcript-video inventory |
| `long_horizon/01_v2_long_horizon_event_returns.csv` | Event-level returns by horizon |
| `long_horizon/02_v2_long_horizon_coverage.csv` | Coverage and censoring |

---

## Core result files

| Topic | Location |
| --- | --- |
| Top-5 vs non-top returns | `long_horizon/04_v2_long_horizon_top5_vs_non_top.csv` |
| Calendar-time factor regressions | `calendar_time_factor_regressions/01_calendar_time_hac_regressions.csv` |
| Master confounds | `confounds_expanded/01_v2_master_confound_panel_expanded.csv` |
| Market-quiet sensitivity | `market_implied_confounds/returns_by_market_confound_bucket.csv` |
| Placebos / falsification | `research_frontier/placebo_matched_controls/` |
| Portfolio realism | `portfolio_execution_realism/` |
| 504D claim control | `long_horizon_claim_controls/` |

---

## Claim matrix and discipline

| Document | Use |
| --- | --- |
| `CLAIM_DISCIPLINE_TABLE.md` | Allowed vs prohibited wording |
| `FINAL_CLAIM_MATRIX.md` | Status by claim |
| `RESULTS_NARRATIVE_SAFE.md` | Conservative results prose |
| `PUBLIC_REPO_AUDIT.md` | GitHub / main branch posture |

---

## Limitations (do not skip)

| Issue | Implication |
| --- | --- |
| AV partial coverage (~4 tickers) | Unknown ≠ clean |
| Non-top master-clean **n = 0** | No public-news-clean non-top test |
| GDELT ~28% success | Diagnostic only |
| 504D thin / censored | Diagnostic only |
| Automated classification | Proxy QA only |

Full list: `LIMITATIONS_AND_THREATS.md`

---

## Reproduction

- **Public clone:** run validators + `pytest` (see `docs/REPRODUCIBILITY.md`)
- **Full rebuild:** RunPod + private DB — `REPRODUCTION_COMMANDS.md`

---

## Public vs private

| Public (GitHub) | Private (RunPod) |
| --- | --- |
| CSV/MD exports, scripts | `finfluencer_alpha.db` |
| Claim matrices, guides | Raw transcripts |
| Hashed asset manifest | API keys, news caches |

See `LOCAL_ASSET_MANIFEST.md` and `docs/DATA_AVAILABILITY.md`.

---

## What **not** to claim

- Broad YouTube alpha
- Causal creator skill
- Tradable finfluencer strategy
- Full public-news-clean robustness
- GDELT-confirmed clean samples
- Two-year (504D) alpha without censoring caveats

**Unknown news is never clean.**
