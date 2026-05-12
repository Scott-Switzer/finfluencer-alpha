# Presentation-Ready Findings (FIN 496 Prototype)

## 5 headline findings

1. Clean sample contains **132** strict-rule events; **131** matched to market data (99.24% match rate).
2. Mean abnormal returns are mildly positive at short horizons (`+0.43%` at 1D, `+0.34%` at 5D).
3. Mean abnormal return at 20D is negative (`-2.64%`), with significant t-test (`p=0.042973`).
4. Mean CAR also turns negative by 20D (`-2.69%`, `p=0.034335`), despite small positive 5D CAR.
5. Sample is concentrated (notably `TSLA=41`, `AAPL=20`, `NVDA=18`), so pooled results reflect concentration effects.

## 5 methodology talking points

1. Events are transcript/metadata-derived and then rules-filtered into a strict clean sample.
2. Market data is interim yfinance/Yahoo prototype and benchmark-adjusted to SPY.
3. Event-study windows are 1D/5D/20D to separate immediate vs short vs medium-run patterns.
4. Match diagnostics explicitly audit unmatched events and classify likely reasons.
5. Reporting layer provides grouped tables (creator/ticker/year/type/direction) plus charts and robustness context.

## 5 caveats / limitations

1. Data source is prototype yfinance, not Bloomberg (final inference requires replacement).
2. Sample is rules-filtered, not hand-labeled gold-standard validation.
3. Ticker and creator concentration may bias pooled estimates.
4. Observational design cannot establish causality.
5. Recent events may have incomplete forward windows depending on horizon.

## 5 likely professor questions (with strong answers)

1. **Q:** Why should we trust these results if data is yfinance?  
   **A:** We treat these as interim prototype estimates only; Bloomberg replacement is the required final step before inference claims.

2. **Q:** Does this prove finfluencers move stocks?  
   **A:** No. This is associational event-study evidence; we do not claim causal identification from this setup.

3. **Q:** Why is there one unmatched event?  
   **A:** Diagnostics isolate one unmatched row (`event_id=420`, `SQ`, 2020-12-07) with reason `no ticker data`; overall match rate remains 99.24%.

4. **Q:** Could concentration in TSLA/NVDA/AAPL drive results?  
   **A:** Yes, that is a key limitation; grouped outputs and future robustness checks are designed to quantify concentration sensitivity.

5. **Q:** How do you handle ticker changes like SQ -> XYZ?  
   **A:** Alias mapping resolves market ticker continuity while preserving original event ticker for auditability.

## 3 slides worth of results bullets

### Slide 1: Sample and match quality

- Clean strict sample: 132 events
- Matched events: 131 (99.24%)
- One unmatched event documented with explicit reason
- Data currently interim yfinance prototype

### Slide 2: Core return results

- Mean abnormal return: +0.43% (1D), +0.34% (5D), -2.64% (20D)
- Mean CAR: +0.27% (5D), -2.69% (20D)
- 20D abnormal and 20D CAR are statistically significant at ~5%
- 1D/5D tests are not statistically significant

### Slide 3: Heterogeneity and caution

- Strong concentration in TSLA/AAPL/NVDA and top creators
- Grouped estimates vary materially across creators and tickers
- Interpret as associational pattern, not causal effect
- Bloomberg replacement + robustness checks are required before final thesis claims

## Final takeaway

This prototype finds a pattern of modest short-horizon positive abnormal performance and weaker (negative) medium-horizon performance in a highly matched but concentrated sample. The result is informative for research design and presentation, but final FIN 496 inference should be framed cautiously and updated after Bloomberg data replacement and concentration-focused robustness checks.
