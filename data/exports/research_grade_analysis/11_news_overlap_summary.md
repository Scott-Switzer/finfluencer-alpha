# News Overlap Summary

## Status

- Live SEC EDGAR pass: **not run** in this pass (ALLOW_SEC_EDGAR off by default
  to keep the analysis fully offline-safe).
- Live GDELT pass: **not run** in this pass.
- All flag columns in `10_news_overlap_flags.csv` are populated with the value
  `unknown`. `news_source_used = protocol_only`, `news_query_status = not_run`.

## Sample

- Rows in flag CSV: `1554` (= 1,554 locked events).

## Bloomberg-Day Rerun Checklist

1. Build `data/seeds/ticker_cik_map.csv` for the 23 locked tickers from
   `https://www.sec.gov/files/company_tickers.json`.
2. Run SEC EDGAR pass: per ticker, pull
   `https://data.sec.gov/submissions/CIK<10-digit>.json`, filter to
   `filings.recent.form in {8-K, 10-Q, 10-K, S-1, 424B, 10-K/A, 10-Q/A}`,
   keep `filingDate`, `form`, `accessionNumber`.
3. For each locked event, set `sec_8k_near_event_flag = True` iff any 8-K filing
   date is within +/-5 trading days of `effective_trading_event_date`. Tighten
   to same-day and +/-1 day flags using the same filing dates.
4. Populate `earnings_near_event_flag` from Bloomberg `EARN_ANN_DT`. SEC EDGAR
   alone is *not* sufficient because earnings are typically announced ahead of
   the 8-K filing.
5. Populate `major_news_near_event_flag` from Bloomberg `NEWS_HEAT_PUB_DNUM`
   peaks within +/-5 trading days, with manual sanity check on the top 30
   flagged events.
6. Replace `news_query_status = not_run` with `bloomberg_<YYYY-MM-DD>` and
   commit the regenerated CSV to `data/exports/research_grade_analysis/`.

## Why No Live Run Now

- The task specification explicitly disallows paid sources and treats SEC and
  GDELT as optional. Going offline keeps the run deterministic, removes
  network failure modes, and means the same CSV schema is delivered whether or
  not external calls succeeded. Bloomberg-day rerun is the canonical fill-in
  step.
