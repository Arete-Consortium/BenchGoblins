-- BenchGoblins PostgreSQL Schema
-- Fantasy Sports Decision Engine Database

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- PLAYERS: ESPN player cache
-- ============================================================================
CREATE TABLE players (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    espn_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    team VARCHAR(50),
    team_abbrev VARCHAR(10),
    position VARCHAR(20),
    sport VARCHAR(10) NOT NULL CHECK (sport IN ('nba', 'nfl', 'mlb', 'nhl', 'soccer')),
    jersey VARCHAR(10),
    height VARCHAR(20),
    weight VARCHAR(20),
    age INTEGER,
    experience INTEGER,
    headshot_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_players_espn_id ON players(espn_id);
CREATE INDEX idx_players_sport ON players(sport);
CREATE INDEX idx_players_name ON players(name);
CREATE INDEX idx_players_team ON players(team_abbrev);

-- ============================================================================
-- PLAYER_STATS: Current season averages
-- ============================================================================
CREATE TABLE player_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season VARCHAR(10) NOT NULL,  -- e.g., '2024-25'

    -- Common stats
    games_played INTEGER DEFAULT 0,
    games_started INTEGER DEFAULT 0,

    -- NBA stats
    minutes_per_game DECIMAL(5,2),
    points_per_game DECIMAL(5,2),
    rebounds_per_game DECIMAL(5,2),
    assists_per_game DECIMAL(5,2),
    steals_per_game DECIMAL(5,2),
    blocks_per_game DECIMAL(5,2),
    turnovers_per_game DECIMAL(5,2),
    usage_rate DECIMAL(5,2),
    field_goal_pct DECIMAL(5,4),
    three_point_pct DECIMAL(5,4),
    free_throw_pct DECIMAL(5,4),

    -- NFL stats
    pass_yards DECIMAL(8,2),
    pass_tds DECIMAL(5,2),
    pass_ints DECIMAL(5,2),
    rush_yards DECIMAL(8,2),
    rush_tds DECIMAL(5,2),
    receptions DECIMAL(6,2),
    receiving_yards DECIMAL(8,2),
    receiving_tds DECIMAL(5,2),
    targets DECIMAL(6,2),
    snap_pct DECIMAL(5,2),

    -- MLB stats
    batting_avg DECIMAL(4,3),
    home_runs DECIMAL(6,2),
    rbis DECIMAL(6,2),
    stolen_bases DECIMAL(5,2),
    ops DECIMAL(4,3),
    era DECIMAL(5,2),
    wins INTEGER,
    strikeouts DECIMAL(6,2),
    whip DECIMAL(4,3),

    -- NHL stats
    goals DECIMAL(5,2),
    assists_nhl DECIMAL(5,2),
    plus_minus DECIMAL(5,2),
    shots DECIMAL(6,2),
    save_pct DECIMAL(4,3),
    goals_against_avg DECIMAL(4,2),

    -- Soccer stats
    soccer_goals DECIMAL(5,2),
    soccer_assists DECIMAL(5,2),
    soccer_minutes DECIMAL(6,2),
    soccer_shots DECIMAL(5,2),
    soccer_shots_on_target DECIMAL(5,2),
    soccer_key_passes DECIMAL(5,2),
    soccer_tackles DECIMAL(5,2),
    soccer_interceptions DECIMAL(5,2),
    soccer_clean_sheets DECIMAL(5,2),
    soccer_saves DECIMAL(5,2),
    soccer_goals_conceded DECIMAL(5,2),
    soccer_xg DECIMAL(5,3),
    soccer_xa DECIMAL(5,3),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (player_id, season)
);

CREATE INDEX idx_player_stats_player ON player_stats(player_id);
CREATE INDEX idx_player_stats_season ON player_stats(season);

-- ============================================================================
-- GAME_LOGS: Game-by-game stats for trend analysis
-- ============================================================================
CREATE TABLE game_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    game_date DATE NOT NULL,
    opponent VARCHAR(10),  -- Team abbreviation
    home_away CHAR(1) CHECK (home_away IN ('H', 'A')),
    result CHAR(1) CHECK (result IN ('W', 'L')),

    -- NBA game stats
    minutes INTEGER,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    steals INTEGER,
    blocks INTEGER,
    turnovers INTEGER,
    fg_made INTEGER,
    fg_attempted INTEGER,
    three_made INTEGER,
    three_attempted INTEGER,
    ft_made INTEGER,
    ft_attempted INTEGER,

    -- NFL game stats
    pass_yards_game INTEGER,
    pass_tds_game INTEGER,
    pass_ints_game INTEGER,
    rush_yards_game INTEGER,
    rush_tds_game INTEGER,
    receptions_game INTEGER,
    receiving_yards_game INTEGER,
    receiving_tds_game INTEGER,
    targets_game INTEGER,
    snaps INTEGER,
    snap_pct_game DECIMAL(5,2),

    -- MLB game stats
    at_bats INTEGER,
    hits INTEGER,
    home_runs_game INTEGER,
    rbis_game INTEGER,
    stolen_bases_game INTEGER,
    walks INTEGER,
    strikeouts_game INTEGER,
    innings_pitched DECIMAL(4,1),
    earned_runs INTEGER,

    -- NHL game stats
    goals_game INTEGER,
    assists_game INTEGER,
    plus_minus_game INTEGER,
    shots_game INTEGER,
    time_on_ice INTEGER,  -- in seconds
    saves INTEGER,
    goals_against INTEGER,

    -- Soccer game stats
    soccer_goals_game INTEGER,
    soccer_assists_game INTEGER,
    soccer_minutes_game INTEGER,
    soccer_shots_game INTEGER,
    soccer_shots_on_target_game INTEGER,
    soccer_key_passes_game INTEGER,
    soccer_tackles_game INTEGER,
    soccer_interceptions_game INTEGER,
    soccer_clean_sheet BOOLEAN,
    soccer_saves_game INTEGER,
    soccer_goals_conceded_game INTEGER,
    soccer_xg_game DECIMAL(5,3),
    soccer_xa_game DECIMAL(5,3),

    -- Fantasy points (calculated)
    fantasy_points DECIMAL(8,2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (player_id, game_date)
);

CREATE INDEX idx_game_logs_player ON game_logs(player_id);
CREATE INDEX idx_game_logs_date ON game_logs(game_date DESC);
CREATE INDEX idx_game_logs_player_date ON game_logs(player_id, game_date DESC);

-- ============================================================================
-- PLAYER_INDICES: Cached SCI/RMI/GIS/OD/MSF calculations
-- ============================================================================
CREATE TABLE player_indices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- The five qualitative indices (0-100 scale, except OD which is -50 to +50)
    sci DECIMAL(5,2) NOT NULL,      -- Space Creation Index
    rmi DECIMAL(5,2) NOT NULL,      -- Role Motion Index
    gis DECIMAL(5,2) NOT NULL,      -- Gravity Impact Score
    od DECIMAL(5,2) NOT NULL,       -- Opportunity Delta (-50 to +50)
    msf DECIMAL(5,2) NOT NULL,      -- Matchup Space Fit

    -- Composite scores per risk mode
    floor_score DECIMAL(5,2) NOT NULL,
    median_score DECIMAL(5,2) NOT NULL,
    ceiling_score DECIMAL(5,2) NOT NULL,

    -- Context
    opponent VARCHAR(10),           -- Team abbrev if matchup-specific
    game_date DATE,                 -- If calculated for specific game

    -- Metadata for debugging/transparency
    calculation_inputs JSONB,       -- Raw inputs used for calculation

    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '6 hours'
);

CREATE INDEX idx_player_indices_player ON player_indices(player_id);
CREATE INDEX idx_player_indices_expires ON player_indices(expires_at);
CREATE INDEX idx_player_indices_matchup ON player_indices(player_id, opponent, game_date);

-- ============================================================================
-- TEAM_DEFENSE: Opponent defensive rankings for MSF calculation
-- ============================================================================
CREATE TABLE team_defense (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_abbrev VARCHAR(10) NOT NULL,
    sport VARCHAR(10) NOT NULL CHECK (sport IN ('nba', 'nfl', 'mlb', 'nhl', 'soccer')),
    season VARCHAR(10) NOT NULL,

    -- General defensive metrics
    defensive_rating DECIMAL(6,2),
    points_allowed DECIMAL(6,2),
    pace DECIMAL(6,2),

    -- NBA position-specific fantasy points allowed
    vs_pg DECIMAL(6,2),
    vs_sg DECIMAL(6,2),
    vs_sf DECIMAL(6,2),
    vs_pf DECIMAL(6,2),
    vs_c DECIMAL(6,2),

    -- NFL position-specific
    vs_qb DECIMAL(6,2),
    vs_rb DECIMAL(6,2),
    vs_wr DECIMAL(6,2),
    vs_te DECIMAL(6,2),

    -- Soccer position-specific
    vs_fwd DECIMAL(6,2),
    vs_mid DECIMAL(6,2),
    vs_def DECIMAL(6,2),
    vs_gk DECIMAL(6,2),

    -- Additional metrics
    turnovers_forced DECIMAL(5,2),
    sacks DECIMAL(5,2),

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (team_abbrev, sport, season)
);

CREATE INDEX idx_team_defense_team ON team_defense(team_abbrev);
CREATE INDEX idx_team_defense_sport ON team_defense(sport);

-- ============================================================================
-- DECISIONS: Decision history for analytics and improvement
-- ============================================================================
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Request context
    user_id VARCHAR(100),           -- Optional, for future auth
    session_id VARCHAR(100),        -- For grouping related decisions
    sport VARCHAR(10) NOT NULL,
    risk_mode VARCHAR(10) NOT NULL CHECK (risk_mode IN ('floor', 'median', 'ceiling')),
    decision_type VARCHAR(20) NOT NULL,
    query TEXT NOT NULL,

    -- Players involved
    player_a_id UUID REFERENCES players(id),
    player_b_id UUID REFERENCES players(id),
    player_a_name VARCHAR(100),
    player_b_name VARCHAR(100),

    -- Decision result
    decision TEXT NOT NULL,
    confidence VARCHAR(10) NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    rationale TEXT,
    source VARCHAR(10) NOT NULL CHECK (source IN ('local', 'claude')),

    -- Scores and indices
    score_a DECIMAL(5,2),
    score_b DECIMAL(5,2),
    margin DECIMAL(5,2),
    indices_a JSONB,
    indices_b JSONB,

    -- Context
    league_type VARCHAR(50),
    player_context TEXT,            -- Formatted player stats at decision time

    -- Outcome tracking (for future feedback loop)
    actual_outcome VARCHAR(20),     -- 'correct', 'incorrect', 'push'
    actual_points_a DECIMAL(8,2),
    actual_points_b DECIMAL(8,2),
    feedback_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_decisions_user ON decisions(user_id);
CREATE INDEX idx_decisions_created ON decisions(created_at DESC);
CREATE INDEX idx_decisions_sport ON decisions(sport);
CREATE INDEX idx_decisions_outcome ON decisions(actual_outcome) WHERE actual_outcome IS NOT NULL;

-- ============================================================================
-- FUNCTIONS: Helper functions for common operations
-- ============================================================================

-- Function to get recent game averages for a player
CREATE OR REPLACE FUNCTION get_recent_averages(
    p_player_id UUID,
    p_games INTEGER DEFAULT 5
)
RETURNS TABLE (
    avg_minutes DECIMAL,
    avg_points DECIMAL,
    avg_rebounds DECIMAL,
    avg_assists DECIMAL,
    avg_fantasy_points DECIMAL,
    games_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ROUND(AVG(minutes)::DECIMAL, 1),
        ROUND(AVG(points)::DECIMAL, 1),
        ROUND(AVG(rebounds)::DECIMAL, 1),
        ROUND(AVG(assists)::DECIMAL, 1),
        ROUND(AVG(fantasy_points)::DECIMAL, 1),
        COUNT(*)::INTEGER
    FROM (
        SELECT minutes, points, rebounds, assists, fantasy_points
        FROM game_logs
        WHERE player_id = p_player_id
        ORDER BY game_date DESC
        LIMIT p_games
    ) recent;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate trend direction
CREATE OR REPLACE FUNCTION calculate_trend(
    p_player_id UUID,
    p_stat VARCHAR DEFAULT 'fantasy_points',
    p_recent INTEGER DEFAULT 5,
    p_baseline INTEGER DEFAULT 10
)
RETURNS VARCHAR AS $$
DECLARE
    recent_avg DECIMAL;
    baseline_avg DECIMAL;
    diff_pct DECIMAL;
BEGIN
    -- Get recent average
    EXECUTE format('
        SELECT AVG(%I) FROM (
            SELECT %I FROM game_logs
            WHERE player_id = $1
            ORDER BY game_date DESC
            LIMIT $2
        ) r', p_stat, p_stat)
    INTO recent_avg
    USING p_player_id, p_recent;

    -- Get baseline average
    EXECUTE format('
        SELECT AVG(%I) FROM (
            SELECT %I FROM game_logs
            WHERE player_id = $1
            ORDER BY game_date DESC
            LIMIT $2
        ) r', p_stat, p_stat)
    INTO baseline_avg
    USING p_player_id, p_baseline;

    IF baseline_avg IS NULL OR baseline_avg = 0 THEN
        RETURN 'stable';
    END IF;

    diff_pct := ((recent_avg - baseline_avg) / baseline_avg) * 100;

    IF diff_pct > 10 THEN
        RETURN 'up';
    ELSIF diff_pct < -10 THEN
        RETURN 'down';
    ELSE
        RETURN 'stable';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS: Auto-update timestamps
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER players_updated_at
    BEFORE UPDATE ON players
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER player_stats_updated_at
    BEFORE UPDATE ON player_stats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER team_defense_updated_at
    BEFORE UPDATE ON team_defense
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- SESSIONS: Client session management
-- ============================================================================
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Session identification
    session_token VARCHAR(64) UNIQUE NOT NULL,
    device_id VARCHAR(100),
    device_name VARCHAR(100),
    platform VARCHAR(20) NOT NULL CHECK (platform IN ('ios', 'android', 'web')),

    -- Lifecycle
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'revoked')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,

    -- Security
    ip_address INET,
    user_agent TEXT,

    -- Future: User association
    user_id VARCHAR(100)
);

CREATE INDEX idx_sessions_token ON sessions(session_token);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
CREATE INDEX idx_sessions_user ON sessions(user_id) WHERE user_id IS NOT NULL;

-- ============================================================================
-- SESSION_CREDENTIALS: Encrypted credential storage per session
-- ============================================================================
CREATE TABLE session_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- Credential identification
    provider VARCHAR(20) NOT NULL CHECK (provider IN ('espn', 'yahoo', 'sleeper')),

    -- Encrypted data (AES-256-GCM)
    encrypted_data BYTEA NOT NULL,
    encryption_iv BYTEA NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,

    UNIQUE (session_id, provider)
);

CREATE INDEX idx_session_credentials_session ON session_credentials(session_id);
CREATE INDEX idx_session_credentials_provider ON session_credentials(provider);

CREATE TRIGGER sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER session_credentials_updated_at
    BEFORE UPDATE ON session_credentials
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- DEVICE_TOKENS: Push notification device registration
-- ============================================================================
CREATE TABLE device_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(255) UNIQUE NOT NULL,
    user_id VARCHAR(100),
    preferences JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_device_tokens_token ON device_tokens(token);
CREATE INDEX idx_device_tokens_user ON device_tokens(user_id) WHERE user_id IS NOT NULL;

CREATE TRIGGER device_tokens_updated_at
    BEFORE UPDATE ON device_tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
