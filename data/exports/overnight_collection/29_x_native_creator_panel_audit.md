# X-native creator panel audit (seed inventory)

Generated: 2026-05-14T20:30:00Z

## Purpose

Inventory candidate **X-native finance** accounts for the separate X attention / amplification sample (not required to match YouTube creators). Sources: `config/x_sources/profiles_likely.txt` and related overnight audit context.

## Classification legend

| Category | Meaning |
|---|---|
| 1 | Stock-picking / trader |
| 2 | Finance education / analysis |
| 3 | Macro / market commentary |
| 4 | News / market data |
| 5 | Missing / unverified / unsafe for checkpoint |

| X handle | Display / source name | Source file | Category | Confidence | Checkpoint allowed | Reason |
|---|---|---|---|---|---|---|
| GrahamStephan | Graham Stephan (YouTube-aligned macro/education creator) | `config/x_sources/profiles_likely.txt` | 2 | likely | yes | High-subscriber finance education; use `from:GrahamStephan $TICKER` style queries. |
| realMeetKevin | Meet Kevin | `profiles_likely.txt` | 1 | likely | yes | Active trader/commentary; good for ticker-specific attention probes. |
| EverythingMoney | Everything Money | `profiles_likely.txt` | 2 | likely | yes | Education + stock commentary blend. |
| ThePlainBagel | The Plain Bagel | `profiles_likely.txt` | 2 | confirmed | yes | Maps cleanly from multiple clean-event rows in `all_clean_events.csv`. |
| StockMoe | Stock Moe | `profiles_likely.txt` | 1 | likely | yes | Trader-style handle. |
| TheRoaringKitty | Roaring Kitty / WSB meme archetype | `profiles_likely.txt` | 1 | weak | no | Iconic but episodic; treat as optional stress only after core panel stabilizes. |
| unusual_whales | Unusual Whales | `profiles_likely.txt` | 4 | likely | yes | Data/news style account; good macro attention control. |
| StockMKTNewz | Stock Market News | `profiles_likely.txt` | 4 | weak | yes | News-like; monitor noise vs. explicit cashtags. |
| KobeissiLetter | Kobeissi Letter | `profiles_likely.txt` | 3 | likely | yes | Macro/market commentary. |
| zerohedge | ZeroHedge | `profiles_likely.txt` | 3 | likely | yes | Macro/news volatility amplifier; label as high-noise macro control. |
| RampCapitalLLC | Ramp Capital | `profiles_likely.txt` | 1 | weak | yes | Trader meme account; use narrow windows. |
| WallStreetSilv | Wall Street Silver | `profiles_likely.txt` | 3 | weak | yes | Macro precious-metals bias; control only unless manually vetted. |
| TicTocTick | TicTocTick | `profiles_likely.txt` | 4 | weak | yes | Data-ish; verify hit quality before expanding. |
| Mayhem4Markets | Mayhem for Markets | `profiles_likely.txt` | 1 | weak | yes | Trader commentary; keep `maxItems` small. |
| DeItaone | DeltaOne / macro headline bot | `profiles_likely.txt` | 4 | weak | yes | Headline-speed account; treat as news-speed control. |

## Manual seed proposals (needs human review)

| Proposed handle | Category | Reason |
|---|---|---|
| `financialjuice` | 3 | Macro livestream community; confirm handle spelling and ToS fit before adding. |
| `tier10k` | 4 | Breaking finance headlines; high velocity, needs noise controls. |

## Notes

- Handles are **case-sensitive** for Apify search construction; keep canonical casing from `profiles_likely.txt`.
- Any account not passing explicit-cashtag / timestamp QA in checkpoint output should be downgraded to category 5 in the next audit revision.
