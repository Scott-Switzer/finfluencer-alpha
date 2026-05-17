# Final presentation defense

---

## 60-second defense

We study **2,341 transcript-supported YouTube stock recommendations**. There is **no defensible broad short-window alpha**.

Results are **heterogeneous**: top mega-cap names show **positive raw** dynamics that **weaken** under factors and placebos; **non-top** names are **weaker over medium horizons**.

Public-news controls are **partial** — Alpha Vantage covers only a few tickers and **unknown is never clean**. GDELT is **diagnostic only**.

Matched controls, cross-ticker placebos (5D ≈ **+0.19%**), and portfolio realism **reject causal skill and tradability**. The **information environment** pass suggests **repackaging** of public/analyst narratives more than original alpha. The story is **attention and ticker selection**, not creator skill.

---

## 3-minute defense

### Question answered

Do YouTube finfluencer recommendations predict abnormal returns in a large transcript-based sample?

### Answer

**Not uniformly.** We reject broad alpha and tradability. We document **heterogeneity** tied to **mega-cap concentration** and **momentum selection**.

### Evidence stack

1. **Baseline:** 2,341 events; SPY-adjusted event studies; top-5 vs non-top split  
2. **Factors:** Calendar-time HAC regressions — full-sample FF5 alpha not defensible  
3. **Mechanism:** Pre-event momentum (especially top-5); attention/volume post-event  
4. **Falsification:** Date-shift placebos; creator cross-ticker placebo ≈ **0** mean 5D difference  
5. **Confounds:** SEC + partial AV; **non-top master-clean n = 0**  
6. **Sensitivity:** Market-quiet non-top 21D ≈ **-0.56%** — not AV-clean identification  
7. **Information environment:** transcript relay scores; sentiment conditioning; incremental predictive value over market baselines weak for broad alpha  

### What we refuse to claim

- Causal creator skill  
- Investable strategy  
- Full news-clean robustness  
- 504D alpha without censoring caveats  

---

## Likely professor questions — and direct answers

### “Is this alpha?”

**No broad alpha.** Subsample raw positives for top names do not survive as a general tradable claim.

### “Did you control for news?”

**Partially.** Alpha Vantage compact metadata on limited tickers. **1,657 events remain unknown** and are **not** coded clean. We cannot validate non-top results on a news-clean subsample (**n = 0**).

### “Is this just momentum?”

**Partly.** Top-5 recommendations align with prior momentum; selection tests and factor adjustments support concentration/momentum framing over skill.

### “Can I trade this?”

**No.** Portfolio execution realism rejects tradability (costs, concentration, drawdowns).

### “Did creators cause returns?”

**We do not claim causality.** Placebos and cross-ticker falsification break a clean event-study causal story.

### “What about long horizons?”

**504D is diagnostic only** — overlap, censoring, and thin full-window support. Medium horizons (21D–63D) are more central for non-top weakness.

### “How good is your event detection?”

Automated with proxy QA (`event_quality_deep_audit/`). We do not claim manual verification of every transcript.

### “Why should I trust v2?”

Validators pass on RunPod; locked manifests; public repo audit and safety checks; conservative claim matrix.

---

## Prohibited claims (do not say in Q&A)

| Do not say |
| --- |
| “YouTube recommendations generate alpha.” |
| “We controlled for all news.” |
| “Short non-top recommendations for profit.” |
| “Creators have stock-picking skill.” |
| “Our strategy is tradable.” |
| “504D proves long-term outperformance.” |
| “Unknown events are clean.” |

---

## Allowed one-liner

**“Heterogeneous attention and selection in mega-cap names — not causal finfluencer alpha.”**
