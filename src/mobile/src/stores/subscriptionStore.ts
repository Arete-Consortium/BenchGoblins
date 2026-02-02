import { create } from 'zustand';
import { PurchasesPackage, CustomerInfo } from 'react-native-purchases';
import {
  purchasesService,
  ENTITLEMENT_ID,
  FREE_TIER_LIMITS,
  PRO_TIER_FEATURES,
} from '../services/purchases';
import AsyncStorage from '@react-native-async-storage/async-storage';

const DAILY_QUERIES_KEY = '@benchgoblins/daily_queries';
const LAST_QUERY_DATE_KEY = '@benchgoblins/last_query_date';

interface SubscriptionState {
  // Subscription status
  isPro: boolean;
  isLoading: boolean;
  customerInfo: CustomerInfo | null;

  // Usage tracking
  dailyQueriesUsed: number;

  // Computed
  canMakeQuery: () => boolean;
  getRemainingQueries: () => number;

  // Actions
  initialize: () => Promise<void>;
  checkSubscriptionStatus: () => Promise<void>;
  purchasePackage: (pkg: PurchasesPackage) => Promise<boolean>;
  restorePurchases: () => Promise<boolean>;
  incrementQueryCount: () => Promise<void>;
  resetDailyQueries: () => Promise<void>;
}

const getTodayDateString = () => new Date().toISOString().split('T')[0];

export const useSubscriptionStore = create<SubscriptionState>((set, get) => ({
  isPro: false,
  isLoading: true,
  customerInfo: null,
  dailyQueriesUsed: 0,

  canMakeQuery: () => {
    const { isPro, dailyQueriesUsed } = get();
    if (isPro) return true;
    return dailyQueriesUsed < FREE_TIER_LIMITS.dailyQueries;
  },

  getRemainingQueries: () => {
    const { isPro, dailyQueriesUsed } = get();
    if (isPro) return Infinity;
    return Math.max(0, FREE_TIER_LIMITS.dailyQueries - dailyQueriesUsed);
  },

  initialize: async () => {
    set({ isLoading: true });

    try {
      await purchasesService.configure();

      // Load daily query count
      const lastDateStr = await AsyncStorage.getItem(LAST_QUERY_DATE_KEY);
      const today = getTodayDateString();

      if (lastDateStr !== today) {
        // New day, reset counter
        await AsyncStorage.setItem(LAST_QUERY_DATE_KEY, today);
        await AsyncStorage.setItem(DAILY_QUERIES_KEY, '0');
        set({ dailyQueriesUsed: 0 });
      } else {
        const countStr = await AsyncStorage.getItem(DAILY_QUERIES_KEY);
        set({ dailyQueriesUsed: parseInt(countStr || '0', 10) });
      }

      // Check subscription status
      await get().checkSubscriptionStatus();
    } catch (error) {
      console.error('Failed to initialize subscription store:', error);
    } finally {
      set({ isLoading: false });
    }
  },

  checkSubscriptionStatus: async () => {
    try {
      const customerInfo = await purchasesService.getCustomerInfo();
      const isPro = customerInfo?.entitlements.active[ENTITLEMENT_ID]?.isActive ?? false;

      set({ customerInfo, isPro });
    } catch (error) {
      console.error('Failed to check subscription status:', error);
    }
  },

  purchasePackage: async (pkg: PurchasesPackage) => {
    set({ isLoading: true });

    try {
      const customerInfo = await purchasesService.purchasePackage(pkg);

      if (customerInfo) {
        const isPro = customerInfo.entitlements.active[ENTITLEMENT_ID]?.isActive ?? false;
        set({ customerInfo, isPro });
        return isPro;
      }

      return false;
    } catch (error) {
      console.error('Purchase failed:', error);
      throw error;
    } finally {
      set({ isLoading: false });
    }
  },

  restorePurchases: async () => {
    set({ isLoading: true });

    try {
      const customerInfo = await purchasesService.restorePurchases();

      if (customerInfo) {
        const isPro = customerInfo.entitlements.active[ENTITLEMENT_ID]?.isActive ?? false;
        set({ customerInfo, isPro });
        return isPro;
      }

      return false;
    } catch (error) {
      console.error('Restore failed:', error);
      throw error;
    } finally {
      set({ isLoading: false });
    }
  },

  incrementQueryCount: async () => {
    const { isPro, dailyQueriesUsed } = get();

    // Pro users don't need to track
    if (isPro) return;

    const newCount = dailyQueriesUsed + 1;
    await AsyncStorage.setItem(DAILY_QUERIES_KEY, newCount.toString());
    set({ dailyQueriesUsed: newCount });
  },

  resetDailyQueries: async () => {
    await AsyncStorage.setItem(DAILY_QUERIES_KEY, '0');
    await AsyncStorage.setItem(LAST_QUERY_DATE_KEY, getTodayDateString());
    set({ dailyQueriesUsed: 0 });
  },
}));

// Export feature access helpers
export const getAvailableSports = (isPro: boolean) => {
  return isPro ? PRO_TIER_FEATURES.sports : FREE_TIER_LIMITS.sports;
};

export const hasFeatureAccess = (feature: keyof typeof FREE_TIER_LIMITS.features, isPro: boolean) => {
  return isPro ? PRO_TIER_FEATURES.features[feature] : FREE_TIER_LIMITS.features[feature];
};
