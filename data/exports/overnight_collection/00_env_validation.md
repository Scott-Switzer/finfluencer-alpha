# Environment Validation

Generated: 2026-05-14T02:29:10Z

## Secret Handling
- Token/API key values printed: no
- Secret-like variable names present: 35

## Apify Keys
- Available Apify token count: 5
- Indexed token slots present: 1, 2, 3, 4, 5
- Token labels: apify_main, apify_key_2, apify_key_3, apify_key_4, apify_key_5
- Fallback APIFY_TOKEN present: yes

## Budget Caps
- APIFY_GLOBAL_MAX_TOTAL_USD: 25.00
- APIFY_GLOBAL_MIN_REMAINING_USD: 0.05
- X_TOTAL_COST_CAP_USD: 18.00
- YOUTUBE_TRANSCRIPT_TOTAL_COST_CAP_USD: 4.00
- X_APIFY_ACTOR_BAKEOFF_MAX_COST_USD: 1.00

## Per-Key Caps
- apify_main: max_total_usd=5.00; min_remaining_usd=0.01
- apify_key_2: max_total_usd=5.00; min_remaining_usd=0.01
- apify_key_3: max_total_usd=5.00; min_remaining_usd=0.01
- apify_key_4: max_total_usd=5.00; min_remaining_usd=0.01
- apify_key_5: max_total_usd=5.00; min_remaining_usd=0.01

## Collection Targets
- X_POST_TARGET_TOTAL: 50000
- YOUTUBE_TRANSCRIPT_TARGET_TOTAL: 11000
- YOUTUBE_TRANSCRIPT_TARGET: not set
- YOUTUBE_TRANSCRIPT_PREFERRED_TARGET: not set

## Actor Candidates
- X_APIFY_ACTOR_CANDIDATES: apidojo/tweet-scraper,kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest,scraper-engine/twitter-x-posts-scraper,scraper_one/x-profile-posts-scraper

## Configured Paths
- X_PROFILE_LIST_PATH: present=yes; exists=no; path=config/x_sources/profiles.txt
- X_SEARCH_QUERY_LIST_PATH: present=yes; exists=no; path=config/x_sources/search_queries.txt
- X_CASTAG_QUERY_LIST_PATH: present=yes; exists=no; path=config/x_sources/cashtags.txt
- DB path source: FINFLUENCER_DB_PATH; resolves: /workspace/FIN496CAPSTONE/data/finfluencer_alpha.db; exists=yes

## Required/Fallback Variable Presence
- APIFY_TOKEN or indexed tokens: yes
- APIFY_TOKEN_COUNT: yes
- APIFY_TOKEN_N_LABEL if indexed tokens exist: yes
- X_APIFY_COLLECTION_ENABLED: yes
- X_POST_TARGET_TOTAL: yes
- X_APIFY_ACTOR_CANDIDATES: yes
- X_PROFILE_LIST_PATH: yes
- X_SEARCH_QUERY_LIST_PATH: yes
- X_CASTAG_QUERY_LIST_PATH: yes
- DATABASE_URL or FINFLUENCER_DB_PATH/default DB: yes
- YOUTUBE_API_KEY: yes
