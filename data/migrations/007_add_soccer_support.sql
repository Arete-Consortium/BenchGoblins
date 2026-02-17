-- Migration 007: Add Soccer support
-- Adds soccer as a supported sport and soccer-specific stat columns

-- Update CHECK constraints to include 'soccer'
ALTER TABLE players DROP CONSTRAINT IF EXISTS players_sport_check;
ALTER TABLE players ADD CONSTRAINT players_sport_check CHECK (sport IN ('nba', 'nfl', 'mlb', 'nhl', 'soccer'));

ALTER TABLE team_defense DROP CONSTRAINT IF EXISTS team_defense_sport_check;
ALTER TABLE team_defense ADD CONSTRAINT team_defense_sport_check CHECK (sport IN ('nba', 'nfl', 'mlb', 'nhl', 'soccer'));

-- Add soccer stats to player_stats
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_goals DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_assists DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_minutes DECIMAL(6,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_shots DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_shots_on_target DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_key_passes DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_tackles DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_interceptions DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_clean_sheets DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_saves DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_goals_conceded DECIMAL(5,2);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_xg DECIMAL(5,3);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS soccer_xa DECIMAL(5,3);

-- Add soccer game stats to game_logs
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_goals_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_assists_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_minutes_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_shots_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_shots_on_target_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_key_passes_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_tackles_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_interceptions_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_clean_sheet BOOLEAN;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_saves_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_goals_conceded_game INTEGER;
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_xg_game DECIMAL(5,3);
ALTER TABLE game_logs ADD COLUMN IF NOT EXISTS soccer_xa_game DECIMAL(5,3);

-- Add soccer position-specific fields to team_defense
ALTER TABLE team_defense ADD COLUMN IF NOT EXISTS vs_fwd DECIMAL(6,2);
ALTER TABLE team_defense ADD COLUMN IF NOT EXISTS vs_mid DECIMAL(6,2);
ALTER TABLE team_defense ADD COLUMN IF NOT EXISTS vs_def DECIMAL(6,2);
ALTER TABLE team_defense ADD COLUMN IF NOT EXISTS vs_gk DECIMAL(6,2);
