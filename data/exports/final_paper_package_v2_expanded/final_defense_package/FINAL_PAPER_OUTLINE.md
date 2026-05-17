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

**Main argument:** Finfluencer literature emphasizes skill heterogeneity and attention; we contribute a large transcript-based event study with explicit falsification, partial news layers, and conservative claim discipline.

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

**Main argument:** Selection into momentum, attention amplification, partial reversal; predictive patterns partly ticker-driven.

**Cite:** `research_frontier/recommendation_selection/`; `attention_amplification/`; `reversal_overreaction/`; `predictive_validity_holdouts/`

**Allowed language:** “Pre-event momentum concentration and post-event attention are consistent with mechanism stories.”

**Prohibited:** “We prove overreaction is tradable.”

**Caveats:** Exploratory tests; multiple comparisons — see `inference_robustness/`.

---

## 7. Confounds and falsification

**Main argument:** Partial AV news layer; SEC flags; placebos shrink event-date narratives; cross-ticker placebo ≈ 0.

**Cite:** `confounds_expanded/`; `news_alpha_vantage_expanded/`; `placebo_matched_controls/`; `market_implied_confounds/`

**Allowed language:** “Partial public-news metadata; unknown treated as not clean; falsification supports selection/attention framing.”

**Prohibited:** “Results survive full public-news controls.”

**Caveats:** Non-top master-clean n=0; GDELT diagnostic only; market-quiet ≠ news-clean.

---

## 8. Portfolio realism

**Main argument:** Concentration, costs, delays, and drawdowns reject tradable strategy claims.

**Cite:** `portfolio_execution_realism/`; `calendar_time_factor_regressions/`

**Allowed language:** “Portfolio diagnostics do not support executable alpha for a general audience.”

**Prohibited:** “Investable strategy.”

**Caveats:** Simplified execution assumptions.

---

## 9. Limitations

**Main argument:** Partial news, automated labels, student data, quota-limited AV, thin 504D.

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
