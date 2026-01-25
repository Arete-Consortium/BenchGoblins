import axios from 'axios';
import { DecisionRequest, DecisionResponse, Player } from '../types';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function healthCheck(): Promise<{ status: string; version: string }> {
  const response = await api.get('/health');
  return response.data;
}

export async function searchPlayers(
  query: string,
  sport: string,
  limit: number = 10
): Promise<Player[]> {
  const response = await api.post('/players/search', { query, sport, limit });
  return response.data;
}

export async function makeDecision(request: DecisionRequest): Promise<DecisionResponse> {
  const response = await api.post('/decide', request);
  return response.data;
}

export async function getDecisionHistory(limit: number = 20): Promise<DecisionResponse[]> {
  const response = await api.get('/history', { params: { limit } });
  return response.data;
}

// ---------------------------------------------------------------------------
// Push Notifications
// ---------------------------------------------------------------------------

export async function registerPushToken(token: string): Promise<void> {
  await api.post('/notifications/register', { token });
}

export async function unregisterPushToken(token: string): Promise<void> {
  await api.post('/notifications/unregister', { token });
}

// ---------------------------------------------------------------------------
// ESPN Integration
// ---------------------------------------------------------------------------

export interface ESPNCredentials {
  swid: string;
  espn_s2: string;
}

export interface FantasyLeague {
  id: string;
  name: string;
  sport: string;
  season: number;
  team_count: number;
  scoring_type: string;
}

export interface RosterPlayer {
  player_id: string;
  espn_id: string;
  name: string;
  position: string;
  team: string;
  lineup_slot: string;
  projected_points: number | null;
}

export async function connectESPNAccount(
  credentials: ESPNCredentials,
  sessionId: string = 'default',
): Promise<{ connected: boolean; user_id: string | null; leagues_found: number }> {
  const response = await api.post('/integrations/espn/connect', credentials, {
    params: { session_id: sessionId },
  });
  return response.data;
}

export async function getESPNLeagues(
  sport?: string,
  sessionId: string = 'default',
): Promise<FantasyLeague[]> {
  const response = await api.get('/integrations/espn/leagues', {
    params: { session_id: sessionId, sport },
  });
  return response.data;
}

export async function getESPNRoster(
  leagueId: string,
  teamId: number,
  sport: string,
  sessionId: string = 'default',
): Promise<RosterPlayer[]> {
  const response = await api.get(`/integrations/espn/leagues/${leagueId}/roster`, {
    params: { team_id: teamId, sport, session_id: sessionId },
  });
  return response.data;
}

export async function disconnectESPNAccount(sessionId: string = 'default'): Promise<void> {
  await api.delete('/integrations/espn/disconnect', {
    params: { session_id: sessionId },
  });
}

export async function getESPNStatus(
  sessionId: string = 'default',
): Promise<{ connected: boolean; user_id: string | null }> {
  const response = await api.get('/integrations/espn/status', {
    params: { session_id: sessionId },
  });
  return response.data;
}

export default api;
