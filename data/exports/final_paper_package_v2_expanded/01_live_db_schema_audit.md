# Live DB Schema Audit

- DB path: `data/finfluencer_alpha.db`
- Scope: table names, column names, row counts, and indexes only.
- Raw transcript text, raw JSON, environment files, and secrets were not printed.

## `apify_collection_runs`

- Rows: `360`
- Columns: `run_id` (TEXT), `platform` (TEXT), `actor_id` (TEXT), `key_label` (TEXT), `started_at` (TEXT), `finished_at` (TEXT), `status` (TEXT), `input_hash` (TEXT), `source_type` (TEXT), `source_query` (TEXT), `requested_items` (INTEGER), `imported_items` (INTEGER), `duplicates` (INTEGER), `cost_usd` (REAL), `error_message` (TEXT)
- Indexes: `idx_apify_collection_runs_platform`, `sqlite_autoindex_apify_collection_runs_1`

## `creator_scores`

- Rows: `5`
- Columns: `creator_handle` (TEXT), `platform` (TEXT), `total_items` (INTEGER), `ticker_mentions` (INTEGER), `actionable_mentions` (INTEGER), `ticker_density` (REAL), `avg_engagement` (REAL), `relevance_score` (REAL), `notes` (TEXT), `created_at` (TEXT)

## `creator_selection`

- Rows: `0`
- Columns: `platform` (TEXT), `handle_or_channel` (TEXT), `initial_category` (TEXT), `count_stockpick_filtered` (INTEGER), `estimated_x_reads` (INTEGER), `estimated_x_cost` (REAL), `ticker_density` (REAL), `actionable_density` (REAL), `creator_selection_score` (REAL), `recommended_action` (TEXT), `reason` (TEXT), `selected_for_collection` (INTEGER), `created_at` (TEXT)
- Indexes: `sqlite_autoindex_creator_selection_1`

## `creator_taxonomy`

- Rows: `0`
- Columns: `platform` (TEXT), `handle_or_channel` (TEXT), `initial_category` (TEXT), `notes` (TEXT), `source` (TEXT), `created_at` (TEXT)
- Indexes: `sqlite_autoindex_creator_taxonomy_1`

## `creators`

- Rows: `39`
- Columns: `creator_id` (INTEGER), `platform` (TEXT), `handle` (TEXT), `display_name` (TEXT), `account_url` (TEXT), `category` (TEXT), `source_method` (TEXT), `include_reason` (TEXT), `follower_count` (INTEGER), `video_count` (INTEGER), `post_count` (INTEGER), `relevance_score` (REAL), `created_at` (TEXT)
- Indexes: `idx_creators_platform_handle`

## `raw_x_posts`

- Rows: `0`
- Columns: `post_id` (TEXT), `creator_handle` (TEXT), `author_id` (TEXT), `created_at` (TEXT), `text` (TEXT), `lang` (TEXT), `like_count` (INTEGER), `repost_count` (INTEGER), `reply_count` (INTEGER), `quote_count` (INTEGER), `impression_count` (INTEGER), `url` (TEXT), `raw_json` (TEXT), `collected_at` (TEXT)
- Indexes: `idx_raw_x_posts_creator`, `sqlite_autoindex_raw_x_posts_1`

## `raw_youtube_videos`

- Rows: `11922`
- Columns: `video_id` (TEXT), `channel_id` (TEXT), `channel_title` (TEXT), `published_at` (TEXT), `title` (TEXT), `description` (TEXT), `view_count` (INTEGER), `like_count` (INTEGER), `comment_count` (INTEGER), `current_view_count` (INTEGER), `current_like_count` (INTEGER), `current_comment_count` (INTEGER), `url` (TEXT), `raw_json` (TEXT), `collected_at` (TEXT), `creator_category` (TEXT), `seed_source` (TEXT), `seed_creator_name` (TEXT), `seed_priority` (INTEGER), `excluded_flag` (INTEGER), `exclusion_reason` (TEXT), `market_regime` (TEXT)
- Indexes: `idx_raw_youtube_videos_channel`, `sqlite_autoindex_raw_youtube_videos_1`

## `recommendation_candidates`

- Rows: `2307`
- Columns: `candidate_id` (INTEGER), `platform` (TEXT), `source_id` (TEXT), `creator_handle` (TEXT), `ticker` (TEXT), `event_time` (TEXT), `stance` (TEXT), `actionability_score` (INTEGER), `recommendation_type` (TEXT), `horizon` (TEXT), `disclosure_flag` (INTEGER), `risk_discussion_flag` (INTEGER), `valuation_discussion_flag` (INTEGER), `classifier_confidence` (REAL), `manual_validated` (INTEGER)
- Indexes: `idx_recommendation_candidates_source`, `idx_recommendation_candidates_unique`

## `sqlite_sequence`

- Rows: `1`
- Columns: `name` (untyped), `seq` (untyped)

## `ticker_mentions`

- Rows: `14468`
- Columns: `mention_id` (INTEGER), `platform` (TEXT), `source_id` (TEXT), `ticker` (TEXT), `mention_text` (TEXT), `cashtag_flag` (INTEGER), `extraction_method` (TEXT), `confidence` (REAL)
- Indexes: `idx_ticker_mentions_source`, `idx_ticker_mentions_unique`

## `transcript_candidate_windows`

- Rows: `12083`
- Columns: `candidate_window_id` (INTEGER), `video_id` (TEXT), `ticker` (TEXT), `company_name` (TEXT), `mention_text` (TEXT), `evidence_start_seconds` (REAL), `evidence_end_seconds` (REAL), `evidence_window` (TEXT), `focused_action_text` (TEXT), `stance` (TEXT), `detected_action` (TEXT), `actionability_score` (INTEGER), `confidence_score` (REAL), `confidence_label` (TEXT), `accepted` (INTEGER), `transcript_event_id` (INTEGER), `classifier_version` (TEXT), `exclusion_reason` (TEXT), `created_at` (TEXT), `accepted_event_flag` (INTEGER), `transcript_source` (TEXT), `provider_name` (TEXT), `transcript_collected_at` (TEXT)
- Indexes: `idx_transcript_candidate_windows_ticker`, `idx_transcript_candidate_windows_video`

## `transcript_collection_attempts`

- Rows: `9946`
- Columns: `attempt_id` (INTEGER), `run_id` (INTEGER), `video_id` (TEXT), `creator` (TEXT), `published_at` (TEXT), `ticker_signal_count` (INTEGER), `attempted_at` (TEXT), `status` (TEXT), `error_type` (TEXT), `error_message` (TEXT), `transcript_source` (TEXT), `provider_name` (TEXT), `retrieval_method` (TEXT), `is_asr_generated` (INTEGER), `language` (TEXT), `source_confidence` (REAL), `word_count` (INTEGER), `segment_count` (INTEGER)
- Indexes: `idx_collection_attempts_status`, `idx_collection_attempts_video`, `idx_collection_attempts_run`

## `transcript_collection_runs`

- Rows: `108`
- Columns: `run_id` (INTEGER), `started_at` (TEXT), `ended_at` (TEXT), `command_name` (TEXT), `input_source` (TEXT), `requested_limit` (INTEGER), `attempted_count` (INTEGER), `available_count` (INTEGER), `no_transcript_count` (INTEGER), `ip_blocked_count` (INTEGER), `request_blocked_count` (INTEGER), `rate_limited_count` (INTEGER), `other_error_count` (INTEGER), `stopped_reason` (TEXT), `min_disk_mb` (INTEGER), `free_disk_mb_start` (REAL), `free_disk_mb_end` (REAL), `sleep_seconds` (REAL), `jitter_seconds` (REAL), `max_per_creator` (INTEGER), `creator_diversify` (INTEGER), `allow_translation` (INTEGER), `notes` (TEXT)
- Indexes: `idx_collection_runs_started`

## `transcript_event_exclusions`

- Rows: `0`
- Columns: `exclusion_id` (INTEGER), `event_id` (INTEGER), `window_id` (INTEGER), `ticker` (TEXT), `reason` (TEXT), `evidence_excerpt` (TEXT), `action` (TEXT), `created_at` (TEXT)
- Indexes: `idx_event_exclusions_ticker`

## `transcript_event_extraction_status`

- Rows: `609`
- Columns: `video_id` (TEXT), `transcript_source` (TEXT), `provider_name` (TEXT), `transcript_collected_at` (TEXT), `transcript_hash` (TEXT), `classifier_version` (TEXT), `processed_at` (TEXT), `ticker_mentions_found` (INTEGER), `candidate_windows_found` (INTEGER), `events_found` (INTEGER)
- Indexes: `sqlite_autoindex_transcript_event_extraction_status_1`

## `transcript_fetch_queue`

- Rows: `6507`
- Columns: `video_id` (TEXT), `channel_title` (TEXT), `published_at` (TEXT), `title` (TEXT), `description` (TEXT), `priority_score` (REAL), `priority_reason` (TEXT), `transcript_status` (TEXT), `attempt_count` (INTEGER), `last_attempted_at` (TEXT), `next_eligible_attempt_at` (TEXT), `created_at` (TEXT)
- Indexes: `idx_transcript_fetch_queue_status`, `idx_transcript_fetch_queue_priority`, `sqlite_autoindex_transcript_fetch_queue_1`

## `transcript_recommendation_events`

- Rows: `2341`
- Columns: `transcript_event_id` (INTEGER), `video_id` (TEXT), `ticker` (TEXT), `company_name` (TEXT), `stance` (TEXT), `detected_action` (TEXT), `actionability_score` (INTEGER), `confidence_score` (REAL), `confidence_label` (TEXT), `evidence_start_seconds` (REAL), `evidence_end_seconds` (REAL), `evidence_window` (TEXT), `classifier_version` (TEXT), `exclusion_reason` (TEXT), `created_at` (TEXT), `transcript_source` (TEXT), `provider_name` (TEXT), `transcript_collected_at` (TEXT)
- Indexes: `idx_transcript_recommendation_events_ticker`, `idx_transcript_recommendation_events_video`

## `x_budget_usage`

- Rows: `0`
- Columns: `usage_id` (INTEGER), `job_name` (TEXT), `estimated_reads` (INTEGER), `estimated_cost` (REAL), `actual_reads` (INTEGER), `actual_cost` (REAL), `status` (TEXT), `details` (TEXT), `created_at` (TEXT), `updated_at` (TEXT)
- Indexes: `idx_x_budget_usage_job`

## `x_collection_progress`

- Rows: `0`
- Columns: `source_type` (TEXT), `source_value` (TEXT), `last_collected_at` (TEXT), `earliest_collected_at` (TEXT), `posts_imported` (INTEGER), `status` (TEXT)
- Indexes: `sqlite_autoindex_x_collection_progress_1`

## `x_enriched_events`

- Rows: `0`
- Columns: `enrichment_id` (INTEGER), `candidate_id` (INTEGER), `source_id` (TEXT), `creator_handle` (TEXT), `reply_reads` (INTEGER), `quote_reads` (INTEGER), `status` (TEXT), `created_at` (TEXT)

## `x_post_ticker_mentions`

- Rows: `6092`
- Columns: `post_id` (TEXT), `ticker` (TEXT), `cashtag` (TEXT), `mention_type` (TEXT), `confidence` (REAL)
- Indexes: `idx_x_post_ticker_mentions_ticker`, `sqlite_autoindex_x_post_ticker_mentions_1`

## `x_posts`

- Rows: `7053`
- Columns: `post_id` (TEXT), `author_handle` (TEXT), `author_name` (TEXT), `author_id` (TEXT), `text` (TEXT), `created_at` (TEXT), `url` (TEXT), `like_count` (INTEGER), `repost_count` (INTEGER), `reply_count` (INTEGER), `quote_count` (INTEGER), `view_count` (INTEGER), `language` (TEXT), `scraped_at` (TEXT), `apify_actor` (TEXT), `apify_key_label` (TEXT), `source_query` (TEXT), `source_type` (TEXT), `raw_json_path` (TEXT), `normalized_text_hash` (TEXT)
- Indexes: `idx_x_posts_source`, `idx_x_posts_author_date`, `idx_x_posts_author_created_hash`, `idx_x_posts_url`, `sqlite_autoindex_x_posts_1`

## `x_query_counts`

- Rows: `0`
- Columns: `count_id` (INTEGER), `query` (TEXT), `handle` (TEXT), `start_date` (TEXT), `end_date` (TEXT), `granularity` (TEXT), `total_tweet_count` (INTEGER), `period_counts_json` (TEXT), `raw_json` (TEXT), `collected_at` (TEXT)
- Indexes: `idx_x_query_counts_handle`

## `x_recommendation_events`

- Rows: `1517`
- Columns: `event_id` (INTEGER), `post_id` (TEXT), `author_handle` (TEXT), `ticker` (TEXT), `event_datetime` (TEXT), `event_date` (TEXT), `recommendation_type` (TEXT), `direction` (TEXT), `confidence` (REAL), `source_method` (TEXT), `evidence_text` (TEXT)
- Indexes: `idx_x_recommendation_events_ticker_date`, `idx_x_recommendation_events_unique`

## `youtube_metadata_expansion_runs`

- Rows: `0`
- Columns: `run_id` (TEXT), `source_name` (TEXT), `source_type` (TEXT), `started_at` (TEXT), `finished_at` (TEXT), `videos_found` (INTEGER), `videos_imported` (INTEGER), `duplicates` (INTEGER), `status` (TEXT), `error_message` (TEXT)
- Indexes: `sqlite_autoindex_youtube_metadata_expansion_runs_1`

## `youtube_transcript_segments`

- Rows: `2832877`
- Columns: `video_id` (TEXT), `segment_index` (INTEGER), `start_seconds` (REAL), `duration_seconds` (REAL), `text` (TEXT)
- Indexes: `idx_youtube_transcript_segments_video`, `sqlite_autoindex_youtube_transcript_segments_1`

## `youtube_transcripts`

- Rows: `9992`
- Columns: `video_id` (TEXT), `provider_name` (TEXT), `provider_version` (TEXT), `language` (TEXT), `language_code` (TEXT), `is_generated` (INTEGER), `is_translatable` (INTEGER), `status` (TEXT), `error_type` (TEXT), `error_message` (TEXT), `full_text` (TEXT), `full_text_sha256` (TEXT), `segment_count` (INTEGER), `raw_json` (TEXT), `retrieved_at` (TEXT), `transcript_source` (TEXT), `retrieval_method` (TEXT), `retrieval_status` (TEXT), `provider_notes` (TEXT), `is_asr_generated` (INTEGER), `source_confidence` (REAL), `collected_at` (TEXT), `character_count` (INTEGER), `word_count` (INTEGER), `collector_notes` (TEXT), `provider_actor_id` (TEXT), `provider_run_id` (TEXT)
- Indexes: `sqlite_autoindex_youtube_transcripts_1`
