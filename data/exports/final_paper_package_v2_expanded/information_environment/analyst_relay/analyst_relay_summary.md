# Analyst Relay Summary

# Analyst relay layer (FMP / Finnhub / yfinance)

## Provider status
| provider | status | key_source |
| --- | --- | --- |
| FMP | active | marketdata_env |
| Finnhub | active | marketdata_env |
| yfinance | diagnostic_fallback |  |

## A. Event-time analyst evidence
| Metric | Count |
| --- | ---: |
| Total events | 2322 |
| Event-time analyst usable (combined) | **2299** |
| yfinance dated pre-event usable | 2222 |
| Analyst unknown (no usable coverage) | **0** |
| Top-5 event-time usable | 1362 |
| Non-top event-time usable | 937 |

Event-time source counts: {'yfinance': 1853, 'finnhub': 446, 'none': 23}

Event-time alignment: {'analyst_bullish_aligned': 1385, 'analyst_neutral_or_mixed': 468, 'finfluencer_contrarian_to_analyst': 450, 'analyst_bearish_aligned': 19}

**Paper use:** Only dated pre-event FMP/Finnhub/yfinance rows support event-time relay claims. Unknown ≠ clean.

## B. yfinance diagnostic current snapshot evidence
| Metric | Count |
| --- | ---: |
| Diagnostic current-only (combined) | **23** |
| yfinance diagnostic current-only flagged | 100 |
| yfinance fallback flagged | 1876 |

Diagnostic alignment: {'analyst_bullish_aligned': 1660, 'finfluencer_contrarian_to_analyst': 482, 'analyst_neutral_or_mixed': 180}

**Warning:** Current yfinance recommendation keys and price targets are **current-snapshot diagnostics only** — not historical event-time proof.

## C. Event-time vs diagnostic comparison
| Metric | Count |
| --- | ---: |
| Events with both event-time and diagnostic fields | 2299 |
| Agreement (same alignment label) | 1751 |

Do not treat diagnostic-current agreement as validation of historical analyst positioning.

## D. Impact on thesis (exploratory)
- Top-5 positives: inspect whether event-time alignment is bullish/contrarian/unknown in `returns_by_analyst_alignment.md`.
- Non-top weakness: check whether analyst evidence is aligned, contrarian, or unknown — not causal skill.
- yfinance improves **coverage** for narrative-relay classification; it does **not** strengthen causal identification.

Coverage tier: {'event_time_yfinance': 1853, 'event_time_primary_provider': 446, 'diagnostic_current_snapshot': 23}

### Allowed paper language
- "yfinance is used more aggressively as a diagnostic gap-filling analyst layer pending Bloomberg validation."
- "Partial dated analyst metadata suggests relay with observable consensus where event-time fields exist."

### Prohibited
- Full analyst-news-clean or public-news-clean robustness.
- Causal finfluencer skill, tradability, or using current yfinance snapshots as historical proof.
