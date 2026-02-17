import type { Package, CustomerInfo, Offerings } from '@revenuecat/purchases-js';

// RevenueCat configuration
const RC_API_KEY = process.env.NEXT_PUBLIC_REVENUECAT_API_KEY || '';
const RC_ENTITLEMENT_ID = 'pro';

/**
 * Check if RevenueCat can be used (client-side + API key configured).
 */
export function isRevenueCatAvailable(): boolean {
  return typeof window !== 'undefined' && !!RC_API_KEY;
}

// Product identifiers (must match mobile + RevenueCat dashboard)
export const PRODUCT_IDS = {
  weekly: 'benchgoblins_pro_weekly',
  monthly: 'benchgoblins_pro_monthly',
  seasonal: 'benchgoblins_pro_seasonal',
  league_seasonal: 'benchgoblins_league_seasonal',
} as const;

/**
 * Lazily load the Purchases SDK (only works client-side).
 */
async function getPurchasesClass() {
  const { Purchases } = await import('@revenuecat/purchases-js');
  return Purchases;
}

/**
 * Initialize RevenueCat SDK for a given user.
 * Call once when the user is identified (after login or as anonymous).
 */
export async function configureRevenueCat(appUserId: string) {
  if (!RC_API_KEY) {
    throw new Error('NEXT_PUBLIC_REVENUECAT_API_KEY is not set');
  }

  const Purchases = await getPurchasesClass();
  return Purchases.configure(RC_API_KEY, appUserId);
}

/**
 * Generate an anonymous user ID for users who haven't signed in.
 */
export async function generateAnonymousUserId(): Promise<string> {
  const Purchases = await getPurchasesClass();
  return Purchases.generateRevenueCatAnonymousAppUserId();
}

/**
 * Get the shared Purchases instance. Throws if not yet configured.
 */
export async function getPurchases() {
  const Purchases = await getPurchasesClass();
  return Purchases.getSharedInstance();
}

/**
 * Check if the SDK has been configured.
 */
export async function isRevenueCatConfigured(): Promise<boolean> {
  const Purchases = await getPurchasesClass();
  return Purchases.isConfigured();
}

/**
 * Switch the active user (e.g., after login/logout).
 */
export async function changeUser(newAppUserId: string): Promise<CustomerInfo> {
  const purchases = await getPurchases();
  return purchases.changeUser(newAppUserId);
}

/**
 * Fetch all available offerings (product packages).
 */
export async function getOfferings(currency?: string): Promise<Offerings> {
  const purchases = await getPurchases();
  const params = currency ? { currency } : undefined;
  return purchases.getOfferings(params);
}

/**
 * Get the current customer info (subscriptions, entitlements).
 */
export async function getCustomerInfo(): Promise<CustomerInfo> {
  const purchases = await getPurchases();
  return purchases.getCustomerInfo();
}

/**
 * Check if the current user has the "pro" entitlement.
 */
export async function isProUser(): Promise<boolean> {
  const purchases = await getPurchases();
  return purchases.isEntitledTo(RC_ENTITLEMENT_ID);
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
  const { PurchasesError, ErrorCode } = await import('@revenuecat/purchases-js');
  const purchases = await getPurchases();

  try {
    const result = await purchases.purchase({
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
