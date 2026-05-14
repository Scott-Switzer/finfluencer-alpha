# X-native creator target windows (checkpoint 1 design)

Generated: 2026-05-14T20:35:00Z

Primary CSV: `data/exports/research_expansion/all_clean_events.csv`.

Windows: **event date UTC minus 3 days through plus 3 days** (inclusive end-of-day). Actor: `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest` with repo `build_x_actor_input()` (`searchTerms`, `since_time`, `until_time`, `maxItems`, `queryType`, `lang`).

Planned `maxItems` for checkpoint script: **35** per row unless overridden by `X_CHECKPOINT_MAX_ITEMS`.

| Priority | X search term | X handle (if any) | Linked YouTube ticker | YouTube event date | YouTube creator | YouTube video ID | Window start | Window end | since_time | until_time | Query type | maxItems | Selection reason |
|---:|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `from:ThePlainBagel $GOOGL` | ThePlainBagel | GOOGL | 2023-10-27 | The Plain Bagel | wBjBs0VibaY | 2023-10-24 | 2023-10-30 | 1698105600 | 1698710399 | x-creator-authored | 35 | Clean-event row; mapped creator; historical window. |
| 2 | `from:ThePlainBagel $NVDA` | ThePlainBagel | NVDA | 2024-12-28 | The Plain Bagel | nKHzfQd4lOo | 2024-12-25 | 2024-12-31 | 1735084800 | 1735689599 | x-creator-authored | 35 | High-salience NVDA mention; narrow holiday window. |
| 3 | `from:EverythingMoney $MSFT` | EverythingMoney | MSFT | 2025-10-11 | Everything Money | 8ZllCsuVEaM | 2025-10-08 | 2025-10-14 | 1759881600 | 1760486399 | x-creator-authored | 35 | Seed list match for “Everything Money”; ticker-specific education channel. |
| 4 | `$MSFT` | — | MSFT | 2024-07-14 | New Money | dsVxaGMD2q8 | 2024-07-11 | 2024-07-17 | 1720656000 | 1721260799 | ticker-only-control | 35 | No deterministic X handle mapping; keep as **labeled control**. |
| 5 | `$META` | — | META | 2026-04-09 | Kenan Grace | wwIh2NK3GMM | 2026-04-06 | 2026-04-12 | 1775433600 | 1776038399 | ticker-only-control | 35 | Forward-dated clean event; control for attention spike testing. |
| 6 | `from:ThePlainBagel $AMC` | ThePlainBagel | AMC | 2024-05-31 | The Plain Bagel | JooqHEF0kBo | 2024-05-28 | 2024-06-03 | 1716854400 | 1717459199 | x-creator-authored | 35 | Meme-name volatility window; creator-specific. |
| 7 | `from:ThePlainBagel $DIS` | ThePlainBagel | DIS | 2022-11-18 | The Plain Bagel | BL_L4hHBTLc | 2022-11-15 | 2022-11-21 | 1668470400 | 1669075199 | x-creator-authored | 35 | Older-year historical coverage (post Kaito UNIX proof). |
| 8 | `$SHOP` | — | SHOP | 2023-01-08 | Ticker Symbol: YOU | kG6MzOFT9RM | 2023-01-05 | 2023-01-11 | 1672876800 | 1673481599 | ticker-only-control | 35 | Labeled ticker-only control for non-mapped creator. |
| 9 | `$AAPL` | — | AAPL | 2023-08-18 | New Money | gaG787XWIXc | 2023-08-15 | 2023-08-21 | 1692057600 | 1692662399 | ticker-only-control | 35 | Liquid mega-cap; good overlap stress control. |
| 10 | `$TSLA` | — | TSLA | 2021-08-02 | Chicken Genius Singapore | 5T_EgAUWhhg | 2021-07-30 | 2021-08-05 | 1627603200 | 1628207999 | ticker-only-control | 35 | Historical window; ticker-only control pending manual X handle. |

## Query hierarchy (operational)

1. **`from:handle $TICKER`** via `source_type="search"` when a handle mapping exists (Kaito `searchTerms` + UNIX bounds).
2. **`@handle $TICKER` / display-name variants** — only after manual verification of exact spelling; not automated in checkpoint v1.
3. **Ticker-only `$TICKER`** — **labeled control** only, never mixed with creator-authored rows in aggregate tables without a `query_type` column.

## Confounders / overlap value

- Rows pairing **The Plain Bagel** with event-study tickers support **YouTube/X overlap diagnostics** on a narrow window around validated transcript events.
- Ticker-only rows provide **attention controls** when creator mapping is unknown.
