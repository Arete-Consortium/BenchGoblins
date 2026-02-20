// Sport types
export type Sport = 'nba' | 'nfl' | 'mlb' | 'nhl' | 'soccer';

// Risk modes for decision making
export type RiskMode = 'floor' | 'median' | 'ceiling';

// Decision types
export type DecisionType = 'start_sit' | 'trade' | 'waiver' | 'explain';

// Confidence levels
export type Confidence = 'low' | 'medium' | 'high';

// League types
export type LeagueType = 'points' | 'categories' | 'half-ppr' | 'ppr' | 'standard';

// Five-index scoring system
export interface PlayerIndices {
  sci: number; // Space Creation Index
  rmi: number; // Role Motion Index
  gis: number; // Gravity Impact Score
  od: number;  // Opportunity Delta
  msf: number; // Matchup Space Fit
}

// Player stats for comparison (start/sit)
export interface PlayerDetails {
  name: string;
  score: number;
  indices: PlayerIndices;
}

// Trade analyzer types
export interface TradePlayerDetails {
  name: string;
  team: string;
  score: number;
  indices: PlayerIndices;
}

export interface TradeSideDetails {
  players: TradePlayerDetails[];
  total_score: number;
}

export interface TradeDetailsData {
  side_giving: TradeSideDetails;
  side_receiving: TradeSideDetails;
  net_value: number;
  margin: number;
  risk_mode: string;
  sport: string;
}

export interface StartSitDetailsData {
  player_a: PlayerDetails;
  player_b: PlayerDetails;
  margin: number;
}

// Decision request to API
export interface DecisionRequest {
  sport: Sport;
  risk_mode: RiskMode;
  decision_type: DecisionType;
  query: string;
  player_a?: string;
  player_b?: string;
  league_type?: LeagueType;
  league_id?: string;
  sleeper_user_id?: string;
}

// Sleeper integration types
export interface SleeperUser {
  user_id: string;
  username: string;
  display_name: string;
  avatar: string | null;
}

export interface SleeperLeague {
  league_id: string;
  name: string;
  sport: string;
  season: string;
  status: string;
  total_rosters: number;
  roster_positions: string[];
  scoring_settings: Record<string, unknown>;
}

export interface SleeperConnectResponse {
  sleeper_user: SleeperUser;
  leagues: SleeperLeague[];
}

export interface RosterPlayer {
  player_id: string;
  full_name: string;
  team: string | null;
  position: string;
  status: string;
  injury_status: string | null;
  is_starter: boolean;
}

export interface RosterResponse {
  roster_id: number;
  owner_id: string;
  players: RosterPlayer[];
}

// Decision response from API
export interface DecisionResponse {
  decision: string;
  confidence: Confidence;
  rationale: string;
  source: 'local' | 'claude';
  details?: StartSitDetailsData | TradeDetailsData;
}

// Chat message
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  decision?: DecisionResponse;
}

// Player search result
export interface Player {
  id: string;
  name: string;
  team: string;
  position: string;
  sport: Sport;
  imageUrl?: string;
}

// Player search response
export interface PlayerSearchResponse {
  players: Player[];
  total: number;
}

// Decision history item
export interface DecisionHistoryItem {
  id: string;
  query: string;
  decision: string;
  confidence: Confidence;
  sport: Sport;
  risk_mode: RiskMode;
  source: 'local' | 'claude';
  created_at: string;
  outcome?: 'correct' | 'incorrect' | 'pending';
}

// User usage stats
export interface UsageStats {
  queries_today: number;
  queries_limit: number;
  tokens_used: number;
  cost_usd: number;
}

// Health check response
export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  components: {
    database: boolean;
    redis: boolean;
    claude: boolean;
    espn: boolean;
  };
}

// Subscription tier
export type SubscriptionTier = 'free' | 'pro';

// User subscription state
export interface Subscription {
  tier: SubscriptionTier;
  queriesRemaining: number;
  queriesLimit: number;
  expiresAt?: string;
}
