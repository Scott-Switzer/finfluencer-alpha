# Extreme-Event News Audit Summary

The extreme-event news audit examines the largest positive and negative return reactions, rather than attempting to certify the full sample as news-clean. The audit is diagnostic: it shows whether the largest return moves coincide with official filings, public-news indicators, Bloomberg news-flow proxies, market-implied attention, or institutional following. Events with incomplete provider coverage remain unknown, not clean.

## Counts

| metric | count | percent | notes |
| --- | --- | --- | --- |
| audited_unique_events | 75 | 100.0% | Unique event IDs selected from top/bottom 25 1D and 5D abnormal returns. |
| bucket_positive_1d | 25 | 33.3% | Bucket memberships are not mutually exclusive after event-id deduplication. |
| bucket_negative_1d | 25 | 33.3% | Bucket memberships are not mutually exclusive after event-id deduplication. |
| bucket_positive_5d | 25 | 33.3% | Bucket memberships are not mutually exclusive after event-id deduplication. |
| bucket_negative_5d | 25 | 33.3% | Bucket memberships are not mutually exclusive after event-id deduplication. |
| official_confounded | 56 | 74.7% | Primary conservative classification; priority order avoids double-counting. |
| media_confounded | 15 | 20.0% | Primary conservative classification; priority order avoids double-counting. |
| bloomberg_news_flow_high | 2 | 2.7% | Primary conservative classification; priority order avoids double-counting. |
| market_attention_high | 2 | 2.7% | Primary conservative classification; priority order avoids double-counting. |
| institutionally_followed | 0 | 0.0% | Primary conservative classification; priority order avoids double-counting. |
| unresolved_unknown | 0 | 0.0% | Primary conservative classification; priority order avoids double-counting. |
| candidate_clean_extreme | 0 | 0.0% | Primary conservative classification; priority order avoids double-counting. |
| selection_rows_before_dedup | 100 |  | 25 rows requested for each of four return buckets. |
| provider_checks_used |  |  | Existing cached/derived Alpha Vantage, GDELT, FNSPID, fallback provider, news_confound_master, and Bloomberg proxy layers; no broad news rebuild. |

## Provider Scope

Provider checks use existing cached/derived layers only: Alpha Vantage and GDELT diagnostics, FNSPID/media flags, provider compact-cache summaries, the conservative news_confound_master panel, Bloomberg News Heat/Sentiment proxies, market-implied attention, and Bloomberg analyst coverage. No raw article bodies are written.

## Top Illustrative Examples

| event_id | ticker | event_date | selection_buckets | ar_1d_pct | ar_5d_pct | classification_label | evidence_note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2043 | AMC | 2023-08-22 | negative_1d; negative_5d | -24.25% | -59.73% | official_confounded | 1D AR -24.25%; 5D AR -59.73%; official filings/earnings flags: 8k_window;offering_registration_window;ownership_insider_window;material_filing_flag; filings_pm5=8; media hits/providers: sec_filing;media:alpha_vantage_news,fnspid_news;market_implied_active; external_hits=1; fnspid_pm7=21; Bloomberg news proxy elevated: heat=0.8292, sentiment=-0.2701; pre-event attention active: ret21z=4.516558105900855, volz=1.776135367064431; provider coverage incomplete/limited: official_confounded; unknown=8; http_429 |
| 2033 | AMC | 2023-08-11 | negative_1d; negative_5d | -36.10% | -20.19% | official_confounded | 1D AR -36.10%; 5D AR -20.19%; official filings/earnings flags: 8k_window;10q_10k_window;material_filing_flag; filings_pm5=4; media hits/providers: sec_filing;earnings;media:alpha_vantage_news,fnspid_news;market_implied_active; external_hits=1; fnspid_pm7=42; pre-event attention active: ret21z=1.04116855431845, volz=-1.4591237494480458; provider coverage incomplete/limited: official_confounded; unknown=8; http_429 |
| 887 | TSLA | 2024-04-22 | positive_5d | 0.66% | 34.54% | official_confounded | 1D AR 0.66%; 5D AR 34.54%; official filings/earnings flags: 8k_window;10q_10k_window;material_filing_flag; filings_pm5=8; institutional following/high salience: analysts=60.0, top5=True; provider coverage incomplete/limited: official_confounded; unknown=9; http_429 |
| 28 | NVDA | 2023-05-24 | positive_1d; positive_5d | 23.50% | 27.62% | official_confounded | 1D AR 23.50%; 5D AR 27.62%; official filings/earnings flags: 8k_window;10q_10k_window;material_filing_flag; filings_pm5=8; media hits/providers: sec_filing;earnings;media:gdelt_news,fnspid_news,alpaca_news; external_hits=2; fnspid_pm7=410; Bloomberg news proxy elevated: heat=3.7354, sentiment=-0.0125; institutional following/high salience: analysts=55.0, top5=True; provider coverage incomplete/limited: official_confounded; unknown=8; ok |
| 2042 | TSLA | 2024-04-23 | positive_1d; positive_5d | 12.11% | 27.41% | official_confounded | 1D AR 12.11%; 5D AR 27.41%; official filings/earnings flags: 8k_window;10q_10k_window;material_filing_flag; filings_pm5=6; media hits/providers: sec_filing;earnings;media:gdelt_news; external_hits=1; fnspid_pm7=0; Bloomberg news proxy elevated: heat=3.0222, sentiment=-0.1966; institutional following/high salience: analysts=60.0, top5=True; provider coverage incomplete/limited: official_confounded; unknown=8; ok |
| 240 | AMC | 2023-03-28 | negative_5d | -4.37% | -27.38% | official_confounded | 1D AR -4.37%; 5D AR -27.38%; official filings/earnings flags: 8k_window; filings_pm5=0; media hits/providers: sec_filing;media:alpha_vantage_news,fnspid_news;market_implied_active; external_hits=1; fnspid_pm7=33; Bloomberg news proxy elevated: heat=1.4076, sentiment=0.4161; pre-event attention active: ret21z=2.370850778694978, volz=-1.0207273221826216; provider coverage incomplete/limited: official_confounded; unknown=8; http_429 |
| 993 | TSLA | 2024-11-05 | positive_1d; positive_5d | 12.26% | 27.14% | market_attention_high | 1D AR 12.26%; 5D AR 27.14%; pre-event attention active: ret21z=-0.6686324677060509, volz=-0.5028147093520885; institutional following/high salience: analysts=60.0, top5=True; provider coverage incomplete/limited: market_implied_confounded; unknown=9; http_429 |
| 279 | NFLX | 2026-02-24 | positive_5d | 5.13% | 26.21% | official_confounded | 1D AR 5.13%; 5D AR 26.21%; official filings/earnings flags: 8k_window;material_filing_flag; filings_pm5=6; provider coverage incomplete/limited: official_confounded; unknown=9 |
| 1381 | TSLA | 2024-06-28 | positive_5d | 5.85% | 25.79% | official_confounded | 1D AR 5.85%; 5D AR 25.79%; official filings/earnings flags: 8k_window;material_filing_flag; filings_pm5=1; media hits/providers: sec_filing;media:eodhd_news,alpaca_news; external_hits=2; fnspid_pm7=0; institutional following/high salience: analysts=58.0, top5=True; provider coverage incomplete/limited: official_confounded; unknown=9 |
| 524 | AMD | 2025-09-27 | positive_5d | -0.11% | 25.05% | media_confounded | 1D AR -0.11%; 5D AR 25.05%; media hits/providers: media:alpha_vantage_news; external_hits=1; fnspid_pm7=0; institutional following/high salience: analysts=64.0, top5=True; provider coverage incomplete/limited: media_confounded; unknown=8 |
