# Analyst Relay Limitations

# Analyst relay limitations

- FMP/Finnhub free tiers may rate-limit; errors are logged in `analyst_relay_provider_request_log_safe.csv` (no raw bodies).
- yfinance is **diagnostic_yfinance_fallback** — gap-filler until Bloomberg exports validate.
- Monthly Finnhub recommendation bins are coarse vs daily upgrades.
- Alignment describes co-movement with observable consensus, not finfluencer skill.
- Unknown analyst coverage must never be coded as clean.
