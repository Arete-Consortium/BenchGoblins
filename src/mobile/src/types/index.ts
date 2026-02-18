export type Sport = 'nba' | 'nfl' | 'mlb' | 'nhl' | 'soccer';
export type RiskMode = 'floor' | 'median' | 'ceiling';
export type DecisionType = 'start_sit' | 'trade' | 'waiver' | 'explain';
export type Confidence = 'low' | 'medium' | 'high';

export interface Player {
  id: string;
  name: string;
  team: string;
  position: string;
  sport: Sport;
}

export interface DecisionRequest {
  sport: Sport;
  risk_mode: RiskMode;
  decision_type: DecisionType;
  query: string;
  player_a?: string;
  player_b?: string;
  league_type?: string;
}

export interface DecisionResponse {
  decision: string;
  confidence: Confidence;
  rationale: string;
  details?: Record<string, unknown>;
  source: 'local' | 'claude';
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  decision?: DecisionResponse;
  isError?: boolean;
}
