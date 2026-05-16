# Transcript Feature Engineering Plan

## Inputs

- `transcript_recommendation_events.evidence_window`: ~100-1000 character
  evidence span anchored on the ticker/company mention.
- `youtube_transcripts.full_text`: full transcript body, available locally for
  most accepted events.

## Codebook

| Feature | Type | Definition | Heuristic Implementation |
| --- | --- | --- | --- |
| `directness` | ordinal 0-3 | How explicitly the speaker recommends action | 0 if no first-person verb; 1 if "considering"; 2 if "I am buying"; 3 if "you should buy" |
| `conviction` | ordinal 0-3 | Tone strength | 0 hedged; 1 cautious; 2 confident; 3 emphatic (caps, repetition) |
| `urgency` | ordinal 0-2 | Time pressure | 0 none; 1 weekly horizon ("this week"); 2 immediate ("right now") |
| `time_horizon` | categorical | Trade horizon | short / medium / long, from lexicon matches |
| `valuation_basis` | binary | Mentions valuation multiple | True if any of P/E, DCF, EV/EBITDA, multiple, fair value |
| `catalyst_type` | categorical | Reason | earnings / product / macro / regulatory / unspecified |
| `risk_disclosure` | binary | DYOR / risk language | True if "not financial advice", "do your own research", "risk" |
| `position_disclosure` | binary | Speaker discloses own position | True if "I own", "in my portfolio", "I hold" |
| `conditionality` | ordinal 0-3 | Recommendation contingent on a condition | count of "if/might/could/may"-style hedges |
| `new_vs_update` | categorical | New call vs reiteration | new / update / recap |
| `sentiment_intensity` | float -1..1 | Strength of bullish/bearish tone | Lexicon polarity score over evidence window |
| `specificity` | ordinal 0-3 | Specific price targets vs generic | 0 generic; 1 directional only; 2 numeric levels; 3 numeric levels with timing |

## Default Implementation (Rule-Based, Auditable)

```python
def extract_features(evidence: str, stance: str) -> dict:
    text = evidence.lower()
    features = {}
    features["directness"] = ... # phrase-table lookups
    features["conviction"] = ... # tone heuristics: caps ratio, exclamation, repetition
    features["urgency"] = 2 if "right now" in text or "today" in text else (1 if "this week" in text else 0)
    features["time_horizon"] = "long" if any(p in text for p in TIME_HORIZON_PHRASES_LONG) else ...
    features["valuation_basis"] = any(p in text for p in VALUATION_PHRASES)
    ...
    return features
```

Phrase tables live alongside the script (see `POSITIVE_REC_PHRASES`,
`NEGATIVE_REC_PHRASES`, `CONDITIONALITY_PHRASES`, `RECAP_PHRASES`,
`POSITION_DISCLOSURE`, `URGENCY_PHRASES`, `TIME_HORIZON_PHRASES_SHORT`,
`TIME_HORIZON_PHRASES_LONG`, `VALUATION_PHRASES`, `CATALYST_PHRASES`,
`RISK_DISCLOSURE` in `scripts/build_research_grade_analysis.py`).

## Optional NLP Layer (Future)

- FinBERT (`yiyanghkust/finbert-tone`) sentiment polarity over the evidence
  window. Already wired in the codebase as an optional pass
  (`finbert_*` columns in `transcript_recommendation_events`); needs activation.
- DistilBERT-based zero-shot classification for catalyst type
  ("earnings", "product launch", "macro", "regulatory") with hypothesis
  templates per class.
- LLM-based scoring (gpt-4o-mini or local Llama) for `directness`,
  `conviction`, and `specificity` with rubric-driven prompts; held to
  inter-rater agreement of >= 0.7 vs the rule-based baseline before adoption.

## Output

- `transcript_features.csv` with one row per event_id:
  event_id, every feature, plus `feature_extractor_version`.
- Features are correlated with abnormal returns in a dedicated robustness
  section: each feature enters the OLS in `08_momentum_decomposition_results.csv`
  Model 5 augmentation as a continuous or binary control.

## Privacy and Redistribution

- Full transcripts remain in the local SQLite database and are not committed.
- Only the evidence quote and the derived features are exported.
- Any LLM call goes via a model with a redistribution-safe license; outputs
  store only the structured feature, not the prompt or the model output text.
