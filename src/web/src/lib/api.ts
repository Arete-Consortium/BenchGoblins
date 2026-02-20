import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  DecisionRequest,
  DecisionResponse,
  Player,
  DecisionHistoryItem,
  UsageStats,
  HealthResponse,
  Sport,
  SleeperConnectResponse,
  SleeperLeague,
  RosterResponse,
} from '@/types';
import { parseSSE } from './utils';

// Session types
interface CreateSessionRequest {
  platform: 'ios' | 'android' | 'web';
  device_id?: string;
  device_name?: string;
}

interface SessionResponse {
  session_id: string;
  session_token: string;
  platform: string;
  device_id: string | null;
  device_name: string | null;
  status: string;
  created_at: string;
  expires_at: string;
  last_active_at: string;
}

interface ValidateSessionResponse {
  valid: boolean;
  expires_at?: string;
}

// Auth types
interface User {
  id: number;
  email: string;
  name: string;
  picture_url?: string;
  subscription_tier: 'free' | 'pro';
  queries_today: number;
  queries_limit: number;
}

interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// Storage keys
const SESSION_TOKEN_KEY = 'benchgoblin_session_token';
const SESSION_EXPIRES_KEY = 'benchgoblin_session_expires';
const AUTH_TOKEN_KEY = 'benchgoblin_auth_token';

// API base URL: use same-origin proxy (/bapi) in the browser to avoid CORS,
// fall back to the direct backend URL for SSR or when proxy isn't available.
const API_BASE_URL =
  typeof window !== 'undefined'
    ? '/bapi'
    : (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');

class APIClient {
  private client: AxiosInstance;
  private sessionToken: string | null = null;
  private authToken: string | null = null;
  private onAuthError: (() => void) | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Load tokens from storage on init
    if (typeof window !== 'undefined') {
      this.sessionToken = localStorage.getItem(SESSION_TOKEN_KEY);
      this.authToken = localStorage.getItem(AUTH_TOKEN_KEY);
    }

    // Add tokens to all requests
    this.client.interceptors.request.use((config) => {
      // Prefer auth token (JWT) over session token
      if (this.authToken) {
        config.headers['Authorization'] = `Bearer ${this.authToken}`;
      } else if (this.sessionToken) {
        config.headers['X-Session-Token'] = this.sessionToken;
      }
      return config;
    });

    // Handle auth errors
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        if (error.response?.status === 401) {
          // If we have an auth token and it's invalid, clear auth state
          if (this.authToken) {
            this.clearAuthToken();
            if (this.onAuthError) {
              this.onAuthError();
            }
          } else {
            // Session expired or invalid, clear and create new
            this.clearSession();
            await this.ensureSession();
          }
        }
        return Promise.reject(error);
      }
    );
  }

  // Set callback for auth errors (used by auth store)
  setOnAuthError(callback: () => void): void {
    this.onAuthError = callback;
  }

  // Auth token management
  setAuthToken(token: string): void {
    this.authToken = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
    }
  }

  clearAuthToken(): void {
    this.authToken = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  }

  getAuthToken(): string | null {
    return this.authToken;
  }

  isUserAuthenticated(): boolean {
    return !!this.authToken;
  }

  // Session management
  private saveSession(token: string, expiresAt: string): void {
    this.sessionToken = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem(SESSION_TOKEN_KEY, token);
      localStorage.setItem(SESSION_EXPIRES_KEY, expiresAt);
    }
  }

  private clearSession(): void {
    this.sessionToken = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem(SESSION_TOKEN_KEY);
      localStorage.removeItem(SESSION_EXPIRES_KEY);
    }
  }

  async ensureSession(): Promise<void> {
    if (this.sessionToken) {
      // Check if session is valid
      try {
        const valid = await this.validateSession();
        if (valid.valid) return;
      } catch {
        // Session invalid, create new
      }
    }

    // Create new session
    const session = await this.createSession({
      platform: 'web',
      device_id: this.getDeviceId(),
      device_name: this.getDeviceName(),
    });

    this.saveSession(session.session_token, session.expires_at);
  }

  private getDeviceId(): string {
    if (typeof window === 'undefined') return 'server';

    let deviceId = localStorage.getItem('benchgoblin_device_id');
    if (!deviceId) {
      deviceId = `web-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
      localStorage.setItem('benchgoblin_device_id', deviceId);
    }
    return deviceId;
  }

  private getDeviceName(): string {
    if (typeof window === 'undefined') return 'Server';
    return navigator.userAgent.slice(0, 100);
  }

  getSessionToken(): string | null {
    return this.sessionToken;
  }

  isAuthenticated(): boolean {
    return !!this.sessionToken;
  }

  // Session endpoints
  async createSession(data: CreateSessionRequest): Promise<SessionResponse> {
    const response = await this.client.post<SessionResponse>('/sessions', data);
    return response.data;
  }

  async validateSession(): Promise<ValidateSessionResponse> {
    const response = await this.client.get<ValidateSessionResponse>('/sessions/validate');
    return response.data;
  }

  async getSession(): Promise<SessionResponse> {
    const response = await this.client.get<SessionResponse>('/sessions/current');
    return response.data;
  }

  async logout(): Promise<void> {
    try {
      await this.client.delete('/sessions/current');
    } finally {
      this.clearSession();
    }
  }

  // Decision endpoints
  async decide(request: DecisionRequest): Promise<DecisionResponse> {
    await this.ensureSession();
    const response = await this.client.post<DecisionResponse>(
      `/decide?session_id=${this.sessionToken}`,
      request
    );
    return response.data;
  }

  async decideStream(
    request: DecisionRequest,
    onChunk: (chunk: string) => void,
    onComplete?: (response: DecisionResponse) => void
  ): Promise<void> {
    await this.ensureSession();

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Prefer auth token over session token
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    } else if (this.sessionToken) {
      headers['X-Session-Token'] = this.sessionToken;
    }

    const response = await fetch(`${API_BASE_URL}/decide/stream?session_id=${this.sessionToken}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to stream decision');
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const events = parseSSE(chunk);

      for (const event of events) {
        if (event === '[DONE]') {
          // Final response with metadata
          continue;
        }

        try {
          const parsed = JSON.parse(event);
          if (parsed.type === 'content') {
            onChunk(parsed.text);
          } else if (parsed.type === 'done' && onComplete) {
            onComplete(parsed.response);
          }
        } catch {
          // Plain text chunk
          onChunk(event);
        }
      }
    }
  }

  // Player endpoints
  async searchPlayers(query: string, sport: Sport): Promise<Player[]> {
    await this.ensureSession();
    const response = await this.client.post<{ players: Player[] }>('/players/search', {
      query,
      sport,
      limit: 10,
    });
    return response.data.players;
  }

  async getPlayer(playerId: string, sport: Sport): Promise<Player> {
    await this.ensureSession();
    const response = await this.client.get<Player>(`/players/${sport}/${playerId}`);
    return response.data;
  }

  // History endpoints
  async getHistory(limit = 20, sport?: Sport): Promise<DecisionHistoryItem[]> {
    await this.ensureSession();
    const params = new URLSearchParams({ limit: String(limit) });
    if (sport) params.append('sport', sport);
    const response = await this.client.get<{ decisions: DecisionHistoryItem[] }>(
      `/history?${params}`
    );
    return response.data.decisions;
  }

  // Usage endpoints
  async getUsage(): Promise<UsageStats> {
    await this.ensureSession();
    const response = await this.client.get<UsageStats>('/usage');
    return response.data;
  }

  // Auth endpoints
  async authWithGoogle(idToken: string): Promise<AuthResponse> {
    const response = await this.client.post<AuthResponse>('/auth/google', {
      id_token: idToken,
    });
    return response.data;
  }

  async getAuthMe(): Promise<User> {
    const response = await this.client.get<User>('/auth/me');
    return response.data;
  }

  async authLogout(): Promise<void> {
    await this.client.post('/auth/logout');
  }

  // Billing endpoints
  async createCheckoutSession(): Promise<{ checkout_url: string }> {
    const response = await this.client.post<{ checkout_url: string }>('/billing/create-checkout', {
      success_url: `${window.location.origin}/billing?success=true`,
      cancel_url: `${window.location.origin}/billing?canceled=true`,
    });
    return response.data;
  }

  async createPortalSession(): Promise<{ portal_url: string }> {
    const response = await this.client.post<{ portal_url: string }>('/billing/create-portal', {
      return_url: `${window.location.origin}/billing`,
    });
    return response.data;
  }

  async getBillingStatus(): Promise<{
    subscription_tier: string;
    stripe_customer_id: string | null;
    stripe_subscription_id: string | null;
    queries_today: number;
    queries_limit: number;
  }> {
    const response = await this.client.get('/billing/status');
    return response.data;
  }

  // League endpoints (Sleeper)
  async connectSleeper(username: string, sport: string, season = '2025'): Promise<SleeperConnectResponse> {
    const response = await this.client.post<SleeperConnectResponse>('/leagues/connect', {
      username,
      sport,
      season,
    });
    return response.data;
  }

  async getLeagueRoster(leagueId: string, sleeperUserId: string, sport: string): Promise<RosterResponse> {
    const response = await this.client.get<RosterResponse>(`/leagues/${leagueId}/roster`, {
      params: { sleeper_user_id: sleeperUserId, sport },
    });
    return response.data;
  }

  async getLeagueSettings(leagueId: string): Promise<SleeperLeague> {
    const response = await this.client.get<SleeperLeague>(`/leagues/${leagueId}/settings`);
    return response.data;
  }

  async syncLeague(
    username: string,
    leagueId: string,
    sport = 'nfl',
    season = '2025'
  ): Promise<{
    sleeper_username: string;
    sleeper_user_id: string;
    sleeper_league_id: string;
    roster_player_count: number;
    synced_at: string;
  }> {
    const response = await this.client.post('/leagues/sync', {
      username,
      league_id: leagueId,
      sport,
      season,
    });
    return response.data;
  }

  async getMyLeague(): Promise<{
    connected: boolean;
    sleeper_username: string | null;
    sleeper_league_id: string | null;
    sleeper_user_id: string | null;
    roster_player_count: number;
    synced_at: string | null;
  }> {
    const response = await this.client.get('/leagues/me');
    return response.data;
  }

  async disconnectLeague(): Promise<{ disconnected: boolean }> {
    const response = await this.client.delete('/leagues/me');
    return response.data;
  }

  // Newsletter
  async subscribeNewsletter(
    email: string,
    name?: string,
    sport?: string,
    referrer?: string
  ): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<{ success: boolean; message: string }>(
      '/newsletter/subscribe',
      { email, name, sport, referrer }
    );
    return response.data;
  }

  // Accuracy endpoints
  async getAccuracyMetrics(
    sport?: string,
    limit = 500
  ): Promise<{
    total_decisions: number;
    decisions_with_outcomes: number;
    correct_decisions: number;
    incorrect_decisions: number;
    pushes: number;
    accuracy_pct: number;
    coverage_pct: number;
    by_confidence: Record<string, { total: number; correct: number; accuracy: number }>;
    by_source: Record<string, { total: number; correct: number }>;
    by_sport: Record<string, { total: number; correct: number }>;
  }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (sport) params.append('sport', sport);
    const response = await this.client.get(`/accuracy/metrics?${params}`);
    return response.data;
  }

  async syncOutcomes(daysBack = 2, sport?: string): Promise<{ status: string; total_decisions_processed: number; total_outcomes_recorded: number }> {
    const response = await this.client.post('/accuracy/sync', {
      days_back: daysBack,
      ...(sport && { sport }),
    });
    return response.data;
  }

  // Health check
  async getHealth(): Promise<HealthResponse> {
    const response = await this.client.get<HealthResponse>('/health');
    return response.data;
  }
}

// Singleton instance
const api = new APIClient();
export default api;

// Named exports for specific use cases
export { APIClient, API_BASE_URL };
export type { SessionResponse, CreateSessionRequest, ValidateSessionResponse, User, AuthResponse };
