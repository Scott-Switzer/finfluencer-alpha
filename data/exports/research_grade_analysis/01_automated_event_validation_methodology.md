# Automated Event Validation Methodology

## Why No Full Manual Audit

A full manual audit of 1,554 accepted recommendation events is not feasible for
this research-grade pass. A defensible manual audit would require at least
3-5 minutes per event for transcript context retrieval, recommendation
classification verification, and bookkeeping. At ~4 minutes per event, the full
sample alone is ~104 hours of single-rater work, before any second-rater
adjudication. The course timeline (Bloomberg validation expected in roughly
two days) cannot absorb that cost, and our goal is reproducible, auditable
inference rather than rater-bottlenecked inference.

## How Automated Validation Substitutes

The automated validator (`scripts/build_research_grade_analysis.py`) produces a
per-event quality score (0-100) and a tier (A/B/C/D) from auditable inputs that
the data already contains:

1. Transcript evidence traceability: presence and length of the
   `transcript_recommendation_events.evidence_window` text.
2. Directional language strength: lexicon match for explicit
   buy/sell/hold/own/add/trim language consistent with the classifier-assigned
   stance.
3. Conditionality and hedging: penalty for "if/might/could/may" patterns that
   would weaken a directional reading.
4. Recap/past-call risk: penalty for "I said/told you/remember when" phrasing
   that flags retrospective rather than forward calls.
5. News-only risk: penalty when the evidence window reads as a news summary
   ("according to/Reuters/Bloomberg reports/press release") without a
   first-person recommendation signal.
6. Ticker/company sanity: bonus when both ticker and company name are
   populated; penalty when the ticker appears on a common-word ambiguity
   watchlist (`NOW`, `ALL`, `ON`, `RUN`, etc.).
7. Duplicate-cluster risk: penalty for events that share creator+ticker+date
   with other events (collapsed by weekday-adjusted date).
8. Concentration flags: down-weight for top-5 ticker or top-5 creator
   membership, since those drive the headline mean by construction.
9. Market data coverage: heavy penalty when no on-or-after trading day exists
   in the local market-data CSV for the event's data ticker.
10. Outlier and high-impact flags: bookkeeping flags for |AR_1D| > 10% and
    AR_1D in the sample top/bottom 5% so downstream code can run high-impact
    cuts without re-deriving thresholds.
11. Classifier confidence: bonus/penalty bands around 0.45 / 0.60 / 0.75 of the
    rule-classifier confidence score already stored on the event row.

Reason codes (see `REASON_CODE_DESCRIPTIONS` in the script) are emitted in a
semicolon-joined `reason_codes` column so every score is auditable: any review
can replay the contribution of every code without rerunning the model.

## Where LLM Adjudication Belongs

This pass does not invoke any external LLM. The intended adjudication scope
for any future LLM pass is narrow and high-risk only:

- D-tier events with `news_only_risk`, `recap_risk`, or `weak_directional_signal`
  flags.
- Events with `ambiguous_ticker` flag (ticker on common-word watchlist).
- Duplicate-cluster heads where every member event tied to the same creator,
  ticker, and trading day might warrant collapsing to a single observation.

The repo already contains a `classifier_ai_audit/` directory with prior
adjudication output schema; that schema can absorb an LLM second pass without
new infrastructure.

## Optional 10-15 Minute Human Spot-Check

A 20-30 event spot-check is sufficient to detect catastrophic validator drift
(direction inversions, evidence quotes that contradict the recommendation
type, ticker collisions, mass duplication). The sample is built by
`04_quick_spot_check_sample.csv` and is composed of five buckets:

- Top 5 highest positive 1D abnormal returns.
- Top 5 most negative 1D abnormal returns.
- 5 lowest-quality-score accepted events.
- 5 duplicate-cluster events (largest creator+ticker+date clusters).
- 5 random events drawn with a fixed seed for reproducibility.

The reviewer fills `quick_review_result` (`agree`/`disagree`/`unsure`) and
`quick_notes` directly. The CSV is the audit artifact; no separate notebook is
required. Disagreement rates above 20% on the four targeted buckets should
trigger a focused LLM adjudication pass before any inference is reported as
research-grade.

## Audit Trail

For every accepted event the validator preserves:

- `event_id` (`transcript_event_id` primary key),
- raw stance and detected action from the classifier,
- evidence window length and a truncated evidence quote,
- duplicate-cluster id and size,
- a semicolon-joined list of validation flags and reason codes.

This means the per-event score can be recomputed from the database snapshot at
any time and any disagreement can be localized to a specific reason code.
