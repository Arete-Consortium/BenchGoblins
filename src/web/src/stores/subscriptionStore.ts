'use client';

import { create } from 'zustand';
import type { CustomerInfo, Offerings, Package } from '@revenuecat/purchases-js';
import {
  configureRevenueCat,
  generateAnonymousUserId,
  changeUser,
  getCustomerInfo,
  getOfferings,
  hasProEntitlement,
  isRevenueCatAvailable,
  isRevenueCatConfigured,
  purchasePackage,
  UserCancelledError,
} from '@/lib/revenuecat';

// Local storage key for anonymous RC user ID
const RC_ANON_USER_KEY = 'benchgoblin_rc_anon_user_id';

interface SubscriptionState {
  // State
  isInitialized: boolean;
  isLoading: boolean;
  isPro: boolean;
  customerInfo: CustomerInfo | null;
  offerings: Offerings | null;
  error: string | null;

  // Actions
  initialize: (appUserId?: string) => Promise<void>;
  switchUser: (appUserId: string) => Promise<void>;
  refreshCustomerInfo: () => Promise<void>;
  refreshOfferings: () => Promise<void>;
  purchase: (rcPackage: Package, email?: string, htmlTarget?: HTMLElement) => Promise<boolean>;
  reset: () => void;
}

export const useSubscriptionStore = create<SubscriptionState>()((set, get) => ({
  // Initial state
  isInitialized: false,
  isLoading: false,
  isPro: false,
  customerInfo: null,
  offerings: null,
  error: null,

  initialize: async (appUserId?: string) => {
    // Skip entirely if not client-side or API key isn't configured
    if (!isRevenueCatAvailable()) {
      set({ isInitialized: false, isLoading: false });
      return;
    }

    if (get().isInitialized && await isRevenueCatConfigured()) return;

    set({ isLoading: true, error: null });

    try {
      const userId = appUserId || await getOrCreateAnonymousUserId();
      await configureRevenueCat(userId);

      // Fetch customer info and offerings in parallel
      const [customerInfo, offerings] = await Promise.all([
        getCustomerInfo(),
        getOfferings(),
      ]);

      set({
        isInitialized: true,
        isLoading: false,
        customerInfo,
        offerings,
        isPro: hasProEntitlement(customerInfo),
      });
    } catch (error) {
      console.error('RevenueCat initialization failed:', error);
      set({
        isInitialized: false,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to initialize subscriptions',
      });
    }
  },

  switchUser: async (appUserId: string) => {
    if (!isRevenueCatAvailable()) return;

    set({ isLoading: true, error: null });

    try {
      if (!await isRevenueCatConfigured()) {
        await configureRevenueCat(appUserId);
      } else {
        await changeUser(appUserId);
      }

      const [customerInfo, offerings] = await Promise.all([
        getCustomerInfo(),
        getOfferings(),
      ]);

      set({
        isInitialized: true,
        isLoading: false,
        customerInfo,
        offerings,
        isPro: hasProEntitlement(customerInfo),
      });
    } catch (error) {
      console.error('RevenueCat user switch failed:', error);
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to switch user',
      });
    }
  },

  refreshCustomerInfo: async () => {
    try {
      const customerInfo = await getCustomerInfo();
      set({
        customerInfo,
        isPro: hasProEntitlement(customerInfo),
      });
    } catch (error) {
      console.error('Failed to refresh customer info:', error);
    }
  },

  refreshOfferings: async () => {
    try {
      const offerings = await getOfferings();
      set({ offerings });
    } catch (error) {
      console.error('Failed to refresh offerings:', error);
    }
  },

  purchase: async (rcPackage: Package, email?: string, htmlTarget?: HTMLElement) => {
    set({ isLoading: true, error: null });

    try {
      const { customerInfo } = await purchasePackage(rcPackage, {
        customerEmail: email,
        htmlTarget,
      });

      set({
        isLoading: false,
        customerInfo,
        isPro: hasProEntitlement(customerInfo),
      });

      return true;
    } catch (error) {
      if (error instanceof UserCancelledError) {
        set({ isLoading: false });
        return false;
      }

      console.error('Purchase failed:', error);
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Purchase failed',
      });
      return false;
    }
  },

  reset: () => {
    set({
      isInitialized: false,
      isLoading: false,
      isPro: false,
      customerInfo: null,
      offerings: null,
      error: null,
    });
  },
}));

/**
 * Get or create an anonymous RevenueCat user ID.
 * Persisted in localStorage so it survives page refreshes.
 */
async function getOrCreateAnonymousUserId(): Promise<string> {
  if (typeof window === 'undefined') return await generateAnonymousUserId();

  let userId = localStorage.getItem(RC_ANON_USER_KEY);
  if (!userId) {
    userId = await generateAnonymousUserId();
    localStorage.setItem(RC_ANON_USER_KEY, userId);
  }
  return userId;
}

export default useSubscriptionStore;
