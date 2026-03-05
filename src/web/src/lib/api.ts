import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  DecisionRequest,
  DecisionResponse,
  Player,
  DecisionHistoryItem,
  UsageStats,
  HealthResponse,
  Sport,
  RiskMode,
  Confidence,
  DraftDetailsData,
  WaiverCandidate,
  SleeperConnectResponse,
  SleeperLeague,
  RosterResponse,
  WeeklyRecap,
  DossierResponse,
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

// API base URL: call backend directly (CORS configured on backend).
// The /bapi proxy through Vercel has a 10s timeout on Hobby plan which
// is too short for Claude-enriched responses.
const API_BASE_URL =
  process.env.NODE_ENV === 'production'
    ? 'https://backend.benchgoblins.com'
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

    // Handle auth errors — only clear session tokens, NOT the JWT.
    // JWT clearing is handled explicitly by the auth store on logout
    // or token refresh failure. Clearing on every 401 causes a
    // destructive cascade where a single failed request (e.g.,
    // getBillingStatus on page mount) wipes the entire auth state.
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        if (error.response?.status === 401 && !this.authToken) {
          // Only auto-recover anonymous sessions (no JWT)
          this.clearSession();
          await this.ensureSession();
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
      // detail can be a string or an object (e.g. quota exceeded)
      const detail = error.detail;
      if (typeof detail === 'object' && detail !== null) {
        throw new Error(detail.message || JSON.stringify(detail));
      }
      throw new Error(detail || 'Failed to stream decision');
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    const STREAM_TIMEOUT_MS = 60000; // 60s max silence before aborting

    while (true) {
      // Race each read against a timeout — if backend stalls, abort cleanly
      const timeoutPromise = new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), STREAM_TIMEOUT_MS)
      );
      const result = await Promise.race([reader.read(), timeoutPromise]);

      if (result === null) {
        // Timeout — cancel the reader and throw a recoverable error
        reader.cancel();
        throw new Error('Response timed out. Please try again.');
      }

      const { done, value } = result;
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

  // Player dossier
  async getPlayerDossier(sport: Sport, playerId: string): Promise<DossierResponse> {
    await this.ensureSession();
    const response = await this.client.get<DossierResponse>(`/dossier/${sport}/${playerId}`);
    return response.data;
  }

  // Draft endpoint
  async draft(request: {
    sport: Sport;
    risk_mode: RiskMode;
    query: string;
    players?: string[];
    position_needs?: string[];
  }): Promise<{
    recommended_pick: string;
    confidence: Confidence;
    rationale: string;
    details: DraftDetailsData | null;
    source: 'local' | 'claude';
  }> {
    await this.ensureSession();
    const response = await this.client.post('/draft', request);
    return response.data;
  }

  // Waiver endpoint
  async waiverRecommend(request: {
    sport: Sport;
    risk_mode: RiskMode;
    query: string;
    league_id: string;
    sleeper_user_id: string;
    position_filter?: string;
  }): Promise<{
    recommendations: WaiverCandidate[];
    drop_candidates: { name: string; position: string; reason: string }[];
    position_needs: string[];
    confidence: Confidence;
    rationale: string;
    source: 'claude';
  }> {
    await this.ensureSession();
    const response = await this.client.post('/waiver/recommend', request);
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
  async createCheckoutSession(priceId: string): Promise<{ checkout_url: string }> {
    const response = await this.client.post<{ checkout_url: string }>('/billing/create-checkout', {
      price_id: priceId,
      success_url: `${window.location.origin}/billing?success=true`,
      cancel_url: `${window.location.origin}/billing?canceled=true`,
    });
    return response.data;
  }

  async getBillingPrices(): Promise<{ prices: Record<string, string> }> {
    const response = await this.client.get<{ prices: Record<string, string> }>('/billing/prices');
    return response.data;
  }

  async createPortalSession(): Promise<{ portal_url: string }> {
    const response = await this.client.post<{ portal_url: string }>('/billing/create-portal', {
      return_url: `${window.location.origin}/billing`,
    });
    return response.data;
  }

  async getBillingStatus(): Promise<{
    tier: string;
    status: string;
    queries_today: number;
    weekly_limit: number;
    queries_remaining: number | null;
    subscription_id?: string;
    current_period_end?: string;
    cancel_at_period_end?: boolean;
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

  // ESPN Fantasy endpoints
  async syncESPN(
    swid: string,
    espnS2: string,
    leagueId: string,
    teamId: string,
    sport = 'nfl'
  ): Promise<{
    espn_league_id: string;
    espn_team_id: string;
    sport: string;
    roster_player_count: number;
    synced_at: string;
  }> {
    const response = await this.client.post('/leagues/sync-espn', {
      swid,
      espn_s2: espnS2,
      league_id: leagueId,
      team_id: teamId,
      sport,
    });
    return response.data;
  }

  async getMyESPN(): Promise<{
    connected: boolean;
    espn_league_id: string | null;
    espn_team_id: string | null;
    sport: string | null;
    roster_player_count: number;
    synced_at: string | null;
  }> {
    const response = await this.client.get('/leagues/me/espn');
    return response.data;
  }

  async disconnectESPN(): Promise<{ disconnected: boolean }> {
    const response = await this.client.delete('/leagues/me/espn');
    return response.data;
  }

  // Yahoo Fantasy endpoints
  async getYahooAuthUrl(redirectUri: string): Promise<{ auth_url: string; state: string }> {
    const response = await this.client.get('/integrations/yahoo/auth', {
      params: { redirect_uri: redirectUri },
    });
    return response.data;
  }

  async syncYahoo(
    accessToken: string,
    refreshToken: string,
    expiresAt: number,
    leagueKey: string,
    teamKey: string,
    sport = 'nfl'
  ): Promise<{
    yahoo_league_key: string;
    yahoo_team_key: string;
    sport: string;
    roster_player_count: number;
    synced_at: string;
  }> {
    const response = await this.client.post('/leagues/sync-yahoo', {
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_at: expiresAt,
      league_key: leagueKey,
      team_key: teamKey,
      sport,
    });
    return response.data;
  }

  async getMyYahoo(): Promise<{
    connected: boolean;
    yahoo_league_key: string | null;
    yahoo_team_key: string | null;
    sport: string | null;
    roster_player_count: number;
    synced_at: string | null;
  }> {
    const response = await this.client.get('/leagues/me/yahoo');
    return response.data;
  }

  async disconnectYahoo(): Promise<{ disconnected: boolean }> {
    const response = await this.client.delete('/leagues/me/yahoo');
    return response.data;
  }

  // Push notification endpoints
  async registerNotificationToken(token: string): Promise<{ registered: boolean; token: string }> {
    const response = await this.client.post('/notifications/register', { token });
    return response.data;
  }

  async unregisterNotificationToken(token: string): Promise<{ unregistered: boolean }> {
    const response = await this.client.delete('/notifications/register', { data: { token } });
    return response.data;
  }

  async getNotificationPreferences(): Promise<{
    preferences: {
      injury_alerts: boolean;
      lineup_reminders: boolean;
      decision_updates: boolean;
      trending_players: boolean;
    };
    token_count: number;
  }> {
    const response = await this.client.get('/notifications/preferences');
    return response.data;
  }

  async updateNotificationPreferences(prefs: {
    injury_alerts: boolean;
    lineup_reminders: boolean;
    decision_updates: boolean;
    trending_players: boolean;
  }): Promise<{
    preferences: typeof prefs;
    token_count: number;
  }> {
    const response = await this.client.put('/notifications/preferences', prefs);
    return response.data;
  }

  async sendTestNotification(title?: string, body?: string): Promise<{ sent: number; results: unknown[] }> {
    const response = await this.client.post('/notifications/test', { title, body });
    return response.data;
  }

  // Managed league endpoints
  async getManagedLeagues(): Promise<{
    id: number;
    external_league_id: string;
    platform: string;
    name: string;
    sport: string;
    season: string;
    role: string;
    member_count: number;
    has_pro: boolean;
    invite_code: string | null;
  }[]> {
    const response = await this.client.get('/leagues/managed');
    return response.data;
  }

  async getManagedLeague(leagueId: number): Promise<{
    id: number;
    external_league_id: string;
    platform: string;
    name: string;
    sport: string;
    season: string;
    role: string;
    member_count: number;
    has_pro: boolean;
    invite_code: string | null;
  }> {
    const response = await this.client.get(`/leagues/managed/${leagueId}`);
    return response.data;
  }

  async getLeagueMembers(leagueId: number): Promise<{
    user_id: number;
    email: string;
    name: string;
    role: string;
    external_team_id: string | null;
    status: string;
    joined_at: string;
  }[]> {
    const response = await this.client.get(`/leagues/managed/${leagueId}/members`);
    return response.data;
  }

  async generateInvite(leagueId: number): Promise<{ invite_code: string; invite_url: string }> {
    const response = await this.client.post(`/leagues/managed/${leagueId}/invite`);
    return response.data;
  }

  async joinLeagueByInvite(inviteCode: string): Promise<{ joined: boolean; league_id: number; role?: string; reason?: string }> {
    const response = await this.client.post(`/leagues/join/${inviteCode}`);
    return response.data;
  }

  async removeLeagueMember(leagueId: number, userId: number): Promise<{ removed: boolean }> {
    const response = await this.client.delete(`/leagues/managed/${leagueId}/members/${userId}`);
    return response.data;
  }

  // Commissioner AI tools
  async getPowerRankings(leagueId: number): Promise<{
    league_id: number;
    league_name: string;
    rankings: { rank: number; owner_id: string; display_name: string | null; roster_size: number; strength_score: number }[];
    generated_at: string;
  }> {
    const response = await this.client.get(`/commissioner/leagues/${leagueId}/power-rankings`);
    return response.data;
  }

  async checkTradeFairness(leagueId: number, teamAPlayers: string[], teamBPlayers: string[]): Promise<{
    fairness_score: number;
    verdict: string;
    reasoning: string;
    source: string;
  }> {
    const response = await this.client.post(`/commissioner/leagues/${leagueId}/trade-check`, {
      team_a_players: teamAPlayers,
      team_b_players: teamBPlayers,
    });
    return response.data;
  }

  async getRosterAnalysis(leagueId: number): Promise<{
    league_id: number;
    teams: { owner_id: string; display_name: string | null; roster_size: number; starters_count: number; strengths: string[]; weaknesses: string[] }[];
  }> {
    const response = await this.client.get(`/commissioner/leagues/${leagueId}/roster-analysis`);
    return response.data;
  }

  async getLeagueActivity(leagueId: number): Promise<{
    league_id: number;
    total_members: number;
    active_members: number;
    members: { user_id: number; name: string; email: string; queries_this_week: number; last_active: string | null; is_active: boolean }[];
  }> {
    const response = await this.client.get(`/commissioner/leagues/${leagueId}/activity`);
    return response.data;
  }

  // Dispute resolution
  async fileDispute(leagueId: number, data: {
    category: string;
    subject: string;
    description: string;
    against_user_id?: number;
  }): Promise<{
    id: number; league_id: number; category: string; subject: string;
    description: string; status: string; created_at: string;
  }> {
    const response = await this.client.post(`/commissioner/leagues/${leagueId}/disputes`, data);
    return response.data;
  }

  async getDisputes(leagueId: number): Promise<{
    league_id: number;
    total: number;
    open: number;
    resolved: number;
    disputes: {
      id: number; league_id: number; filed_by_user_id: number; filed_by_name: string | null;
      against_user_id: number | null; against_name: string | null; category: string;
      subject: string; description: string; status: string; resolution: string | null;
      resolved_by_name: string | null; resolved_at: string | null; created_at: string;
    }[];
  }> {
    const response = await this.client.get(`/commissioner/leagues/${leagueId}/disputes`);
    return response.data;
  }

  async resolveDispute(leagueId: number, disputeId: number, data: {
    status: 'resolved' | 'dismissed';
    resolution: string;
  }): Promise<{ id: number; status: string; resolution: string }> {
    const response = await this.client.patch(
      `/commissioner/leagues/${leagueId}/disputes/${disputeId}`,
      data
    );
    return response.data;
  }

  // Rivalry tracking
  async syncRivalries(leagueId: number, season = '2025', weeks = '1-18'): Promise<{ upserted: number; message: string }> {
    const response = await this.client.post(`/rivalries/${leagueId}/sync`, null, {
      params: { season, weeks },
    });
    return response.data;
  }

  async getLeagueRivalries(leagueId: number, season?: string): Promise<{
    owner_a: string;
    owner_b: string;
    games_played: number;
    wins_a: number;
    wins_b: number;
    ties: number;
    avg_margin: number;
    total_points_a: number;
    total_points_b: number;
  }[]> {
    const response = await this.client.get(`/rivalries/${leagueId}`, {
      params: season ? { season } : {},
    });
    return response.data;
  }

  async getMyRivalries(leagueId: number, season?: string): Promise<{
    opponent: string;
    games_played: number;
    wins: number;
    losses: number;
    ties: number;
    win_pct: number;
  }[]> {
    const response = await this.client.get(`/rivalries/${leagueId}/me`, {
      params: season ? { season } : {},
    });
    return response.data;
  }

  async getH2HRecord(leagueId: number, ownerA: string, ownerB: string, season?: string): Promise<{
    owner_a: string;
    owner_b: string;
    wins_a: number;
    wins_b: number;
    ties: number;
    total_points_a: number;
    total_points_b: number;
    matchups: { season: string; week: number; points_a: number; points_b: number; winner: string | null }[];
  }> {
    const response = await this.client.get(`/rivalries/${leagueId}/h2h`, {
      params: { owner_a: ownerA, owner_b: ownerB, ...(season ? { season } : {}) },
    });
    return response.data;
  }

  // Goblin Verdicts
  async getGoblinVerdict(riskMode = 'median', week?: number): Promise<GoblinVerdict> {
    const params: Record<string, string | number> = { risk_mode: riskMode };
    if (week) params.week = week;
    const response = await this.client.get<GoblinVerdict>('/goblin/verdict', { params });
    return response.data;
  }

  async generateGoblinVerdict(riskMode = 'median', week?: number): Promise<GoblinVerdict> {
    const params: Record<string, string | number> = { risk_mode: riskMode };
    if (week) params.week = week;
    const response = await this.client.post<GoblinVerdict>('/goblin/verdict/generate', null, { params });
    return response.data;
  }

  // Weekly recaps
  async getWeeklyRecaps(limit = 10): Promise<WeeklyRecap[]> {
    const response = await this.client.get<WeeklyRecap[]>('/recaps/weekly', {
      params: { limit },
    });
    return response.data;
  }

  async generateWeeklyRecap(): Promise<WeeklyRecap | null> {
    const response = await this.client.post<WeeklyRecap | null>('/recaps/weekly/generate');
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
