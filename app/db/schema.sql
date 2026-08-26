-- feedbot schema. Idempotent: every statement is IF NOT EXISTS, so init_db()
-- runs on every start and only ever adds what is missing.

-- Flat key/value for everything the panel and the bot remember about the
-- installation itself: owner, active feed, keys the panel saved.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- A feed is one niche being tested: its own sources, its own channel, its own
-- show. Several of them belong to the same person — the panel switches between
-- them in the header.
CREATE TABLE IF NOT EXISTS feeds (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    note        TEXT,                         -- what this niche is, in plain words
    channel_id  INTEGER,                      -- bound by making the bot an admin
    enabled     INTEGER NOT NULL DEFAULT 1,
    -- The window a sweep looks at. hold_days is the important one: a post
    -- younger than that has not been voted on yet, so ranking it by score is
    -- ranking noise. Measured on Arctic Shift — a three-day window tops out
    -- at four points, a thirty-day one at four hundred.
    window_days INTEGER NOT NULL DEFAULT 45,
    hold_days   INTEGER NOT NULL DEFAULT 7,
    reel_seconds INTEGER NOT NULL DEFAULT 90,  -- how long a reel of this feed runs
    voice        TEXT NOT NULL DEFAULT 'ru-RU-DmitryNeural',
    voice_tempo  REAL NOT NULL DEFAULT 1.2,   -- applied on playback, not at synthesis
    pack         TEXT NOT NULL DEFAULT 'talk', -- which visual pack this feed uses
    theme_json   TEXT NOT NULL DEFAULT '{}',   -- only what differs from the defaults
    created_at  INTEGER NOT NULL,
    UNIQUE(name)
);

-- Sources are global, not per feed: one subreddit is fetched once even when
-- three feeds watch it. What differs per feed are the keywords, and those live
-- in feed_sources below.
CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY,
    adapter      TEXT NOT NULL,               -- reddit | hn
    name         TEXT NOT NULL,               -- subreddit name, or the adapter's own handle
    config_json  TEXT NOT NULL DEFAULT '{}',
    stored_total INTEGER NOT NULL DEFAULT 0,  -- raw items this source ever brought in
    last_run_at  INTEGER,
    last_error   TEXT,
    created_at   INTEGER NOT NULL,
    UNIQUE(adapter, name)
);

-- The subscription: this feed watches this source with these words.
CREATE TABLE IF NOT EXISTS feed_sources (
    id           INTEGER PRIMARY KEY,
    feed_id      INTEGER NOT NULL REFERENCES feeds(id)   ON DELETE CASCADE,
    source_id    INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    queries_json TEXT NOT NULL DEFAULT '[]',  -- the keywords this feed searches for
    limit_posts  INTEGER NOT NULL DEFAULT 60, -- how much of the subreddit to take per sweep
    enabled      INTEGER NOT NULL DEFAULT 1,
    last_run_at  INTEGER,
    stored_total INTEGER NOT NULL DEFAULT 0,
    kept_total   INTEGER NOT NULL DEFAULT 0,  -- how many reached the feed
    created_at   INTEGER NOT NULL,
    UNIQUE(feed_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_feed_sources_feed ON feed_sources(feed_id);

-- The shared pool of everything ever fetched. Two feeds asking the same
-- subreddit for different words collapse into the same rows here.
CREATE TABLE IF NOT EXISTS raw_items (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    ext_id      TEXT NOT NULL,
    url         TEXT,
    title       TEXT,
    body        TEXT,
    author      TEXT,
    score       INTEGER DEFAULT 0,
    comments    INTEGER DEFAULT 0,
    created_utc INTEGER,
    fetched_at  INTEGER NOT NULL,
    matched     TEXT,                         -- which keyword found it
    image_url   TEXT,                         -- the post's own picture, if it had one
    raw_json    TEXT,
    UNIQUE(source_id, ext_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_items(source_id, created_utc DESC);

-- Background work. The bot stays responsive because nothing slow happens in a
-- handler: handlers enqueue, workers run.
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'queued', -- queued | running | done | failed
    attempts     INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    run_after    INTEGER,
    chat_id      INTEGER,
    message_id   INTEGER,
    created_at   INTEGER NOT NULL,
    started_at   INTEGER,
    finished_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, run_after);

-- What a sweep put in front of this feed. raw_items is shared; this is the
-- feed's own opinion of it — the three numbers behind the ranking and what
-- happened to the post afterwards.
CREATE TABLE IF NOT EXISTS feed_items (
    id          INTEGER PRIMARY KEY,
    feed_id     INTEGER NOT NULL REFERENCES feeds(id)     ON DELETE CASCADE,
    raw_item_id INTEGER NOT NULL REFERENCES raw_items(id) ON DELETE CASCADE,
    hot         REAL,                         -- score, as a percentile of this sweep
    talk        REAL,                         -- comments, likewise
    interesting INTEGER,                      -- 1-10, the model's call
    why         TEXT,                         -- one line from the model
    rank        REAL,                         -- the three above, weighed together
    state       TEXT NOT NULL DEFAULT 'new',  -- new | picked | hidden | used
    rated_at    INTEGER,
    created_at  INTEGER NOT NULL,
    UNIQUE(feed_id, raw_item_id)
);
CREATE INDEX IF NOT EXISTS idx_feed_items_rank ON feed_items(feed_id, state, rank DESC);

-- What was made out of a post. The mode says which treatment produced it, so
-- adding a second kind of write-up is a row here, not a new table.
CREATE TABLE IF NOT EXISTS treatments (
    id           INTEGER PRIMARY KEY,
    feed_item_id INTEGER NOT NULL REFERENCES feed_items(id) ON DELETE CASCADE,
    mode         TEXT NOT NULL,
    title        TEXT,
    hook         TEXT,
    text         TEXT,
    model        TEXT,
    created_at   INTEGER NOT NULL,
    UNIQUE(feed_item_id, mode)
);
CREATE INDEX IF NOT EXISTS idx_treatments_item ON treatments(feed_item_id);

-- The reel, as text. Beats are the unit everything downstream works in: the
-- voice reads them, the frames illustrate them, the edit cuts on them.
CREATE TABLE IF NOT EXISTS scripts (
    id           INTEGER PRIMARY KEY,
    feed_item_id INTEGER NOT NULL REFERENCES feed_items(id) ON DELETE CASCADE,
    source_mode  TEXT,                     -- which treatment it was written from
    hook         TEXT,
    beats_json   TEXT NOT NULL DEFAULT '[]',
    vo_text      TEXT,                     -- every beat's voice-over, joined
    seconds_est  REAL,
    model        TEXT,
    created_at   INTEGER NOT NULL,
    UNIQUE(feed_item_id)
);

-- The voice-over, and the word timings that everything visual hangs off.
CREATE TABLE IF NOT EXISTS voiceovers (
    id           INTEGER PRIMARY KEY,
    feed_item_id INTEGER NOT NULL REFERENCES feed_items(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,
    seconds      REAL,                     -- raw, before tempo is applied
    words_json   TEXT NOT NULL DEFAULT '[]',
    voice        TEXT,
    created_at   INTEGER NOT NULL,
    UNIQUE(feed_item_id)
);

-- The finished reel.
CREATE TABLE IF NOT EXISTS reels (
    id           INTEGER PRIMARY KEY,
    feed_item_id INTEGER NOT NULL REFERENCES feed_items(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,
    seconds      REAL,
    size_bytes   INTEGER,
    pack         TEXT,
    created_at   INTEGER NOT NULL,
    UNIQUE(feed_item_id)
);
