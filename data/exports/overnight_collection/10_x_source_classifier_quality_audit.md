# X Source And Classifier Quality Audit

Generated: 2026-05-14T16:17:46Z

## Overall Counts
- X posts: 6,936
- X ticker mentions: 5,605
- X recommendation events: 1,462
- Apify runs: 317
- Collection spend: $17.9563
- Collection duplicate rate from ledger: 0.46%
- Cost per imported item: $0.0026
- Near-duplicate normalized text hashes: 13
- Posts involved in repeated normalized hashes: 30
- Parsed X post date coverage: 2026-05-14 to 2026-05-14 across 1 calendar day(s)

## Critical Quality Flags
- Date coverage is not historical: all parsed X posts are from 2026-05-14 to 2026-05-14, so the collected X data do not yet cover 2020-01-01 through 2026-05-13.
- X recommendation `event_date` values are not ISO-normalized in the DB; they are derived from the raw Twitter date prefix and need a derived ISO date before event studies.
- Ticker extraction is over-broad: only 629 of 5,605 mentions (11.2%) and 46 of 1,462 recommendation events (3.1%) match the configured cashtag seed universe.
- Common-word or non-equity-looking tokens account for 1,129 ticker mentions and 452 recommendation events before filtering.
- No posts came from verified creator profiles; source coverage is likely profiles, market controls, and broad cashtag/search queries.

## X Posts By Source Type
| Source Type | Posts |
| --- | ---: |
| verified creator profile | 0 |
| likely creator profile | 1,635 |
| inferred/unverified handle | 0 |
| market-control account | 1,394 |
| cashtag/search query | 3,907 |
| unknown | 0 |

## X Recommendation Events By Source Type
| Source Type | Recommendation Events |
| --- | ---: |
| verified creator profile | 0 |
| likely creator profile | 362 |
| inferred/unverified handle | 0 |
| market-control account | 301 |
| cashtag/search query | 799 |
| unknown | 0 |

## Top 25 Source Accounts By Post Count
| Source | Posts |
| --- | ---: |
| realMeetKevin | 132 |
| GrahamStephan | 131 |
| ("$TSLA" OR TSLA) ("buying" OR "buy" OR "bullish" OR "adding" OR "price target" OR "undervalued") | 124 |
| Stocktwits | 122 |
| StockMoe | 121 |
| BreakoutStocks | 120 |
| RampCapitalLLC | 118 |
| $AAPL | 117 |
| DeItaone | 117 |
| CNBC | 117 |
| WallStreetSilv | 116 |
| bespokeinvest | 116 |
| TheRoaringKitty | 115 |
| ThePlainBagel | 114 |
| Benzinga | 114 |
| WSJMarkets | 114 |
| zerohedge | 113 |
| nytimesbusiness | 111 |
| $TSLA | 110 |
| unusual_whales | 110 |
| $ROKU | 108 |
| $LCID | 105 |
| ("$NVDA" OR NVDA) ("buying" OR "buy" OR "bullish" OR "AI" OR "price target" OR "overvalued") | 104 |
| Mayhem4Markets | 103 |
| Investingcom | 103 |

## Top 25 Source Accounts By Recommendation-Event Count
| Source | Recommendation Events |
| --- | ---: |
| zerohedge | 56 |
| $TSLA | 49 |
| $NIO | 42 |
| CNBC | 41 |
| $MSFT | 39 |
| WSJDealJournal | 38 |
| $SMCI | 38 |
| ("$AAPL" OR AAPL) ("buy" OR "sell" OR "hold" OR "earnings" OR "price target") | 38 |
| GrahamStephan | 37 |
| unusual_whales | 36 |
| KobeissiLetter | 35 |
| DeItaone | 34 |
| ("$GME" OR GME) ("buying" OR "calls" OR "squeeze" OR "Roaring Kitty" OR "DFV") | 31 |
| $PYPL | 30 |
| $GOOGL | 29 |
| realMeetKevin | 29 |
| YahooFinance | 28 |
| Investingcom | 27 |
| $CRWD | 26 |
| $RIOT | 26 |
| ThePlainBagel | 24 |
| bespokeinvest | 24 |
| $SQ | 24 |
| nytimesbusiness | 23 |
| $DIS | 23 |

## Top 50 Tickers By X Mention Count
| Ticker | Mentions |
| --- | ---: |
| SQ | 115 |
| AI | 112 |
| GOOGL | 92 |
| AAPL | 91 |
| US | 70 |
| THE | 64 |
| BTC | 62 |
| NFLX | 62 |
| META | 48 |
| TSLA | 46 |
| AMZN | 40 |
| DM | 38 |
| TO | 35 |
| YOU | 35 |
| AND | 33 |
| IN | 33 |
| IS | 32 |
| OF | 32 |
| AM | 31 |
| NVDA | 30 |
| SOL | 30 |
| ALL | 29 |
| IT | 29 |
| NOT | 27 |
| CA | 26 |
| GOLD | 25 |
| NOW | 25 |
| WTS | 25 |
| XRP | 25 |
| PM | 22 |
| BUY | 20 |
| ETH | 20 |
| MC | 20 |
| LONG | 19 |
| NO | 18 |
| ON | 18 |
| POTUS | 18 |
| THAT | 18 |
| CIA | 16 |
| FOR | 16 |
| MSFT | 16 |
| PYPL | 16 |
| SO | 16 |
| THIS | 16 |
| UP | 16 |
| GM | 15 |
| ME | 15 |
| WITH | 15 |
| BTS | 14 |
| TRUMP | 14 |

## Top 50 Tickers By X Recommendation-Event Count
| Ticker | Recommendation Events |
| --- | ---: |
| AI | 30 |
| US | 23 |
| BUY | 20 |
| LONG | 19 |
| THE | 19 |
| IN | 15 |
| MC | 15 |
| AND | 14 |
| WTS | 14 |
| YOU | 14 |
| TO | 13 |
| DM | 11 |
| IT | 11 |
| NOT | 11 |
| BTC | 10 |
| CA | 10 |
| HOLD | 10 |
| WITH | 10 |
| ALL | 9 |
| OF | 9 |
| IS | 8 |
| SELL | 8 |
| THAT | 8 |
| AAPL | 7 |
| SO | 7 |
| FOR | 6 |
| NO | 6 |
| NVDA | 6 |
| NYC | 6 |
| PM | 6 |
| TOUR | 6 |
| TRADE | 6 |
| TRUMP | 6 |
| VOL | 6 |
| AMZN | 5 |
| BE | 5 |
| MCP | 5 |
| NOW | 5 |
| POTUS | 5 |
| PT | 5 |
| SL | 5 |
| THIS | 5 |
| UK | 5 |
| XI | 5 |
| ARE | 4 |
| CF | 4 |
| CHINA | 4 |
| CMP | 4 |
| GOOGL | 4 |
| II | 4 |

## Ticker Precision Diagnostic
- Configured cashtag seed tickers: 33
- Mentions in configured seed ticker universe: 629 of 5,605 (11.2%)
- Recommendation events in configured seed ticker universe: 46 of 1,462 (3.1%)
- Final event studies should use a validated investable ticker universe and should prefer cashtag mentions or explicit company-name mappings over plain uppercase-token extraction.

## Classifier Label Distribution
| Label | Events |
| --- | ---: |
| explicit_buy | 876 |
| explicit_sell_or_avoid | 414 |
| hold | 157 |
| price_target | 15 |

## Direction Distribution
| Direction | Events |
| --- | ---: |
| bullish | 876 |
| bearish | 414 |
| neutral | 172 |

## Confidence Distribution
| Confidence Bin | Events |
| --- | ---: |
| high >=0.80 | 1,290 |
| medium 0.60-0.79 | 172 |

## Examples: High-Confidence Buy/Long Recommendations
Raw post text is intentionally omitted from this committed audit to avoid committing raw X data.
| Event ID | Parsed Date | Source | Source Type | Ticker | Label | Direction | Confidence | Audit Note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1502 | 2026-05-14 | unusual_whales | likely creator profile | NVDA | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe |
| 1546 | 2026-05-14 | DeItaone | likely creator profile | AAPL | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe |
| 1649 | 2026-05-14 | $PLTR | cashtag/search query | NVDA | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe; broad query source |
| 1657 | 2026-05-14 | $SQ | cashtag/search query | TSLA | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe; broad query source |
| 1679 | 2026-05-14 | $SMCI | cashtag/search query | AAPL | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe; broad query source |
| 1710 | 2026-05-14 | $BABA | cashtag/search query | MSFT | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe; broad query source |
| 1779 | 2026-05-14 | $MSTR | cashtag/search query | AMC | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe; broad query source |
| 1804 | 2026-05-14 | ("$GME" OR GME) ("buying" OR "calls" OR "squeeze" OR "Roaring Kitty" OR "DFV") | cashtag/search query | AMC | explicit_buy | bullish | 0.85 | ticker in configured cashtag universe; broad query source |

## Examples: High-Confidence Sell/Short Recommendations
Raw post text is intentionally omitted from this committed audit to avoid committing raw X data.
| Event ID | Parsed Date | Source | Source Type | Ticker | Label | Direction | Confidence | Audit Note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1529 | 2026-05-14 | RampCapitalLLC | likely creator profile | AAPL | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe |
| 1674 | 2026-05-14 | $HOOD | cashtag/search query | NFLX | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe; broad query source |
| 1742 | 2026-05-14 | $UBER | cashtag/search query | SQ | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe; broad query source |
| 2338 | 2026-05-14 | $TSLA | cashtag/search query | SQ | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe; broad query source |
| 2396 | 2026-05-14 | $SQ | cashtag/search query | COIN | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe; broad query source |
| 2458 | 2026-05-14 | $RIOT | cashtag/search query | AMD | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe; broad query source |
| 2898 | 2026-05-14 | Mayhem4Markets | likely creator profile | SQ | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe |
| 2902 | 2026-05-14 | DeItaone | likely creator profile | SQ | explicit_sell_or_avoid | bearish | 0.85 | ticker in configured cashtag universe |

## Examples Likely To Be False Positives Or Non-Actionable
Raw post text is intentionally omitted; rows show classifier/ticker patterns requiring exclusion or manual review.
| Event ID | Parsed Date | Source | Source Type | Ticker | Label | Direction | Confidence | Audit Note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1465 | 2026-05-14 | GrahamStephan | likely creator profile | SFV | explicit_buy | bullish | 0.85 | ticker requires investable-universe validation |
| 1470 | 2026-05-14 | ("$TSLA" OR TSLA) ("buying" OR "buy" OR "bullish" OR "adding" OR "price target"  | cashtag/search query | AI | explicit_sell_or_avoid | bearish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1505 | 2026-05-14 | unusual_whales | likely creator profile | AND | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1506 | 2026-05-14 | unusual_whales | likely creator profile | BUY | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1514 | 2026-05-14 | unusual_whales | likely creator profile | NO | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1518 | 2026-05-14 | unusual_whales | likely creator profile | WITH | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1520 | 2026-05-14 | unusual_whales | likely creator profile | YOU | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1523 | 2026-05-14 | KobeissiLetter | likely creator profile | UP | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1542 | 2026-05-14 | Mayhem4Markets | likely creator profile | LONG | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |
| 1544 | 2026-05-14 | Mayhem4Markets | likely creator profile | THE | explicit_buy | bullish | 0.85 | ticker token is a common word or non-equity abbreviation; exclude unless externally validated |

## Examples Likely To Be Market-News/Control Posts Rather Than Recommendations
Raw post text is intentionally omitted; market-control rows should be treated as attention/control observations.
| Event ID | Parsed Date | Source | Ticker | Label | Direction | Confidence | Audit Note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1547 | 2026-05-14 | CNBC | AI | explicit_sell_or_avoid | bearish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |
| 1549 | 2026-05-14 | Benzinga | BAD | explicit_sell_or_avoid | bearish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |
| 1550 | 2026-05-14 | Benzinga | COL | explicit_sell_or_avoid | bearish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |
| 1558 | 2026-05-14 | bespokeinvest | EU | explicit_sell_or_avoid | bearish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |
| 1559 | 2026-05-14 | bespokeinvest | ID | explicit_sell_or_avoid | bearish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |
| 1561 | 2026-05-14 | WSJMarkets | ASIA | explicit_buy | bullish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |
| 1562 | 2026-05-14 | WSJMarkets | CAT | explicit_buy | bullish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |
| 1563 | 2026-05-14 | WSJMarkets | DM | explicit_buy | bullish | 0.85 | market/control source; use for attention baseline, not creator recommendation portfolio |

## Duplicate And Near-Duplicate Risk
- Exact duplicate imports recorded by collection ledger: 32
- Ledger duplicate rate: 0.46%
- Normalized text hashes repeated across DB: 13
- Posts in repeated normalized hashes: 30
- Assessment: duplicate risk is low, but final analyses should still dedupe by `post_id`, URL, and normalized text hash.

## Quality Judgment
- High-confidence classifier share: 88.2%
- Market-control share of recommendation events: 20.6%
- Cashtag/search share of recommendation events: 54.7%
- Strict seed-ticker recommendation-event share: 3.1%
- Whether the 1,462 X recommendation events look credible enough for final event studies: no, not as an unfiltered sample.
- Whether they are useful for research now: yes, as a diagnostic/pilot sample after strict source, ticker, and date-normalization filters.
- Main reason: duplicate risk is low, but ticker extraction and date coverage are not strong enough for final X event-study claims.
- Whether more X collection is worth spending money on now: no. Fix source/date/ticker validation and run filtered diagnostics before spending more.

## Recommended Source Filters For Final Analysis
- For creator-signal tests, include likely creator profiles and X-native finance profiles only after the handle/source is rechecked; keep verified profiles separate, currently N=0.
- Exclude inferred/unverified handles from recommendation portfolios unless separately validated.
- Use market-control accounts only for attention and news/control baselines, not creator recommendation portfolios.
- For cashtag/search data, require a validated investable ticker, explicit recommendation label, confidence >= 0.80, and an ISO-normalized event date.
- Exclude common-word ticker tokens unless they are confirmed by cashtag, company-name mapping, or an external ticker universe.
- Run robustness variants excluding broad query sources, market-control accounts, and any rows with non-ISO or out-of-window event dates.
- Cap per-author and per-ticker concentration to avoid source/query dominance.

## Conservative Caveats
- X classifier labels are rules-based pseudo-labels, not human validation.
- Market-control posts are useful controls, not creator stock-picking recommendations.
- Current X collection does not yet provide historical coverage for the intended 2020-2026 study window.
- Do not claim causality or tradable alpha from this audit.
- yfinance-derived returns remain prototype-grade until independently validated.
