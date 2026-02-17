import Purchases, {
  PurchasesPackage,
  CustomerInfo,
  PurchasesOffering,
  LOG_LEVEL,
} from 'react-native-purchases';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

// Product identifiers - must match App Store Connect configuration
export const ENTITLEMENT_ID = 'pro';
export const PRODUCT_IDS = {
  WEEKLY: 'benchgoblins_pro_weekly',
  MONTHLY: 'benchgoblins_pro_monthly',
  SEASONAL: 'benchgoblins_pro_seasonal',
  LEAGUE_SEASONAL: 'benchgoblins_league_seasonal',
} as const;

// Subscription tier limits
export const FREE_TIER_LIMITS = {
  dailyQueries: 5,
  sports: ['nba', 'nfl', 'mlb', 'nhl', 'soccer'] as const,
  features: {
    aiInsights: false,
    tradeAnalysis: false,
    waiverAlerts: false,
    historicalData: false,
  },
};

export const PRO_TIER_FEATURES = {
  dailyQueries: Infinity,
  sports: ['nba', 'nfl', 'mlb', 'nhl', 'soccer'] as const,
  features: {
    aiInsights: true,
    tradeAnalysis: true,
    waiverAlerts: true,
    historicalData: true,
  },
};

class PurchasesService {
  private isConfigured = false;

  async configure(): Promise<void> {
    if (this.isConfigured) return;

    const apiKey = Platform.select({
      ios: Constants.expoConfig?.extra?.revenueCatApiKey?.ios,
      android: Constants.expoConfig?.extra?.revenueCatApiKey?.android,
    });

    if (!apiKey || apiKey.startsWith('YOUR_')) {
      console.warn('RevenueCat API key not configured. Purchases will not work.');
      return;
    }

    try {
      Purchases.setLogLevel(LOG_LEVEL.DEBUG);
      await Purchases.configure({ apiKey });
      this.isConfigured = true;
      console.log('RevenueCat configured successfully');
    } catch (error) {
      console.error('Failed to configure RevenueCat:', error);
    }
  }

  async getOfferings(): Promise<PurchasesOffering | null> {
    if (!this.isConfigured) {
      await this.configure();
    }

    try {
      const offerings = await Purchases.getOfferings();
      return offerings.current;
    } catch (error) {
      console.error('Failed to get offerings:', error);
      return null;
    }
  }

  async purchasePackage(pkg: PurchasesPackage): Promise<CustomerInfo | null> {
    try {
      const { customerInfo } = await Purchases.purchasePackage(pkg);
      return customerInfo;
    } catch (error: any) {
      if (error.userCancelled) {
        console.log('User cancelled purchase');
        return null;
      }
      console.error('Purchase failed:', error);
      throw error;
    }
  }

  async restorePurchases(): Promise<CustomerInfo | null> {
    try {
      const customerInfo = await Purchases.restorePurchases();
      return customerInfo;
    } catch (error) {
      console.error('Failed to restore purchases:', error);
      throw error;
    }
  }

  async getCustomerInfo(): Promise<CustomerInfo | null> {
    if (!this.isConfigured) {
      await this.configure();
    }

    try {
      const customerInfo = await Purchases.getCustomerInfo();
      return customerInfo;
    } catch (error) {
      console.error('Failed to get customer info:', error);
      return null;
    }
  }

  async checkProAccess(): Promise<boolean> {
    const customerInfo = await this.getCustomerInfo();
    if (!customerInfo) return false;

    return customerInfo.entitlements.active[ENTITLEMENT_ID]?.isActive ?? false;
  }

  async setUserEmail(email: string): Promise<void> {
    try {
      await Purchases.setEmail(email);
    } catch (error) {
      console.error('Failed to set user email:', error);
    }
  }

  async logIn(userId: string): Promise<CustomerInfo | null> {
    try {
      const { customerInfo } = await Purchases.logIn(userId);
      return customerInfo;
    } catch (error) {
      console.error('Failed to log in user:', error);
      return null;
    }
  }

  async logOut(): Promise<void> {
    try {
      await Purchases.logOut();
    } catch (error) {
      console.error('Failed to log out user:', error);
    }
  }
}

export const purchasesService = new PurchasesService();
