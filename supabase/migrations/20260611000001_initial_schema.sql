-- =============================================================================
-- DM Action Cricket Stats Tracker — Initial Schema
-- =============================================================================

-- ── Seasons ───────────────────────────────────────────────────────────────────
CREATE TABLE seasons (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key         text UNIQUE NOT NULL,   -- 'spring2025', 'autumn2026'
    label       text NOT NULL,          -- 'Spring 2025', 'Autumn 2026'
    created_at  timestamptz DEFAULT now()
);

-- ── Games ─────────────────────────────────────────────────────────────────────
CREATE TABLE games (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id   uuid REFERENCES seasons(id) NOT NULL,
    game_key    text UNIQUE NOT NULL,   -- 'G1', 'G2', etc.
    date        date NOT NULL,
    opponent    text NOT NULL,
    result      text NOT NULL,          -- 'win' or 'loss'
    dm_score    int,
    opp_score   int,
    fixture_id  text,
    url         text,
    -- Skins breakdown (from PDF scorecard)
    dm_skins    int DEFAULT 0,
    opp_skins   int DEFAULT 0,
    points      int DEFAULT 0,
    max_points  int DEFAULT 0,
    dm_skin1    int DEFAULT 0,
    dm_skin2    int DEFAULT 0,
    dm_skin3    int DEFAULT 0,
    dm_skin4    int DEFAULT 0,
    opp_skin1   int DEFAULT 0,
    opp_skin2   int DEFAULT 0,
    opp_skin3   int DEFAULT 0,
    opp_skin4   int DEFAULT 0,
    created_at  timestamptz DEFAULT now()
);

-- ── Players ───────────────────────────────────────────────────────────────────
CREATE TABLE players (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text UNIQUE NOT NULL,   -- canonical display name e.g. 'Kiran Varghese'
    created_at  timestamptz DEFAULT now()
);

-- ── Player Aliases ────────────────────────────────────────────────────────────
-- Replaces the hardcoded NAME_MAP dict and GAME_OVERRIDES in aggregate.py.
-- raw_name: exactly as it appears in the PDF after clean_name() normalisation
-- game_id:  NULL = applies to all games; set to override for a specific game
--           (handles cases like 'Kiaran N' meaning different players in G2 vs others)
CREATE TABLE player_aliases (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_name    text NOT NULL,
    player_id   uuid REFERENCES players(id) NOT NULL,
    game_id     uuid REFERENCES games(id),  -- NULL = global
    created_at  timestamptz DEFAULT now()
);

-- Partial unique indexes handle the NULL game_id case correctly
-- (standard UNIQUE constraint treats NULL != NULL, so two global aliases for
-- the same raw_name would not conflict without this)
CREATE UNIQUE INDEX player_aliases_global_uq
    ON player_aliases(raw_name)
    WHERE game_id IS NULL;

CREATE UNIQUE INDEX player_aliases_game_uq
    ON player_aliases(raw_name, game_id)
    WHERE game_id IS NOT NULL;

-- ── Game Stats ────────────────────────────────────────────────────────────────
-- One row per player per game. player_id is NULL for unresolved names —
-- query WHERE player_id IS NULL to find names that need mapping.
CREATE TABLE game_stats (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id      uuid REFERENCES games(id) NOT NULL,
    player_id    uuid REFERENCES players(id),   -- NULL = unresolved
    raw_name     text NOT NULL,                 -- original name from PDF
    rs           int DEFAULT 0,                 -- runs scored
    rc           int DEFAULT 0,                 -- net runs conceded
    wkts         int DEFAULT 0,                 -- wickets taken
    contrib      int DEFAULT 0,                 -- rs - rc
    sr           numeric(6,1) DEFAULT 0,        -- strike rate
    ob           int DEFAULT 0,                 -- overs bowled
    econ         numeric(6,2) DEFAULT 0,        -- economy rate
    dots_faced   int DEFAULT 0,
    dots_bowled  int DEFAULT 0,
    extras       int DEFAULT 0,
    sevens       int DEFAULT 0,                 -- zone D full hits
    d_caught     int DEFAULT 0,
    d_bowled     int DEFAULT 0,
    d_runout     int DEFAULT 0,
    d_stumped    int DEFAULT 0,
    created_at   timestamptz DEFAULT now(),
    UNIQUE (game_id, raw_name)
);

-- View: unresolved names needing a mapping — check this after each new game
CREATE VIEW unresolved_names AS
SELECT
    gs.raw_name,
    g.game_key,
    g.date,
    g.opponent,
    gs.created_at
FROM game_stats gs
JOIN games g ON g.id = gs.game_id
WHERE gs.player_id IS NULL
ORDER BY g.date DESC, gs.raw_name;

-- ── Pair Stats ────────────────────────────────────────────────────────────────
-- One row per skin per game — which pair batted and what they scored
CREATE TABLE pair_stats (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id      uuid REFERENCES games(id) NOT NULL,
    skin         int NOT NULL,              -- 1–4
    player1_id   uuid REFERENCES players(id),
    player2_id   uuid REFERENCES players(id),
    player1_raw  text,                      -- raw names as in PDF
    player2_raw  text,
    dm_runs      int DEFAULT 0,
    opp_runs     int DEFAULT 0,
    dm_wickets   int DEFAULT 0,
    over_runs    jsonb,                     -- {"1": 7, "2": 10, "3": 6, "4": 14}
    skins_won    boolean GENERATED ALWAYS AS (dm_runs > opp_runs) STORED,
    created_at   timestamptz DEFAULT now(),
    UNIQUE (game_id, skin)
);

-- ── Bowling Data ──────────────────────────────────────────────────────────────
-- One row per over bowled — used for the Pairs & Bowling tab heatmap
CREATE TABLE bowling_data (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id     uuid REFERENCES games(id) NOT NULL,
    player_id   uuid REFERENCES players(id),
    raw_name    text NOT NULL,
    skin        int NOT NULL,
    over_num    int NOT NULL,
    rc          int NOT NULL,              -- runs conceded that over
    created_at  timestamptz DEFAULT now(),
    UNIQUE (game_id, skin, over_num)
);

-- =============================================================================
-- Row Level Security
-- =============================================================================
-- The anon (public) key can read everything — the app is public.
-- Only the service_role key (used by the pipeline) can write.

ALTER TABLE seasons      ENABLE ROW LEVEL SECURITY;
ALTER TABLE games        ENABLE ROW LEVEL SECURITY;
ALTER TABLE players      ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_stats   ENABLE ROW LEVEL SECURITY;
ALTER TABLE pair_stats   ENABLE ROW LEVEL SECURITY;
ALTER TABLE bowling_data ENABLE ROW LEVEL SECURITY;

-- Public read on all tables
CREATE POLICY "Public read seasons"       ON seasons       FOR SELECT USING (true);
CREATE POLICY "Public read games"         ON games         FOR SELECT USING (true);
CREATE POLICY "Public read players"       ON players       FOR SELECT USING (true);
CREATE POLICY "Public read aliases"       ON player_aliases FOR SELECT USING (true);
CREATE POLICY "Public read game_stats"    ON game_stats    FOR SELECT USING (true);
CREATE POLICY "Public read pair_stats"    ON pair_stats    FOR SELECT USING (true);
CREATE POLICY "Public read bowling_data"  ON bowling_data  FOR SELECT USING (true);
