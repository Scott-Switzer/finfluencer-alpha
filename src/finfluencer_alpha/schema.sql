CREATE TABLE IF NOT EXISTS creators (
  creator_id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL,
  handle TEXT NOT NULL,
  display_name TEXT,
  account_url TEXT,
  category TEXT,
  source_method TEXT,
  include_reason TEXT,
  follower_count INTEGER,
  video_count INTEGER,
  post_count INTEGER,
  relevance_score REAL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_creators_platform_handle
ON creators(platform, handle);

CREATE TABLE IF NOT EXISTS raw_x_posts (
  post_id TEXT PRIMARY KEY,
  creator_handle TEXT,
  author_id TEXT,
  created_at TEXT,
  text TEXT,
  lang TEXT,
  like_count INTEGER,
  repost_count INTEGER,
  reply_count INTEGER,
  quote_count INTEGER,
  impression_count INTEGER,
  url TEXT,
  raw_json TEXT,
  collected_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_youtube_videos (
  video_id TEXT PRIMARY KEY,
  channel_id TEXT,
  channel_title TEXT,
  published_at TEXT,
  title TEXT,
  description TEXT,
  view_count INTEGER,
  like_count INTEGER,
  comment_count INTEGER,
  url TEXT,
  raw_json TEXT,
  collected_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticker_mentions (
  mention_id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL,
  source_id TEXT NOT NULL,
  ticker TEXT NOT NULL,
  mention_text TEXT,
  cashtag_flag INTEGER,
  extraction_method TEXT,
  confidence REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ticker_mentions_unique
ON ticker_mentions(platform, source_id, ticker, mention_text, extraction_method);

CREATE TABLE IF NOT EXISTS recommendation_candidates (
  candidate_id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL,
  source_id TEXT NOT NULL,
  creator_handle TEXT,
  ticker TEXT,
  event_time TEXT,
  stance TEXT,
  actionability_score INTEGER,
  recommendation_type TEXT,
  horizon TEXT,
  disclosure_flag INTEGER,
  risk_discussion_flag INTEGER,
  valuation_discussion_flag INTEGER,
  classifier_confidence REAL,
  manual_validated INTEGER DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendation_candidates_unique
ON recommendation_candidates(platform, source_id, ticker, recommendation_type);

CREATE TABLE IF NOT EXISTS creator_scores (
  creator_handle TEXT,
  platform TEXT,
  total_items INTEGER,
  ticker_mentions INTEGER,
  actionable_mentions INTEGER,
  ticker_density REAL,
  avg_engagement REAL,
  relevance_score REAL,
  notes TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS x_query_counts (
  count_id INTEGER PRIMARY KEY,
  query TEXT NOT NULL,
  handle TEXT,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  granularity TEXT NOT NULL,
  total_tweet_count INTEGER NOT NULL,
  period_counts_json TEXT,
  raw_json TEXT,
  collected_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_x_query_counts_handle
ON x_query_counts(handle, start_date, end_date);

CREATE TABLE IF NOT EXISTS x_budget_usage (
  usage_id INTEGER PRIMARY KEY,
  job_name TEXT NOT NULL,
  estimated_reads INTEGER NOT NULL,
  estimated_cost REAL NOT NULL,
  actual_reads INTEGER DEFAULT 0,
  actual_cost REAL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'reserved',
  details TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_x_budget_usage_job
ON x_budget_usage(job_name, created_at);

CREATE TABLE IF NOT EXISTS creator_taxonomy (
  platform TEXT NOT NULL,
  handle_or_channel TEXT NOT NULL,
  initial_category TEXT NOT NULL,
  notes TEXT,
  source TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (platform, handle_or_channel)
);

CREATE TABLE IF NOT EXISTS creator_selection (
  platform TEXT NOT NULL,
  handle_or_channel TEXT NOT NULL,
  initial_category TEXT,
  count_stockpick_filtered INTEGER DEFAULT 0,
  estimated_x_reads INTEGER DEFAULT 0,
  estimated_x_cost REAL DEFAULT 0,
  ticker_density REAL DEFAULT 0,
  actionable_density REAL DEFAULT 0,
  creator_selection_score REAL DEFAULT 0,
  recommended_action TEXT,
  reason TEXT,
  selected_for_collection INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (platform, handle_or_channel)
);

CREATE TABLE IF NOT EXISTS x_enriched_events (
  enrichment_id INTEGER PRIMARY KEY,
  candidate_id INTEGER,
  source_id TEXT NOT NULL,
  creator_handle TEXT,
  reply_reads INTEGER DEFAULT 0,
  quote_reads INTEGER DEFAULT 0,
  status TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_raw_x_posts_creator ON raw_x_posts(creator_handle);
CREATE INDEX IF NOT EXISTS idx_raw_youtube_videos_channel ON raw_youtube_videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_ticker_mentions_source ON ticker_mentions(platform, source_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_candidates_source ON recommendation_candidates(platform, source_id);
