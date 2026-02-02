import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import * as SecureStore from 'expo-secure-store';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import { API_BASE_URL } from '../config';

// -------------------------------------------------------------------------
// Types
// -------------------------------------------------------------------------

export interface CredentialStatus {
  connected: boolean;
  expires_at: string | null;
  expired: boolean;
  updated_at: string | null;
}

export interface SessionResponse {
  session_id: string;
  session_token?: string;
  platform: string;
  device_id: string | null;
  device_name: string | null;
  status: string;
  created_at: string;
  expires_at: string;
  last_active_at: string;
  credentials: Record<string, CredentialStatus>;
}

export interface SessionState {
  // Session data
  sessionId: string | null;
  sessionToken: string | null;
  expiresAt: Date | null;
  status: 'active' | 'expired' | 'revoked' | null;

  // Credential status
  espnConnected: boolean;
  yahooConnected: boolean;
  sleeperUsername: string | null;

  // Loading state
  isInitializing: boolean;
  isRefreshing: boolean;
  error: string | null;

  // Actions
  initSession: () => Promise<void>;
  refreshSession: () => Promise<void>;
  clearSession: () => Promise<void>;
  validateSession: () => Promise<boolean>;

  // Credential actions
  setESPNConnected: (connected: boolean) => void;
  setYahooConnected: (connected: boolean) => void;
  setSleeperUsername: (username: string | null) => void;

  // Internal
  _setSessionFromResponse: (response: SessionResponse) => void;
}

// -------------------------------------------------------------------------
// Secure Storage Adapter
// -------------------------------------------------------------------------

const SECURE_STORE_KEY = 'benchgoblins_session_token';

async function getSecureToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(SECURE_STORE_KEY);
  } catch (error) {
    console.error('Failed to get secure token:', error);
    return null;
  }
}

async function setSecureToken(token: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(SECURE_STORE_KEY, token);
  } catch (error) {
    console.error('Failed to set secure token:', error);
    throw error;
  }
}

async function deleteSecureToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(SECURE_STORE_KEY);
  } catch (error) {
    console.error('Failed to delete secure token:', error);
  }
}

// -------------------------------------------------------------------------
// API Functions
// -------------------------------------------------------------------------

async function getDeviceInfo(): Promise<{ deviceId: string; deviceName: string }> {
  const deviceName = Device.deviceName || `${Device.brand} ${Device.modelName}`;
  // Use a combination of device info for a semi-stable ID
  const deviceId = `${Device.brand}-${Device.modelName}-${Device.osVersion}`.replace(/\s+/g, '-');
  return { deviceId, deviceName };
}

async function createSessionAPI(): Promise<SessionResponse> {
  const { deviceId, deviceName } = await getDeviceInfo();
  const platform = Platform.OS === 'ios' ? 'ios' : 'android';

  const response = await fetch(`${API_BASE_URL}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      platform,
      device_id: deviceId,
      device_name: deviceName,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || 'Failed to create session');
  }

  return response.json();
}

async function getCurrentSessionAPI(token: string): Promise<SessionResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/current`, {
    headers: {
      'X-Session-Token': token,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || 'Failed to get session');
  }

  return response.json();
}

async function refreshSessionAPI(token: string): Promise<SessionResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/refresh`, {
    method: 'POST',
    headers: {
      'X-Session-Token': token,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || 'Failed to refresh session');
  }

  return response.json();
}

async function revokeSessionAPI(token: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/sessions/current`, {
    method: 'DELETE',
    headers: {
      'X-Session-Token': token,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || 'Failed to revoke session');
  }
}

async function validateSessionAPI(token: string): Promise<{ valid: boolean }> {
  const response = await fetch(`${API_BASE_URL}/sessions/validate`, {
    headers: {
      'X-Session-Token': token,
    },
  });

  if (!response.ok) {
    return { valid: false };
  }

  return response.json();
}

// -------------------------------------------------------------------------
// Store
// -------------------------------------------------------------------------

export const useSessionStore = create<SessionState>()((set, get) => ({
  // Initial state
  sessionId: null,
  sessionToken: null,
  expiresAt: null,
  status: null,
  espnConnected: false,
  yahooConnected: false,
  sleeperUsername: null,
  isInitializing: false,
  isRefreshing: false,
  error: null,

  _setSessionFromResponse: (response: SessionResponse) => {
    set({
      sessionId: response.session_id,
      sessionToken: response.session_token || get().sessionToken,
      expiresAt: new Date(response.expires_at),
      status: response.status as 'active' | 'expired' | 'revoked',
      espnConnected: response.credentials?.espn?.connected ?? false,
      yahooConnected: response.credentials?.yahoo?.connected ?? false,
      error: null,
    });
  },

  initSession: async () => {
    const { isInitializing, sessionToken } = get();
    if (isInitializing) return;

    set({ isInitializing: true, error: null });

    try {
      // Check for existing token in secure storage
      let token = sessionToken || (await getSecureToken());

      if (token) {
        // Validate existing session
        try {
          const session = await getCurrentSessionAPI(token);
          get()._setSessionFromResponse(session);
          set({ isInitializing: false });
          return;
        } catch (error) {
          // Token invalid, create new session
          console.log('Existing session invalid, creating new one');
          await deleteSecureToken();
        }
      }

      // Create new session
      const session = await createSessionAPI();

      if (session.session_token) {
        await setSecureToken(session.session_token);
      }

      get()._setSessionFromResponse(session);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to initialize session';
      set({ error: message });
      console.error('Session initialization failed:', error);
    } finally {
      set({ isInitializing: false });
    }
  },

  refreshSession: async () => {
    const { sessionToken, isRefreshing } = get();
    if (isRefreshing || !sessionToken) return;

    set({ isRefreshing: true, error: null });

    try {
      const session = await refreshSessionAPI(sessionToken);
      get()._setSessionFromResponse(session);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to refresh session';
      set({ error: message });
      console.error('Session refresh failed:', error);
    } finally {
      set({ isRefreshing: false });
    }
  },

  clearSession: async () => {
    const { sessionToken } = get();

    try {
      if (sessionToken) {
        await revokeSessionAPI(sessionToken);
      }
    } catch (error) {
      console.error('Failed to revoke session on server:', error);
    }

    await deleteSecureToken();

    set({
      sessionId: null,
      sessionToken: null,
      expiresAt: null,
      status: null,
      espnConnected: false,
      yahooConnected: false,
      sleeperUsername: null,
      error: null,
    });
  },

  validateSession: async () => {
    const { sessionToken } = get();
    if (!sessionToken) return false;

    try {
      const result = await validateSessionAPI(sessionToken);
      return result.valid;
    } catch (error) {
      return false;
    }
  },

  setESPNConnected: (connected: boolean) => {
    set({ espnConnected: connected });
  },

  setYahooConnected: (connected: boolean) => {
    set({ yahooConnected: connected });
  },

  setSleeperUsername: (username: string | null) => {
    set({ sleeperUsername: username });
  },
}));

// -------------------------------------------------------------------------
// Helper Hook
// -------------------------------------------------------------------------

/**
 * Get the current session token for API requests.
 * Returns null if no session is active.
 */
export function getSessionToken(): string | null {
  return useSessionStore.getState().sessionToken;
}

/**
 * Get session headers for API requests.
 */
export function getSessionHeaders(): Record<string, string> {
  const token = getSessionToken();
  if (!token) return {};
  return { 'X-Session-Token': token };
}
