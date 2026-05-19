# Final paper outline

Use this outline for the FIN 496 write-up. Every section lists **argument**, **tables/figures**, **claim language**, and **caveats**.

---

## 1. Introduction

**Main argument:** YouTube finfluencer stock recommendations are economically important for retail attention but do not constitute a uniform profitable signal in our expanded transcript-supported sample.

**Cite:** `FINAL_CLAIM_MATRIX.md`; sample counts in `locked_sample_v2/`

**Allowed language:** “We study 2,341 transcript-supported recommendation events…”

**Prohibited:** “YouTube recommendations generate alpha.”

**Caveats:** Student research; not investment advice.

---

## 2. Literature and contribution

**Main argument:** Finfluencer literature emphasizes skill heterogeneity and attention; we contribute a large transcript-based event study with explicit falsification, multi-provider news diagnostics, and conservative claim discipline.

**Cite:** `literature_positioning/01_literature_comparison_matrix.csv`

**Allowed language:** “Consistent with attention and selection rather than causal skill.”

**Prohibited:** “First proof of finfluencer alpha.”

**Caveats:** Not a Bloomberg replication; U.S. YouTube sample.

---

## 3. Data and sample construction

**Main argument:** v2 primary sample = 2,341 accepted events from RunPod DB; v1 is benchmark only.

**Cite:** `locked_sample_v2/02_v2_event_manifest.csv`; `validate_expanded_primary_sample_package.py` output

**Allowed language:** “Expanded v2 is our primary empirical sample.”

**Prohibited:** “We use all YouTube finance content.”

**Caveats:** Automated event detection; exclusions documented.

---

## 4. Event detection methodology

**Main argument:** Recommendations extracted from transcripts with quality scores; buy/sell stance; timing buckets; duplicate clustering.

**Cite:** `event_quality_deep_audit/`; `validation/` exports

**Allowed language:** “Transcript-supported recommendations with proxy quality audit.”

**Prohibited:** “Manually verified every event.”

**Caveats:** No full manual transcript audit in this repo.

---

## 5. Baseline return results

**Main argument:** No broad short-window alpha; heterogeneity between top-5 and non-top; medium-horizon non-top weakness.

**Cite:** `long_horizon/03_v2_long_horizon_summary_by_spec.csv`; `04_v2_long_horizon_top5_vs_non_top.csv`

**Allowed language:** “Top mega-cap recommendations show positive raw short-window abnormal returns; non-top recommendations underperform over medium horizons.”

**Prohibited:** “Finfluencers beat the market.”

**Caveats:** SPY-adjusted BHAR; overlap; right-censoring on long windows.

---

## 6. Mechanism and robustness tests

**Main argument:** Selection into momentum, attention amplification, partial reversal; **information environment** tests whether speech repackages analyst/public narratives vs incremental YouTube signal.

**Cite:** `research_frontier/`; `information_environment/` (analyst relay, sentiment regimes, transcript narrative relay, originality taxonomy, incremental predictive value); `PRIMARY_SECONDARY_EXPLORATORY_HIERARCHY.md`

**Allowed language:** “Evidence is consistent with retail-facing relay of public Wall Street narratives and attention/hype language, not incremental alpha over market baselines.” “Improved analyst grade normalization helps classify dated analyst stance, but does not establish causality.”

**Prohibited:** “We prove overreaction is tradable.”; “Analyst snapshots prove event-time alignment.”; “Current yfinance snapshots are historical analyst evidence.”

**Caveats:** Exploratory tests; 57/73 BH FDR 10% survival does not upgrade tier; holdout AUC ≠ tradability; yfinance is diagnostic unless a dated pre-event record exists; Bloomberg is an institutional mechanism layer, not causal identification.

---

## 7. Confounds and falsification

**Main argument:** Multi-provider news master still leaves no usable clean-news sample; SEC flags and media hits explain many events; placebos shrink event-date narratives; cross-ticker placebo ≈ 0.

**Cite:** `news_confound_master/`; `confounds_expanded/`; `news_alpha_vantage_expanded/`; `placebo_matched_controls/`; `market_implied_confounds/` (non-top + market_quiet 21D ≈ **-0.56%**)

**Allowed language:** “Multi-provider public-news coverage remains incomplete; unknown treated as not clean; cross-ticker placebo 5D ≈ **+0.19%**; falsification supports selection/attention framing.”

**Prohibited:** “Results survive full public-news controls.”

**Caveats:** Multi_source_clean n=0; GDELT diagnostic only; market-quiet ≠ news-clean; analyst unknown ≠ clean; current yfinance snapshots diagnostic only.

---

## 8. Portfolio realism

**Main argument:** Concentration, costs, delays, and drawdowns reject tradable strategy claims.

**Cite:** `portfolio_execution_realism/`; `calendar_time_factor_regressions/`

**Allowed language:** “Portfolio diagnostics do not support executable alpha for a general audience.”

**Prohibited:** “Investable strategy.”

**Caveats:** Simplified execution assumptions.

---

## 9. Limitations

**Main argument:** Partial news, automated labels, student data, provider coverage limits, thin 504D.

**Cite:** `LIMITATIONS_AND_THREATS.md`; `long_horizon_claim_controls/`

**Allowed language:** Enumerate limitations explicitly.

**Prohibited:** Burying non-top clean n=0 or unknown-news coding.

**Caveats:** None — this section is the caveats.

---

## 10. Conclusion

**Main argument:** Heterogeneous dynamics, not broad alpha; policy-relevant attention story; no causal skill or tradability.

**Cite:** `CLAIM_DISCIPLINE_TABLE.md`

**Allowed language (closing):** “Evidence is consistent with attention concentration and ticker selection in mega-cap momentum names, while non-top recommendations show weaker medium-horizon performance that we cannot validate on a public-news-clean subsample.”

**Prohibited:** “Trade on finfluencer signals.”

**Caveats:** Reiterate unknown ≠ clean and 504D diagnostic only.

## May 2026 — news layer and claim discipline (RunPod)

- **No broad tradable YouTube alpha**; heterogeneity and salience matter more than uniform creator skill.
- **Top-5 raw positives** reflect concentration, consensus relay, and attention—not causal creator skill.
- **Non-top weakness** is **not** automatically public-news-clean; **unknown_news_coverage is never clean**.
- **multi_source_clean** is strict (may be zero); provider failures, **403/429**, missing keys, and shallow history are **not** “no news.”
- **FNSPID** adds historical *media* coverage (not official disclosure) through about 2023 but does not cover every recent event window.
- **Marketaux, EODHD, Alpaca/Benzinga, Massive/Polygon, NewsAPI** are free-tier **diagnostic** supplements; **NewsAPI** developer tiers are not a historical backbone.
- **yfinance** analyst snapshots in this repo are **diagnostic only** unless dated pre-event rows exist; they are **not** Bloomberg-grade validation.
- Report **news sensitivity bounds** because public-news identification remains incomplete; frame conclusions as **mechanism-consistent**, not causal.
