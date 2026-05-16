# Bloomberg Required Fields Checklist

| File | Required fields |
| --- | --- |
| `bloomberg_price_template.csv` | `event_id, ticker, bloomberg_ticker, date, adjusted_close_or_total_return_index, px_last, volume, market_cap, beta, gics_sector, gics_industry, benchmark_spy_return, benchmark_qqq_return, sector_etf_return` |
| `bloomberg_news_template.csv` | `event_id, ticker, bloomberg_ticker, event_date, headline_timestamp, headline, source, news_category, relevance_score_if_available` |
| `bloomberg_corporate_actions_template.csv` | `ticker, bloomberg_ticker, action_date, action_type, description` |
| `bloomberg_earnings_template.csv` | `ticker, bloomberg_ticker, earnings_announcement_datetime, fiscal_period, eps_actual, eps_estimate, revenue_actual, revenue_estimate` |
| `bloomberg_analyst_actions_template.csv` | `ticker, bloomberg_ticker, action_datetime, broker, action_type, old_rating, new_rating, old_target, new_target` |

These fields support later replacement of yfinance prices, SEC-only news
flags, free metadata checks, and provisional calendar-time portfolio results.
