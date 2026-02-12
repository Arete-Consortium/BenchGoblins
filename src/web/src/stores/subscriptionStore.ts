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

  /**
   * Initialize RevenueCat SDK.
   * If appUserId is provided (authenticated user), use it.
   * Otherwise, generate/retrieve an anonymous user ID.
   */
  initialize: async (appUserId?: string) => {
    if (get().isInitialized && isRevenueCatConfigured()) return;

    set({ isLoading: true, error: null });

    try {
      const userId = appUserId || getOrCreateAnonymousUserId();
      configureRevenueCat(userId);

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

  /**
   * Switch to an identified user (after login).
   * Transfers any anonymous purchases to the identified user.
   */
  switchUser: async (appUserId: string) => {
    set({ isLoading: true, error: null });

    try {
      if (!isRevenueCatConfigured()) {
        configureRevenueCat(appUserId);
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

  /**
   * Refresh customer info (e.g., after a purchase or to check status).
   */
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

  /**
   * Refresh available offerings.
   */
  refreshOfferings: async () => {
    try {
      const offerings = await getOfferings();
      set({ offerings });
    } catch (error) {
      console.error('Failed to refresh offerings:', error);
    }
  },

  /**
   * Purchase a package. Returns true if successful, false if cancelled.
   */
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

  /**
   * Reset subscription state (on logout).
   */
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
function getOrCreateAnonymousUserId(): string {
  if (typeof window === 'undefined') return generateAnonymousUserId();

  let userId = localStorage.getItem(RC_ANON_USER_KEY);
  if (!userId) {
    userId = generateAnonymousUserId();
    localStorage.setItem(RC_ANON_USER_KEY, userId);
  }
  return userId;
}

export default useSubscriptionStore;
