# Analyst Unknown Reduction Summary

# Analyst grade normalization audit

| Metric | Count |
| --- | ---: |
| Event-time alignment unknown before | 1824 |
| Event-time alignment unknown after | 52 |
| Events reclassified from analyst_unknown | 1772 |
| Event-time coverage before | 2270 |
| Event-time coverage after | 2299 |

## Reclassified distribution by provider
| analyst_event_time_source | analyst_coverage_tier | alignment_after | n |
| --- | --- | --- | --- |
| yfinance | event_time_yfinance | analyst_bullish_aligned | 955 |
| yfinance | event_time_yfinance | analyst_neutral_or_mixed | 458 |
| yfinance | event_time_yfinance | finfluencer_contrarian_to_analyst | 337 |
| yfinance | event_time_yfinance | analyst_bearish_aligned | 22 |

## Alignment distribution before
| analyst_alignment | n |
| --- | --- |
| analyst_unknown | 1824 |
| analyst_bullish_aligned | 351 |
| finfluencer_contrarian_to_analyst | 108 |
| analyst_neutral_or_mixed | 39 |

## Alignment distribution after
| analyst_alignment | n |
| --- | --- |
| analyst_bullish_aligned | 1301 |
| analyst_neutral_or_mixed | 504 |
| finfluencer_contrarian_to_analyst | 443 |
| analyst_unknown | 52 |
| analyst_bearish_aligned | 22 |

## Top raw strings causing remaining unknowns
| raw_latest_grade | grade_mapping_rule | n |
| --- | --- | --- |
|  | missing | 52 |

## Claim discipline
- Grade normalization improves descriptive analyst-relay classification.
- Dated yfinance rows are event-time usable only when the recommendation record predates the creator event.
- Current yfinance snapshots remain diagnostic and are not historical event-time evidence.
- The mapping does not establish causality, tradability, or clean public-information controls.
