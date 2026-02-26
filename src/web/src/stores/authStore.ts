'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from '@/lib/api';
import { useLeagueStore } from '@/stores/leagueStore';

// Helper to get cookie by name
function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    const cookieValue = parts.pop()?.split(';').shift();
    return cookieValue ? decodeURIComponent(cookieValue) : null;
  }
  return null;
}

// User type for authenticated users
export interface User {
  id: number;
  email: string;
  name: string;
  picture_url?: string;
  subscription_tier: 'free' | 'pro';
  queries_today: number;
  queries_limit: number; // 5 for free, unlimited for pro
}

// Auth state interface
interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  accessToken: string | null;

  onboardingComplete: boolean;

  // Actions
  signInWithGoogle: (idToken: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
  setLoading: (loading: boolean) => void;
  clearAuth: () => void;
  completeOnboarding: () => void;
}

// Storage key for JWT
const AUTH_TOKEN_KEY = 'benchgoblin_auth_token';

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      isLoading: false,
      isAuthenticated: false,
      accessToken: null,
      onboardingComplete: false,

      // Set loading state
      setLoading: (loading: boolean) => set({ isLoading: loading }),

      // Clear auth state
      clearAuth: () => {
        if (typeof window !== 'undefined') {
          localStorage.removeItem(AUTH_TOKEN_KEY);
          // Clear any auth cookies
          document.cookie = 'benchgoblin_jwt=; path=/; max-age=0; secure; samesite=lax';
          document.cookie = 'benchgoblin_user=; path=/; max-age=0; secure; samesite=lax';
          document.cookie = 'benchgoblin_session=; path=/; max-age=0; secure; samesite=lax';
        }
        set({
          user: null,
          isAuthenticated: false,
          accessToken: null,
          isLoading: false,
          onboardingComplete: false,
        });
      },

      // Sign in with Google ID token
      signInWithGoogle: async (idToken: string) => {
        set({ isLoading: true });
        try {
          const response = await api.authWithGoogle(idToken);
          const { access_token, user } = response;

          // Store token
          if (typeof window !== 'undefined') {
            localStorage.setItem(AUTH_TOKEN_KEY, access_token);
          }

          // Update API client with new token
          api.setAuthToken(access_token);

          set({
            user,
            accessToken: access_token,
            isAuthenticated: true,
            isLoading: false,
          });

          // Restore Sleeper connection from backend (non-blocking)
          useLeagueStore.getState().restoreFromBackend();
        } catch (error) {
          console.error('Google sign-in failed:', error);
          get().clearAuth();
          throw error;
        }
      },

      // Sign out
      signOut: async () => {
        set({ isLoading: true });
        try {
          await api.authLogout();
        } catch (error) {
          console.error('Logout error:', error);
        } finally {
          get().clearAuth();
          api.clearAuthToken();
        }
      },

      // Refresh user data from backend
      refreshUser: async () => {
        const { accessToken } = get();
        if (!accessToken) {
          get().clearAuth();
          return;
        }

        set({ isLoading: true });
        try {
          // Ensure API client has the token
          api.setAuthToken(accessToken);

          const user = await api.getAuthMe();
          set({
            user,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          console.error('Failed to refresh user:', error);
          get().clearAuth();
        }
      },

      // Mark onboarding as complete
      completeOnboarding: () => set({ onboardingComplete: true }),
    }),
    {
      name: 'benchgoblin-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        onboardingComplete: state.onboardingComplete,
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;

        // Check for JWT cookie from OAuth redirect flow
        const jwtCookie = getCookie('benchgoblin_jwt');
        if (jwtCookie) {
          // Clear the cookie now that we've consumed it
          if (typeof window !== 'undefined') {
            document.cookie = 'benchgoblin_jwt=; path=/; max-age=0; secure; samesite=lax';
            document.cookie = 'benchgoblin_user=; path=/; max-age=0; secure; samesite=lax';
          }

          // Use setState so zustand persists the token (direct mutation on
          // the rehydrated state object does NOT trigger set(), so get()
          // inside refreshUser would see null and call clearAuth).
          api.setAuthToken(jwtCookie);
          useAuthStore.setState({ accessToken: jwtCookie, isAuthenticated: true });

          // Now refreshUser will see the token via get()
          useAuthStore.getState().refreshUser().then(() => {
            useLeagueStore.getState().restoreFromBackend();
          });
          return;
        }

        // Check for user cookie without JWT (legacy — prompt re-login)
        const userCookie = getCookie('benchgoblin_user');
        if (userCookie && !state.accessToken) {
          // Cookie-only session has no JWT — clear stale cookies
          if (typeof window !== 'undefined') {
            document.cookie = 'benchgoblin_user=; path=/; max-age=0; secure; samesite=lax';
            document.cookie = 'benchgoblin_session=; path=/; max-age=0; secure; samesite=lax';
          }
          // Don't set isAuthenticated — user needs to re-login
          return;
        }

        // Token-based auth from localStorage
        if (state.accessToken) {
          api.setAuthToken(state.accessToken);
          // Refresh user data from backend to validate the token
          useAuthStore.getState().refreshUser().then(() => {
            useLeagueStore.getState().restoreFromBackend();
          });
        }
      },
    }
  )
);

export default useAuthStore;
