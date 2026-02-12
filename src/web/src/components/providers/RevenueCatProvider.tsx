'use client';

import { useEffect, useRef } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { useSubscriptionStore } from '@/stores/subscriptionStore';

/**
 * Initializes RevenueCat SDK and keeps it in sync with auth state.
 *
 * - On mount: initializes with anonymous user or authenticated user ID
 * - On login: switches RevenueCat to the authenticated user
 * - On logout: resets subscription state and reinitializes as anonymous
 */
export function RevenueCatProvider({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore();
  const { initialize, switchUser, reset, isInitialized } = useSubscriptionStore();
  const prevAuthRef = useRef<boolean>(false);
  const initRef = useRef<boolean>(false);

  // Initialize on mount
  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    const appUserId = isAuthenticated && user ? String(user.id) : undefined;
    initialize(appUserId);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync with auth state changes
  useEffect(() => {
    const wasAuthenticated = prevAuthRef.current;
    prevAuthRef.current = isAuthenticated;

    if (!isInitialized) return;

    // User just logged in
    if (isAuthenticated && !wasAuthenticated && user) {
      switchUser(String(user.id));
    }

    // User just logged out
    if (!isAuthenticated && wasAuthenticated) {
      reset();
      // Reinitialize as anonymous after a tick
      setTimeout(() => initialize(), 0);
    }
  }, [isAuthenticated, user, isInitialized, switchUser, reset, initialize]);

  return <>{children}</>;
}
