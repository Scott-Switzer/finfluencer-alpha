# Research Design

## Core Question

Do finance influencers on YouTube and X influence stock prices and provide excess returns to investors, or do they mostly amplify attention toward stocks that were already moving?

The project treats a ticker mention as a screening signal only. The final event must be a creator making an identifiable, time-stamped, directional, tradeable public-equity recommendation.

## Prior Thesis Baseline and Improvements

The prior thesis used manual YouTube search terms such as `best stocks to buy`, `best penny stocks`, `stock advice`, and `high return stocks`. It manually watched videos, selected explicitly promoted stocks, focused on 2021-2022, emphasized small and micro-cap stocks, stored ticker and video placement date, and used yFinance with the Russell 2000 for the event study.

This repo improves that baseline by making the collection and filtering process reproducible. The improvements are structured metadata collection, transcript or manual evidence for recommendation language, explicit confidence labels, creator taxonomy, cleaner ticker universe rules, Bloomberg market data, and a cross-platform X/YouTube comparison.

## Platform Roles

YouTube is the slower explanation and amplification layer. It is useful for historical metadata and longer-form recommendation evidence, but title and description fields are only a screening layer.

X is the faster attention, news, and recommendation layer. It can help test whether stock attention appears before YouTube publication, but paid retrieval must be constrained by counts, budget, and creator selection.

Bloomberg is the market-data truth layer. Event-study outputs should use Bloomberg prices, volume, benchmark returns, sector, beta, market cap, and liquidity fields rather than scraped or committed licensed data.

## Creator Taxonomy And Channel Verification

Creators are separated into `stock_picker`, `news_attention`, `analytical_control`, `meme_retail`, `macro_commentary`, and `unknown`.

YouTube seed channels are candidates until `youtube_seed_channels.csv` is resolved and manually reviewed. A verified channel record should track channel name, channel ID, handle, URL, category, expected role, latest upload date, videos in the 2020-2026 window, finance-video density, ticker density, recommendation density, U.S. equity focus, size focus, noise scores, active status, include decision, include reason, and manual notes.

Allowed include decisions are `include_primary`, `include_control`, `exclude_too_news_heavy`, `exclude_too_macro`, `exclude_too_crypto`, `exclude_too_low_signal`, and `needs_manual_review`.

## Transcript And Evidence Rules

Titles and descriptions are discovery fields. They can create candidates, but high-confidence YouTube recommendation events require transcript evidence or manual review.

Transcripts, captions, and manually reviewed snippets provide evidence for whether the creator actually recommended buying, selling, shorting, avoiding, holding, or watching a stock. Comments are audience reaction data and can support attention analysis, but comments are not creator recommendation source data.

High confidence requires transcript, X text, or manual evidence with explicit recommendation language. Medium confidence can use title or description only if the recommendation is clear. Low confidence is a mention or watchlist only and should not enter the main alpha test. Exclude news recaps, vague macro commentary, crypto-only items, options-only items without an underlying stock recommendation, and unclear tickers.

## Ticker Universe

The primary universe is U.S.-listed common stocks and ETFs, with ETFs separated from single-name stocks. Crypto, OTC, foreign listings, SPACs, penny stocks, and options-only trades should be excluded or flagged depending on the event-study design.

Ambiguous tickers such as `AI`, `ON`, `ARE`, `FOR`, `BE`, and `IT` require company-name confirmation. Ticker validity should be stored by event date so delisted or inactive securities can be handled correctly. Bloomberg mapping should include security type, exchange, sector, industry, market cap bucket, average dollar volume, price threshold, and missing-data flags.

Market cap buckets are `micro cap`, `small cap`, `mid cap`, `large cap`, and `mega cap`. The prior thesis focused on small and micro-cap stocks, but this project can include broader buckets for robustness if they are analyzed separately.

## Event Definition

An event is a creator making an identifiable, time-stamped, directional, tradeable public-equity recommendation.

Core fields include event ID, platform, creator ID/name/category, content ID/URL, raw published timestamp, event trading day, ticker, company name, security type, exchange, market cap bucket, sector, industry, recommendation direction, recommendation action, confidence score, confidence label, source layer, evidence text or snippet, transcript metadata, current engagement metrics, and market-data readiness fields.

Source layers are `title`, `description`, `transcript`, `manual`, `x_text`, and `comment_context`. Confidence labels are `high`, `medium`, `low`, and `exclude`.

## Event-Date Alignment

Store the raw `published_at` timestamp with timezone. Convert the timestamp to U.S. Eastern Time for market-event alignment.

If content is published after 4:00 PM ET on a trading day, set `event_trading_day` to the next trading day. If content is published on a weekend or market holiday, set `event_trading_day` to the next trading day. Preserve the raw timestamp separately from the aligned trading day.

## Duplicate Events And Attention Clusters

Duplicate event detection is within platform and creator. A duplicate has the same ticker, same creator, same platform, same trading day, and same recommendation direction. Duplicates should be retained in an audit log and excluded from the primary event study sample unless manual review says they are distinct recommendations.

Cross-platform clustering is separate. If a YouTube video and X post mention the same ticker within +/- 3 trading days, preserve both events and assign a linked attention cluster ID. Do not collapse cross-platform events because the research question depends on YouTube versus X timing.

## Market-Data Readiness

Each event needs these fields before the primary event study: `event_trading_day`, `price_available_flag`, `volume_available_flag`, `benchmark_available_flag`, `sector_available_flag`, `market_cap_available_flag`, `liquidity_screen_pass`, and `missing_market_data_reason`.

Events with missing price data are excluded from the primary event study but retained in an exclusion log. Missing benchmark, sector, market cap, or liquidity data should be reported and handled consistently before any inference.

## Event Study Plan

The event study should compare pre-event and post-event windows. Pre-event windows test whether abnormal returns, volume, or attention already existed before the recommendation. Post-event windows test whether the recommendation is associated with incremental abnormal return or abnormal volume.

Bloomberg fields should support adjusted returns, volume, dollar volume, benchmark returns, beta, sector, market cap, liquidity, and prior momentum controls. The analysis should report abnormal return and abnormal volume by platform, creator category, market cap bucket, confidence label, and cross-platform cluster status.

## YouTube Quota Estimates

The safe pilot command is:

```bash
python -m finfluencer_alpha collect-youtube-history-seeds --start-date 2024-01-01 --end-date 2026-05-06 --max-channels 3 --max-pages 1
```

With the current first 3 seed rows, the estimate is about 5 `channels.list` calls, 3 `playlistItems.list` calls, up to 3 `videos.list` calls, 0 `search.list` calls, and roughly 11 quota units. This reflects one channel ID and two handle resolutions.

If the first 3 seed channels were unresolved names, add up to 3 `search.list` calls. Since `search.list` costs 100 units each, that fallback would be about 309 quota units.

Use `--dry-run` to print the estimate without calling the YouTube API.

## Data Collection Staging

Stage 0: no API research-design review. Verify seed files, schemas, docs, and tests.

Stage 1: YouTube pilot metadata. Collect 3 to 5 verified or candidate channels over 2024-01-01 to 2026-05-06, or a smaller window if needed. Verify metadata collection, ticker extraction, and candidate generation.

Stage 2: transcript pilot. Review 25 to 50 candidate videos to estimate transcript availability and classification quality.

Stage 3: manual validation pilot. Review 50 to 100 candidate events to estimate false positives and refine rules.

Stage 4: YouTube historical collection. Collect selected verified channels over 2020-01-01 to 2026-05-06.

Stage 5: X counts only. Do not retrieve posts until credits and budget are confirmed.

Stage 6: budgeted X retrieval. Limit to $50, 10,000 reads, selected creators, and stock-pick-filtered posts only.

Stage 7: Bloomberg market-data join. Add prices, volume, benchmark returns, sector, market cap, beta, and liquidity.

Stage 8: event study. Estimate pre-event and post-event abnormal returns and abnormal volume.

## Go/No-Go Gates

Do not proceed from the YouTube pilot to full historical YouTube collection unless at least 3 primary stock-picker channels resolve successfully, at least 30 candidate videos are collected, at least 10 candidate recommendation events are generated, and manual review of a small sample shows an acceptable false-positive rate.

Do not proceed to paid X retrieval unless X counts work, `x_budget_plan.csv` is reviewed, `final_selected_creators.csv` is reviewed, expected reads are no more than 10,000, expected spend is no more than $50, and no full-timeline collection is planned.
