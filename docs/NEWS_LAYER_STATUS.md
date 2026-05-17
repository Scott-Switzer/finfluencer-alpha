# News layer status

## Alpha Vantage (NEWS_SENTIMENT)

- Stores **compact metadata only** (counts, truncated titles, flags). No raw article bodies or API keys in exports.
- **Coverage:** partial (~4 tickers under free-tier daily limits); ticker-chunk mode with resume.
- **Expanded panel counts:** 98 clean / 586 confounded / 1,657 unknown (of 2,341 events).

### Critical rule

**Unknown coverage is never treated as clean.**

Events without a successful provider query remain **unknown**, not “no news.”

## GDELT

- **Diagnostic only.** Retry success rate ~**28%** — below threshold for headline robustness claims.
- Do **not** cite GDELT-clean samples as confirmatory.

## SEC / earnings

- Expanded SEC/earnings flags feed the master confound panel.
- See `confounds_expanded/` for merged clean / confounded / unknown counts.

## Market-implied activity screen

- Separate layer in `market_implied_confounds/`
- Flags pre-event return/volume **z-scores** (market-quiet vs market-active)
- **Not** equivalent to public-news-clean — sensitivity for abnormal pre-event trading only
- Example: non-top + market_quiet 21D SPY BHAR ≈ **-0.56%**

## Analyst relay (optional FMP / Finnhub + yfinance diagnostic)

- Module: `information_environment/analyst_relay/`
- **Priority:** FMP stable API → Finnhub recommendation trends → **yfinance** (`diagnostic_yfinance_fallback` only)
- Keys load from env or `/root/.config/fin496/marketdata.env` (never committed)
- **Dated** consensus/revisions → `analyst_event_time_usable` when pre-event rows exist
- **Latest-only** / yfinance snapshots → not authoritative historical proof
- Finnhub free tier: monthly bins often **2026-only** — limited event-study depth
- FMP may **rate-limit** on bulk pulls; re-run with `FIN496_FORCE_ANALYST_RELAY=1` after cooldown
- Unknown analyst coverage is **never clean**

## Transcript narrative relay

- Evidence-window keyword scores only (no full transcript export)
- Tests whether language resembles Wall Street / earnings / hype relay

## Paper language

| Allowed | Prohibited |
| --- | --- |
| Partial real-news metadata; unknown is not clean | Results survive complete public-news controls |
| GDELT attempted but unreliable for main robustness | GDELT validates the finding |
| Market-quiet sensitivity slice | News-clean identification |
