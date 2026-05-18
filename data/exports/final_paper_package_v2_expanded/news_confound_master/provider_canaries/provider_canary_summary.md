# Provider canaries

Minimal calls per provider. Authentication is **not** logged. See `provider_canary_status.csv`.

## Interpretation

- `proceed=yes` means the canary returned HTTP OK for at least one ticker/window.
- `403/429` must be treated as provider-limited in downstream layers, not as clean no-news.
