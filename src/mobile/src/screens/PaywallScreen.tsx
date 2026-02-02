import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { PurchasesPackage, PurchasesOffering } from 'react-native-purchases';
import { purchasesService } from '../services/purchases';
import { useSubscriptionStore } from '../stores/subscriptionStore';
import { useThemeStore } from '../stores/themeStore';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';

type PaywallScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const FEATURES = [
  { icon: 'infinite', title: 'Unlimited Queries', description: 'Ask as many questions as you need' },
  { icon: 'american-football', title: 'All Sports', description: 'NBA, NFL, MLB, and NHL coverage' },
  { icon: 'analytics', title: 'AI Deep Analysis', description: 'Advanced Claude-powered insights' },
  { icon: 'swap-horizontal', title: 'Trade Analyzer', description: 'Complex multi-player trade evaluation' },
  { icon: 'notifications', title: 'Waiver Alerts', description: 'Get notified of hot pickups' },
  { icon: 'time', title: 'Historical Data', description: 'Access past performance trends' },
];

export default function PaywallScreen({ navigation }: PaywallScreenProps) {
  const [offering, setOffering] = useState<PurchasesOffering | null>(null);
  const [selectedPackage, setSelectedPackage] = useState<PurchasesPackage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPurchasing, setIsPurchasing] = useState(false);

  const { purchasePackage, restorePurchases, isPro } = useSubscriptionStore();
  const { theme } = useThemeStore();

  useEffect(() => {
    loadOfferings();
  }, []);

  useEffect(() => {
    // If user becomes pro, go back
    if (isPro) {
      navigation.goBack();
    }
  }, [isPro, navigation]);

  const loadOfferings = async () => {
    try {
      const currentOffering = await purchasesService.getOfferings();
      setOffering(currentOffering);

      // Auto-select annual as best value
      if (currentOffering?.annual) {
        setSelectedPackage(currentOffering.annual);
      } else if (currentOffering?.availablePackages?.[0]) {
        setSelectedPackage(currentOffering.availablePackages[0]);
      }
    } catch (error) {
      console.error('Failed to load offerings:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePurchase = async () => {
    if (!selectedPackage) return;

    setIsPurchasing(true);
    try {
      const success = await purchasePackage(selectedPackage);
      if (success) {
        Alert.alert('Welcome to Pro!', 'You now have unlimited access to BenchGoblins.');
      }
    } catch (error: any) {
      Alert.alert('Purchase Failed', error.message || 'Please try again later.');
    } finally {
      setIsPurchasing(false);
    }
  };

  const handleRestore = async () => {
    setIsPurchasing(true);
    try {
      const success = await restorePurchases();
      if (success) {
        Alert.alert('Restored!', 'Your subscription has been restored.');
      } else {
        Alert.alert('No Purchases Found', 'We couldn\'t find any previous purchases to restore.');
      }
    } catch (error: any) {
      Alert.alert('Restore Failed', error.message || 'Please try again later.');
    } finally {
      setIsPurchasing(false);
    }
  };

  const formatPrice = (pkg: PurchasesPackage) => {
    const price = pkg.product.priceString;
    const period = pkg.packageType;

    switch (period) {
      case 'WEEKLY':
        return `${price}/week`;
      case 'MONTHLY':
        return `${price}/month`;
      case 'ANNUAL':
        return `${price}/year`;
      default:
        return price;
    }
  };

  const getPackageLabel = (pkg: PurchasesPackage) => {
    switch (pkg.packageType) {
      case 'WEEKLY':
        return 'Weekly';
      case 'MONTHLY':
        return 'Monthly';
      case 'ANNUAL':
        return 'Annual';
      default:
        return pkg.identifier;
    }
  };

  const getSavingsLabel = (pkg: PurchasesPackage) => {
    if (pkg.packageType === 'ANNUAL') {
      return 'BEST VALUE - Save 50%';
    }
    return null;
  };

  if (isLoading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
        <ActivityIndicator size="large" color={theme.primary} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <ScrollView style={styles.scrollView} contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.closeButton} onPress={() => navigation.goBack()}>
            <Ionicons name="close" size={28} color={theme.text} />
          </TouchableOpacity>
          <Text style={[styles.title, { color: theme.text }]}>Upgrade to Pro</Text>
          <Text style={[styles.subtitle, { color: theme.textSecondary }]}>
            Unlock unlimited fantasy sports intelligence
          </Text>
        </View>

        {/* Features */}
        <View style={styles.featuresContainer}>
          {FEATURES.map((feature, index) => (
            <View key={index} style={styles.featureRow}>
              <View style={styles.featureIcon}>
                <Ionicons name={feature.icon as any} size={24} color={theme.primary} />
              </View>
              <View style={styles.featureText}>
                <Text style={[styles.featureTitle, { color: theme.text }]}>{feature.title}</Text>
                <Text style={[styles.featureDescription, { color: theme.textSecondary }]}>{feature.description}</Text>
              </View>
            </View>
          ))}
        </View>

        {/* Packages */}
        <View style={styles.packagesContainer}>
          {offering?.availablePackages.map((pkg) => {
            const isSelected = selectedPackage?.identifier === pkg.identifier;
            const savings = getSavingsLabel(pkg);

            return (
              <TouchableOpacity
                key={pkg.identifier}
                style={[styles.packageCard, { backgroundColor: theme.backgroundSecondary }, isSelected && { borderColor: theme.primary }]}
                onPress={() => setSelectedPackage(pkg)}
              >
                {savings && (
                  <View style={[styles.savingsBadge, { backgroundColor: theme.primary }]}>
                    <Text style={styles.savingsText}>{savings}</Text>
                  </View>
                )}
                <View style={styles.packageContent}>
                  <View style={[styles.radioOuter, { borderColor: theme.primary }]}>
                    {isSelected && <View style={[styles.radioInner, { backgroundColor: theme.primary }]} />}
                  </View>
                  <View style={styles.packageInfo}>
                    <Text style={[styles.packageLabel, { color: theme.text }]}>{getPackageLabel(pkg)}</Text>
                    <Text style={[styles.packagePrice, { color: theme.textSecondary }]}>{formatPrice(pkg)}</Text>
                  </View>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* CTA */}
        <TouchableOpacity
          style={[styles.purchaseButton, { backgroundColor: theme.primary }, isPurchasing && styles.purchaseButtonDisabled]}
          onPress={handlePurchase}
          disabled={isPurchasing || !selectedPackage}
        >
          {isPurchasing ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.purchaseButtonText}>
              Start Free Trial
            </Text>
          )}
        </TouchableOpacity>

        {/* Restore */}
        <TouchableOpacity style={styles.restoreButton} onPress={handleRestore}>
          <Text style={[styles.restoreButtonText, { color: theme.primary }]}>Restore Purchases</Text>
        </TouchableOpacity>

        {/* Legal */}
        <Text style={[styles.legalText, { color: theme.textTertiary }]}>
          Payment will be charged to your Apple ID account at confirmation of purchase.
          Subscription automatically renews unless auto-renew is turned off at least
          24 hours before the end of the current period. Your account will be charged
          for renewal within 24 hours prior to the end of the current period.
        </Text>

        <View style={styles.legalLinks}>
          <TouchableOpacity onPress={() => navigation.navigate('PrivacyPolicy')}>
            <Text style={[styles.legalLink, { color: theme.primary }]}>Privacy Policy</Text>
          </TouchableOpacity>
          <Text style={[styles.legalSeparator, { color: theme.textTertiary }]}>|</Text>
          <TouchableOpacity onPress={() => navigation.navigate('TermsOfService')}>
            <Text style={[styles.legalLink, { color: theme.primary }]}>Terms of Service</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 24,
  },
  header: {
    alignItems: 'center',
    marginBottom: 32,
  },
  closeButton: {
    position: 'absolute',
    top: 0,
    right: 0,
    padding: 8,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#9ca3af',
    textAlign: 'center',
  },
  featuresContainer: {
    marginBottom: 32,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  featureIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 16,
  },
  featureText: {
    flex: 1,
  },
  featureTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 2,
  },
  featureDescription: {
    fontSize: 14,
    color: '#9ca3af',
  },
  packagesContainer: {
    marginBottom: 24,
  },
  packageCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: 'transparent',
    marginBottom: 12,
    overflow: 'hidden',
  },
  packageCardSelected: {
    borderColor: '#6366f1',
  },
  savingsBadge: {
    backgroundColor: '#6366f1',
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  savingsText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: 'bold',
    textAlign: 'center',
  },
  packageContent: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  radioOuter: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#6366f1',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 16,
  },
  radioInner: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#6366f1',
  },
  packageInfo: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  packageLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  packagePrice: {
    fontSize: 16,
    color: '#9ca3af',
  },
  purchaseButton: {
    backgroundColor: '#6366f1',
    borderRadius: 12,
    padding: 18,
    alignItems: 'center',
    marginBottom: 16,
  },
  purchaseButtonDisabled: {
    opacity: 0.6,
  },
  purchaseButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  restoreButton: {
    alignItems: 'center',
    padding: 12,
    marginBottom: 24,
  },
  restoreButtonText: {
    color: '#6366f1',
    fontSize: 16,
  },
  legalText: {
    fontSize: 11,
    color: '#6b7280',
    textAlign: 'center',
    lineHeight: 16,
    marginBottom: 16,
  },
  legalLinks: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  legalLink: {
    color: '#6366f1',
    fontSize: 12,
  },
  legalSeparator: {
    color: '#6b7280',
    marginHorizontal: 8,
  },
});
