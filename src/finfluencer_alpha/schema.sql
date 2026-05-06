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

CREATE INDEX IF NOT EXISTS idx_raw_x_posts_creator ON raw_x_posts(creator_handle);
CREATE INDEX IF NOT EXISTS idx_raw_youtube_videos_channel ON raw_youtube_videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_ticker_mentions_source ON ticker_mentions(platform, source_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_candidates_source ON recommendation_candidates(platform, source_id);
