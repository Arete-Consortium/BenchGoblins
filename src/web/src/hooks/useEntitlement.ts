'use client';

import { useSubscriptionStore } from '@/stores/subscriptionStore';

/**
 * Hook to gate features behind the "Bench Goblins Pro" entitlement.
 *
 * Usage:
 *   const { isPro, isLoading, requirePro } = useEntitlement();
 *   if (!isPro) return <UpgradePrompt />;
 */
export function useEntitlement() {
  const { isPro, isLoading, customerInfo, refreshCustomerInfo } = useSubscriptionStore();

  return {
    /** Whether the user has the "Bench Goblins Pro" entitlement */
    isPro,
    /** Whether subscription state is still loading */
    isLoading,
    /** Active entitlements map (for advanced use) */
    activeEntitlements: customerInfo?.entitlements.active ?? {},
    /** Force-refresh entitlement status from RevenueCat */
    refresh: refreshCustomerInfo,
  };
}
