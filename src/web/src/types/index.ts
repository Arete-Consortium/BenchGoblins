// Sport types
export type Sport = 'nba' | 'nfl' | 'mlb' | 'nhl' | 'soccer';

// Risk modes for decision making
export type RiskMode = 'floor' | 'median' | 'ceiling';

// Decision types
export type DecisionType = 'start_sit' | 'trade' | 'waiver' | 'explain' | 'draft';

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

// Draft assistant types
export interface DraftPickDetails {
  rank: number;
  name: string;
  team: string;
  position: string;
  score: number;
  base_score: number;
  indices: PlayerIndices;
  position_boosted: boolean;
}

export interface DraftDetailsData {
  ranked_players: DraftPickDetails[];
  risk_mode: string;
  sport: string;
  position_needs: string[] | null;
}

// Waiver wire types
export interface WaiverCandidate {
  name: string;
  position: string;
  team: string;
  rationale: string;
  priority: number;
}

export interface WaiverDetailsData {
  recommendations: WaiverCandidate[];
  drop_candidates: { name: string; position: string; reason: string }[];
  position_needs: string[];
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
  details?: StartSitDetailsData | TradeDetailsData | DraftDetailsData | WaiverDetailsData;
}

// Chat message
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  decision?: DecisionResponse;
  suggestions?: string[];
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

// Goblin Verdict types
export interface SwapRecommendation {
  bench_player: string;
  start_player: string;
  confidence: number;
  reasoning: string;
  urgency: 'critical' | 'recommended' | 'optional';
}

export interface GoblinVerdict {
  team_name: string;
  week: number;
  season: number;
  risk_mode: RiskMode;
  swaps: SwapRecommendation[];
  verdict_headline: string;
  overall_outlook: string;
  generated_at: string;
  cached: boolean;
}

// Weekly recap
export interface WeeklyRecap {
  id: string;
  week_start: string;
  week_end: string;
  total_decisions: number;
  correct_decisions: number;
  incorrect_decisions: number;
  pending_decisions: number;
  accuracy_pct: number | null;
  avg_confidence: string | null;
  most_asked_sport: string | null;
  narrative: string;
  highlights: string | null;
  created_at: string;
}

// Dossier types
export interface DossierIndices {
  sci: number;
  rmi: number;
  gis: number;
  od: number;
  msf: number;
  floor_score: number;
  median_score: number;
  ceiling_score: number;
  calculated_at: string;
  opponent: string | null;
  game_date: string | null;
}

export interface DossierGameLog {
  game_date: string;
  opponent: string | null;
  home_away: string | null;
  result: string | null;
  fantasy_points: number | null;
  stats: Record<string, number>;
}

export interface DossierDecision {
  id: string;
  decision_type: string;
  query: string;
  decision: string;
  confidence: string;
  risk_mode: string;
  source: string;
  created_at: string;
  outcome: string | null;
}

export interface DossierPlayerDetail {
  id: string;
  name: string;
  team: string | null;
  team_abbrev: string | null;
  position: string | null;
  sport: string;
  headshot_url: string | null;
  stats: Record<string, number> | null;
}

export interface DossierSummary {
  games_played: number;
  total_indices: number;
  total_game_logs: number;
  total_decisions: number;
  latest_median: number | null;
}

export interface DossierResponse {
  player: DossierPlayerDetail;
  indices: DossierIndices[];
  game_logs: DossierGameLog[];
  decisions: DossierDecision[];
  summary: DossierSummary;
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
