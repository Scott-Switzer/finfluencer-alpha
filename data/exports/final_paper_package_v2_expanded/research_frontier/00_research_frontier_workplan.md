# Research Frontier Workplan

Maps FIN 496 v2 extensions to finfluencer / event-study literature themes. **No broad alpha claim.** Mechanism, falsification, and robustness only.

| Literature theme | Our test module | Primary outputs | Claim posture |
| --- | --- | --- | --- |
| Finfluencer skill vs popularity | `build_v2_creator_skill_taxonomy.py` | `creator_skill_taxonomy/` | Heterogeneity; skill-like labels only |
| Selection into momentum / high-volume names | `build_v2_recommendation_selection_tests.py` | `recommendation_selection/` | Supports selection mechanism |
| Short-lived sentiment / attention | `build_v2_attention_amplification_tests.py` | `attention_amplification/` | Attention amplification if vol↑, alpha weak |
| Attention-induced trading | attention + placebo modules | combined | Diagnostic / mechanism |
| Disagreement / volume | prior & post abnormal volume | selection + attention | Partial (volume proxy only) |
| Event-study inference risks | `build_v2_placebo_matched_control_expansion.py` | `placebo_matched_controls/` | Falsification; causal rejected |
| Public-news confounding | existing `confounds_expanded/` + frontier splits | confound panels | Partial; unknown ≠ clean |
| Long-horizon fragility | `build_v2_reversal_overreaction_tests.py` + long_horizon controls | reversal + 504D downgrade | 504D diagnostic only |
| Language / hype / disclosure | `build_v2_transcript_quality_language_tests.py` | `transcript_language_quality/` | Descriptive; snippet-only |
| Predictability / tradability | `build_v2_predictive_validity_tests.py` | `predictive_validity/` | Strategy value limited if OOS weak |

## Execution order (RunPod)

```bash
cd /workspace/FIN496CAPSTONE
.venv/bin/python3 scripts/build_v2_recommendation_selection_tests.py
.venv/bin/python3 scripts/build_v2_attention_amplification_tests.py
.venv/bin/python3 scripts/build_v2_reversal_overreaction_tests.py
.venv/bin/python3 scripts/build_v2_creator_skill_taxonomy.py
.venv/bin/python3 scripts/build_v2_transcript_quality_language_tests.py
.venv/bin/python3 scripts/build_v2_placebo_matched_control_expansion.py
.venv/bin/python3 scripts/build_v2_predictive_validity_tests.py
.venv/bin/python3 scripts/build_v2_research_frontier_docs.py
```

## Hard rules

- Unknown news coverage is **never** clean.
- No Apify, no new transcripts, no X in main sample, no Bloomberg.
- Do not commit secrets, raw DBs, raw transcripts, or bulky API caches.
