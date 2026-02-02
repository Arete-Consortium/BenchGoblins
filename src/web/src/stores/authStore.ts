'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from '@/lib/api';

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

// Auth response from backend
interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// Auth state interface
interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  accessToken: string | null;

  // Actions
  signInWithGoogle: (idToken: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
  setLoading: (loading: boolean) => void;
  clearAuth: () => void;
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

      // Set loading state
      setLoading: (loading: boolean) => set({ isLoading: loading }),

      // Clear auth state
      clearAuth: () => {
        if (typeof window !== 'undefined') {
          localStorage.removeItem(AUTH_TOKEN_KEY);
        }
        set({
          user: null,
          isAuthenticated: false,
          accessToken: null,
          isLoading: false,
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
    }),
    {
      name: 'benchgoblin-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        // First check for cookie-based session (OAuth workaround)
        const userCookie = getCookie('benchgoblin_user');
        if (userCookie && state) {
          try {
            const cookieUser = JSON.parse(userCookie);
            // Create a user object from cookie data
            state.user = {
              id: 0, // No ID in cookie session
              email: cookieUser.email || '',
              name: cookieUser.name || 'User',
              picture_url: cookieUser.picture,
              subscription_tier: 'free', // Default to free for cookie sessions
              queries_today: 0,
              queries_limit: 5,
            };
            state.isAuthenticated = true;
            state.isLoading = false;
            return; // Don't try to refresh from backend
          } catch (e) {
            console.error('Failed to parse user cookie:', e);
          }
        }

        // Fall back to token-based auth with backend
        if (state?.accessToken) {
          // Set the token in API client
          api.setAuthToken(state.accessToken);
          // Refresh user data in background
          state.refreshUser();
        }
      },
    }
  )
);

export default useAuthStore;
