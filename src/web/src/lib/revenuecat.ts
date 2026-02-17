import { Purchases, type Package, type CustomerInfo, type Offerings, type PaywallPurchaseResult, ErrorCode, PurchasesError } from '@revenuecat/purchases-js';

// RevenueCat configuration
const RC_API_KEY = process.env.NEXT_PUBLIC_REVENUECAT_API_KEY || '';
const RC_ENTITLEMENT_ID = 'pro';

/**
 * Check if RevenueCat API key is configured.
 * When false, all RC operations should be skipped gracefully.
 */
export function isRevenueCatAvailable(): boolean {
  return !!RC_API_KEY;
}

// Product identifiers (must match mobile + RevenueCat dashboard)
export const PRODUCT_IDS = {
  weekly: 'benchgoblins_pro_weekly',
  monthly: 'benchgoblins_pro_monthly',
  annual: 'benchgoblins_pro_annual',
} as const;

/**
 * Initialize RevenueCat SDK for a given user.
 * Call once when the user is identified (after login or as anonymous).
 */
export function configureRevenueCat(appUserId: string): Purchases {
  if (!RC_API_KEY) {
    throw new Error('NEXT_PUBLIC_REVENUECAT_API_KEY is not set');
  }

  return Purchases.configure(RC_API_KEY, appUserId);
}

/**
 * Generate an anonymous user ID for users who haven't signed in.
 */
export function generateAnonymousUserId(): string {
  return Purchases.generateRevenueCatAnonymousAppUserId();
}

/**
 * Get the shared Purchases instance. Throws if not yet configured.
 */
export function getPurchases(): Purchases {
  return Purchases.getSharedInstance();
}

/**
 * Check if the SDK has been configured.
 */
export function isRevenueCatConfigured(): boolean {
  return Purchases.isConfigured();
}

/**
 * Switch the active user (e.g., after login/logout).
 */
export async function changeUser(newAppUserId: string): Promise<CustomerInfo> {
  return getPurchases().changeUser(newAppUserId);
}

/**
 * Fetch all available offerings (product packages).
 */
export async function getOfferings(currency?: string): Promise<Offerings> {
  const params = currency ? { currency } : undefined;
  return getPurchases().getOfferings(params);
}

/**
 * Get the current customer info (subscriptions, entitlements).
 */
export async function getCustomerInfo(): Promise<CustomerInfo> {
  return getPurchases().getCustomerInfo();
}

/**
 * Check if the current user has the "pro" entitlement.
 */
export async function isProUser(): Promise<boolean> {
  return getPurchases().isEntitledTo(RC_ENTITLEMENT_ID);
}

/**
 * Check entitlement from an existing CustomerInfo object (no network call).
 */
export function hasProEntitlement(customerInfo: CustomerInfo): boolean {
  return RC_ENTITLEMENT_ID in customerInfo.entitlements.active;
}

/**
 * Purchase a package. Opens the RevenueCat checkout UI.
 */
export async function purchasePackage(
  rcPackage: Package,
  options?: {
    customerEmail?: string;
    htmlTarget?: HTMLElement;
  }
): Promise<{ customerInfo: CustomerInfo }> {
  try {
    const result = await getPurchases().purchase({
      rcPackage,
      customerEmail: options?.customerEmail,
      htmlTarget: options?.htmlTarget,
    });
    return result;
  } catch (error) {
    if (error instanceof PurchasesError) {
      if (error.errorCode === ErrorCode.UserCancelledError) {
        throw new UserCancelledError();
      }
    }
    throw error;
  }
}

/**
 * Present the RevenueCat managed paywall UI.
 */
export async function presentPaywall(
  htmlTarget: HTMLElement,
  offeringId?: string
): Promise<PaywallPurchaseResult> {
  const purchases = getPurchases();

  if (offeringId) {
    const offerings = await purchases.getOfferings();
    const offering = offerings.all[offeringId];
    if (offering) {
      return purchases.presentPaywall({ htmlTarget, offering });
    }
  }

  return purchases.presentPaywall({ htmlTarget });
}

/**
 * Custom error for user-cancelled purchases.
 */
export class UserCancelledError extends Error {
  constructor() {
    super('Purchase cancelled by user');
    this.name = 'UserCancelledError';
  }
}

export { RC_ENTITLEMENT_ID, RC_API_KEY };
export type { CustomerInfo, Package, Offerings };
