import axios, { AxiosError } from 'axios';
import { DecisionRequest, DecisionResponse, Player } from '../types';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ---------------------------------------------------------------------------
// Error Handling
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  code: string;
  retryable: boolean;

  constructor(message: string, status: number, code: string, retryable: boolean = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

function handleApiError(error: unknown): never {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string }>;

    // Network error (no response)
    if (!axiosError.response) {
      throw new ApiError(
        'Unable to connect. Check your internet connection.',
        0,
        'NETWORK_ERROR',
        true,
      );
    }

    const status = axiosError.response.status;
    const detail =
      typeof axiosError.response.data?.detail === 'string'
        ? axiosError.response.data.detail
        : undefined;

    switch (status) {
      case 429:
        throw new ApiError(
          detail || 'Too many requests. Please wait a moment.',
          429,
          'RATE_LIMITED',
          true,
        );
      case 402:
        throw new ApiError(
          detail || 'Query limit reached. Upgrade to Pro for unlimited queries.',
          402,
          'LIMIT_REACHED',
          false,
        );
      case 400:
        throw new ApiError(
          detail || 'Invalid request.',
          400,
          'BAD_REQUEST',
          false,
        );
      case 503:
        throw new ApiError(
          detail || 'Service temporarily unavailable. Try again shortly.',
          503,
          'SERVICE_UNAVAILABLE',
          true,
        );
      default:
        throw new ApiError(
          detail || 'Something went wrong. Please try again.',
          status,
          'SERVER_ERROR',
          status >= 500,
        );
    }
  }

  throw new ApiError('An unexpected error occurred.', 0, 'UNKNOWN', true);
}

// ---------------------------------------------------------------------------
// Core API
// ---------------------------------------------------------------------------

export async function healthCheck(): Promise<{ status: string; version: string }> {
  try {
    const response = await api.get('/health');
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function searchPlayers(
  query: string,
  sport: string,
  limit: number = 10
): Promise<Player[]> {
  try {
    const response = await api.post('/players/search', { query, sport, limit });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function makeDecision(request: DecisionRequest): Promise<DecisionResponse> {
  try {
    const response = await api.post('/decide', request);
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function getDecisionHistory(limit: number = 20): Promise<DecisionResponse[]> {
  try {
    const response = await api.get('/history', { params: { limit } });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

// ---------------------------------------------------------------------------
// Push Notifications
// ---------------------------------------------------------------------------

export async function registerPushToken(token: string): Promise<void> {
  try {
    await api.post('/notifications/register', { token });
  } catch (error) {
    handleApiError(error);
  }
}

export async function unregisterPushToken(token: string): Promise<void> {
  try {
    await api.post('/notifications/unregister', { token });
  } catch (error) {
    handleApiError(error);
  }
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
  try {
    const response = await api.post('/integrations/espn/connect', credentials, {
      params: { session_id: sessionId },
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function getESPNLeagues(
  sport?: string,
  sessionId: string = 'default',
): Promise<FantasyLeague[]> {
  try {
    const response = await api.get('/integrations/espn/leagues', {
      params: { session_id: sessionId, sport },
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function getESPNRoster(
  leagueId: string,
  teamId: number,
  sport: string,
  sessionId: string = 'default',
): Promise<RosterPlayer[]> {
  try {
    const response = await api.get(`/integrations/espn/leagues/${leagueId}/roster`, {
      params: { team_id: teamId, sport, session_id: sessionId },
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function disconnectESPNAccount(sessionId: string = 'default'): Promise<void> {
  try {
    await api.delete('/integrations/espn/disconnect', {
      params: { session_id: sessionId },
    });
  } catch (error) {
    handleApiError(error);
  }
}

export async function getESPNStatus(
  sessionId: string = 'default',
): Promise<{ connected: boolean; user_id: string | null }> {
  try {
    const response = await api.get('/integrations/espn/status', {
      params: { session_id: sessionId },
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

// ---------------------------------------------------------------------------
// Sleeper Integration (No Auth Required)
// ---------------------------------------------------------------------------

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
}

export interface SleeperPlayer {
  player_id: string;
  full_name: string;
  team: string | null;
  position: string;
  status: string;
  injury_status: string | null;
}

export interface SleeperRoster {
  roster_id: number;
  owner_id: string;
  players: SleeperPlayer[];
  starters: string[];
}

export interface TrendingPlayer {
  player_id: string;
  count: number;
  player: {
    full_name: string;
    team: string | null;
    position: string;
  } | null;
}

export async function getSleeperUser(username: string): Promise<SleeperUser> {
  try {
    const response = await api.get(`/integrations/sleeper/user/${username}`);
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function getSleeperLeagues(
  userId: string,
  sport: string = 'nfl',
  season: string = '2024',
): Promise<SleeperLeague[]> {
  try {
    const response = await api.get(`/integrations/sleeper/user/${userId}/leagues`, {
      params: { sport, season },
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function getSleeperRoster(
  leagueId: string,
  userId: string,
  sport: string = 'nfl',
): Promise<SleeperRoster> {
  try {
    const response = await api.get(`/integrations/sleeper/league/${leagueId}/roster/${userId}`, {
      params: { sport },
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export async function getSleeperTrending(
  sport: string = 'nfl',
  trendType: 'add' | 'drop' = 'add',
  limit: number = 25,
): Promise<TrendingPlayer[]> {
  try {
    const response = await api.get(`/integrations/sleeper/trending/${sport}`, {
      params: { trend_type: trendType, limit },
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export default api;
