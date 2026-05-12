# Presentation Script: Results Section (5 Slides)

## Slide 1 — Sample and Match Quality

### Slide title suggestion
Prototype sample construction and match coverage

### Speaking notes
- "Our strict clean sample contains 132 classified recommendation events from the transcript-based pipeline."
- "We successfully matched 131 of 132 events to market data, a 99.24% match rate."
- "Diagnostics show one unmatched case: `event_id=420` for `SQ`, labeled `no ticker data`."
- "That means the event-study join is high quality overall, with one transparent and documented exception."

### If asked "Why only 132 events?"
- "Because we use the strict rules-only filtered sample, not a looser inclusion rule. At the 0.75 strict threshold, included events are exactly 132."

---

## Slide 2 — What Abnormal Return Means

### Slide title suggestion
Return definitions and event windows

### Speaking notes
- "Abnormal return means stock return minus SPY return over the same horizon."
- "CAR is cumulative abnormal return — the running sum of daily abnormal returns over the window."
- "We evaluate three horizons: 1D, 5D, and 20D, representing immediate, short-run, and medium-run behavior."
- "This setup lets us compare early reaction versus subsequent drift."

### Plain-English line
- "If abnormal return is positive, the stock beat SPY; if negative, it underperformed SPY."

---

## Slide 3 — Core Findings

### Slide title suggestion
Headline prototype results

### Speaking notes
- "At 1D and 5D, average abnormal returns are slightly positive: about +0.43% and +0.34%."
- "At 20D, average abnormal return is negative: about -2.64%."
- "CAR shows the same direction: +0.27% at 5D and -2.69% at 20D."
- "So the pattern is: modest short-run positive association, then weaker medium-run performance."

### If asked "Does this prove finfluencers hurt investors?"
- "No. This is an observational event-study association, not a causal identification design."
- "Safe interpretation is that medium-horizon underperformance appears in this prototype sample."

---

## Slide 4 — Statistical Interpretation

### Slide title suggestion
What is and is not statistically strong

### Speaking notes
- "1D and 5D tests are not statistically significant in this run."
- "20D abnormal return is significant at about the 5% level (`p=0.042973`)."
- "20D CAR is also significant at about the 5% level (`p=0.034335`)."
- "I frame this as suggestive medium-horizon evidence, not definitive proof."

### Caution line
- "Given sample concentration and prototype data quality, significance should be treated as provisional."

---

## Slide 5 — Heterogeneity, Caveats, and Next Step

### Slide title suggestion
Concentration risks and Bloomberg upgrade path

### Speaking notes
- "The sample is concentrated in a few names, especially TSLA (41), AAPL (20), NVDA (18)."
- "Creator and ticker grouped results vary a lot, so pooled means hide heterogeneity."
- "Data source is yfinance prototype; Bloomberg replacement is the next required step."
- "After Bloomberg replacement, we rerun validation, event study, diagnostics, reporting, and charts, then compare sign/magnitude stability."

### If asked "Why use yfinance?"
- "It is a pragmatic prototype source to build and test the full pipeline. It is explicitly not final evidence quality."

### If asked "What changes with Bloomberg?"
- "Potentially both magnitude and significance. Bloomberg rerun is the final quality-control gate before making stronger paper claims."
