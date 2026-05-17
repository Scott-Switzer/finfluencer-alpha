# Analyst Relay Summary

# Analyst relay layer (event-time validation)

## Provider status
| provider | status | key_source |
| --- | --- | --- |
| FMP | active | marketdata_env |
| Finnhub | active | marketdata_env |
| yfinance | diagnostic_fallback |  |

## Coverage
| Metric | Count |
| --- | ---: |
| Total events | 2322 |
| Event-time analyst usable | **446** |
| Diagnostic current-only | **0** |
| yfinance diagnostic fallback flagged | **1876** |
| Analyst unknown | **1876** |
| Bullish aligned | 320 |
| Bearish aligned | 0 |
| Contrarian to analyst | 97 |
| Analyst relay likely | 417 |
| Top-5 event-time usable | 224 |
| Non-top event-time usable | 222 |

## Interpretation
- **FMP/Finnhub** are primary; **yfinance** is `diagnostic_yfinance_fallback` only — not authoritative historical evidence unless dated pre-event rows exist.
- **Unknown analyst ≠ clean.** Current-only snapshots cannot support event-time causal claims.
- Inspect `returns_by_analyst_alignment.md` for whether aligned vs contrarian buckets differ economically.

### Allowed paper language
- "Partial dated analyst metadata suggests many calls align with observable Wall Street consensus (relay), not independent information."
- "yfinance fills coverage gaps as a diagnostic fallback pending Bloomberg validation."

### Prohibited
- "Results are analyst-news-clean."
- "yfinance proves historical analyst alignment at event time" (unless `analyst_event_time_usable`).
- Causal skill, tradability, or full public-news-clean robustness.
