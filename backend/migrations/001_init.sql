CREATE TABLE games (
  appid INTEGER PRIMARY KEY,
  name_en TEXT, name_ko TEXT,
  type TEXT DEFAULT 'game',
  short_description TEXT,
  release_date TEXT, release_ts INTEGER,
  is_free INTEGER, price_final INTEGER, price_initial INTEGER, discount_percent INTEGER, currency TEXT,
  review_pct INTEGER, review_count INTEGER,
  detail_json TEXT, detail_fetched_at INTEGER,
  listed_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX idx_games_reviews ON games(review_count DESC);
CREATE INDEX idx_games_release ON games(release_ts);
CREATE INDEX idx_games_price ON games(price_final);
CREATE TABLE game_tags (appid INTEGER NOT NULL, tag_id INTEGER NOT NULL, PRIMARY KEY (appid, tag_id)) WITHOUT ROWID;
CREATE INDEX idx_game_tags_tag ON game_tags(tag_id);
CREATE VIRTUAL TABLE games_fts USING fts5(names, tokenize='trigram');
CREATE TABLE kv_cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE crawl_state (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE fetch_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, kind TEXT NOT NULL,
  target TEXT, ok INTEGER NOT NULL, message TEXT
);
CREATE INDEX idx_fetch_log_ts ON fetch_log(ts DESC);
