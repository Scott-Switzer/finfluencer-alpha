# Analyst Relay Limitations

# Analyst relay limitations

- FMP/Finnhub remain preferred when usable; yfinance fills gaps as **diagnostic_yfinance_fallback**.
- Current-only yfinance snapshots are diagnostic — not event-time historical evidence.
- Bloomberg analyst exports are the planned authoritative validation path.
- Unknown analyst coverage must never be coded as clean.
- Alignment is descriptive co-movement with consensus, not skill or tradability.
