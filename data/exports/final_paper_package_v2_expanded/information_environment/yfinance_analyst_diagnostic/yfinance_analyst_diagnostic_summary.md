# YFinance Analyst Diagnostic

# yfinance analyst diagnostic layer

**diagnostic_yfinance_fallback** — gap-filler until Bloomberg validation. Not authoritative historical evidence unless dated pre-event rows exist.

## Coverage
| Metric | Count |
| --- | ---: |
| Tickers | 19 |
| Events | 2322 |
| Snapshot available | 2322 |
| yfinance event-time usable (dated pre-event) | **2222** |
| Diagnostic current snapshot only | 100 |

## Event-time alignment (yfinance dated only)
| Flag | Count |
| --- | ---: |
| Bullish aligned | 1230 |
| Bearish aligned | 22 |
| Contrarian | 412 |

## Current snapshot alignment (NOT historical event-time proof)
| Flag | Count |
| --- | ---: |
| Current bullish aligned | 1660 |
| Current contrarian | 482 |

## Paper use
- **Allowed:** yfinance improves **diagnostic** analyst-relay coverage; dated pre-event rows support **exploratory** event-time splits only.
- **Prohibited:** Treating current yfinance targets/ratings as historical event-time proof; analyst-news-clean claims.
