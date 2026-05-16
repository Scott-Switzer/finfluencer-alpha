# V2 Sample Construction

| metric | count | source | filter_definition | notes |
| --- | --- | --- | --- | --- |
| live_transcript_rows | 9992 | youtube_transcripts | all rows | one current live DB transcript row per video_id |
| successful_transcript_rows | 9977 | youtube_transcripts | status/retrieval_status success-like |  |
| strict_text_gt_50 | 9972 | youtube_transcripts | length(full_text) > 50, aggregate only | full_text not exported |
| language_filtered_transcripts | 9106 | youtube_transcripts | language/language_code English-like |  |
| candidate_windows | 12083 | transcript_candidate_windows | all candidate windows |  |
| accepted_recommendation_events | 2341 | transcript_recommendation_events | all accepted/extracted rows | v2 primary candidate event panel |
| distinct_event_videos | 1153 | transcript_recommendation_events | count distinct video_id |  |
| buy_recommendations | 1823 | v2 event manifest | recommendation_type == buy |  |
| sell_recommendations | 518 | v2 event manifest | recommendation_type == sell |  |
| creators | 35 | raw_youtube_videos join | distinct channel_title in event panel |  |
| tickers | 24 | transcript_recommendation_events | distinct ticker |  |
| return_matched_1d | 2322 | local yfinance_market_data.csv | ticker and SPY benchmark available through +1 trading day |  |
| return_matched_5d | 2299 | local yfinance_market_data.csv | ticker and SPY benchmark available through +5 trading days |  |
| low_lookahead_events | 803 | published_at timing bucket | before_open or weekend_or_holiday |  |
| duplicate_collapsed_events | 1710 | creator+ticker+weekday_adjusted_date clusters | one observation per duplicate cluster |  |
| sec_clean_events | 721 | v1 SEC flags joined by event_id | known v1 SEC flag and sec_confounded_event_flag false | partial: SEC flags are available only for shared v1 event IDs |
| sec_confounded_events | 833 | v1 SEC flags joined by event_id | known v1 SEC flag and sec_confounded_event_flag true | partial: SEC flags are available only for shared v1 event IDs |
| top5_events | 1362 | v2 event manifest | ticker in NVDA, TSLA, AAPL, AMD, AMZN |  |
| non_top_events | 979 | v2 event manifest | ticker outside top-5 set |  |
| factor_matched_events | 0 | data/imports/french_factors | not computed; factor input directory absent | factor-adjusted v2 table is a documented gap |
