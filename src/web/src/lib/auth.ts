import api from './api';
import type { SessionResponse } from './api';

// Auth state
interface AuthState {
  isAuthenticated: boolean;
  session: SessionResponse | null;
  isLoading: boolean;
}

// Get OAuth URLs
export function getGoogleOAuthUrl(): string {
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
  return `${baseUrl}/api/auth/google`;
}

// Check if user is authenticated (session-based)
export function isAuthenticated(): boolean {
  return api.isAuthenticated();
}

// Check if user is authenticated with JWT
export function isUserAuthenticated(): boolean {
  return api.isUserAuthenticated();
}

// Get current session token
export function getSessionToken(): string | null {
  return api.getSessionToken();
}

// Get current auth token (JWT)
export function getAuthToken(): string | null {
  return api.getAuthToken();
}

// Initialize auth state (call on app mount)
export async function initAuth(): Promise<AuthState> {
  try {
    await api.ensureSession();
    const session = await api.getSession();
    return {
      isAuthenticated: true,
      session,
      isLoading: false,
    };
  } catch (error) {
    console.error('Failed to initialize auth:', error);
    return {
      isAuthenticated: false,
      session: null,
      isLoading: false,
    };
  }
}

// Logout (session-based)
export async function logout(): Promise<void> {
  await api.logout();
  // Redirect to home
  if (typeof window !== 'undefined') {
    window.location.href = '/';
  }
}

// Require auth middleware for pages
export function requireAuth(redirectTo = '/auth/login'): void {
  if (typeof window !== 'undefined' && !isAuthenticated()) {
    window.location.href = redirectTo;
  }
}

// Require user auth (JWT-based) for protected pages
export function requireUserAuth(redirectTo = '/auth/login'): void {
  if (typeof window !== 'undefined' && !isUserAuthenticated()) {
    window.location.href = redirectTo;
  }
}

// Protected route HOC data
export async function getProtectedSessionData(): Promise<SessionResponse | null> {
  if (!isAuthenticated()) {
    return null;
  }

  try {
    return await api.getSession();
  } catch {
    return null;
  }
}
