import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Alert, Linking, Switch } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSubscriptionStore } from '../stores/subscriptionStore';
import { useThemeStore, ThemeMode } from '../stores/themeStore';
import { FREE_TIER_LIMITS } from '../services/purchases';
import { hapticSelection } from '../utils/haptics';

type SettingsScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

export default function SettingsScreen({ navigation }: SettingsScreenProps) {
  const { isPro, restorePurchases, dailyQueriesUsed, isLoading } = useSubscriptionStore();
  const { mode, isDark, setMode, theme } = useThemeStore();

  const handleThemeChange = (newMode: ThemeMode) => {
    hapticSelection();
    setMode(newMode);
  };

  const handleRestorePurchases = async () => {
    try {
      const success = await restorePurchases();
      if (success) {
        Alert.alert('Restored!', 'Your subscription has been restored.');
      } else {
        Alert.alert('No Purchases Found', 'We couldn\'t find any previous purchases to restore.');
      }
    } catch (error: any) {
      Alert.alert('Restore Failed', error.message || 'Please try again later.');
    }
  };

  const handleManageSubscription = () => {
    Linking.openURL('https://apps.apple.com/account/subscriptions');
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <View style={[styles.header, { borderBottomColor: theme.border }]}>
        <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
          <Ionicons name="arrow-back" size={24} color={theme.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: theme.text }]}>Settings</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView style={styles.scrollView}>
        {/* Subscription Status */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.textTertiary }]}>Subscription</Text>

          <View style={[styles.subscriptionCard, { backgroundColor: theme.backgroundSecondary }]}>
            <View style={styles.subscriptionHeader}>
              {isPro ? (
                <>
                  <View style={styles.proBadge}>
                    <Ionicons name="star" size={16} color="#fbbf24" />
                    <Text style={styles.proBadgeText}>PRO</Text>
                  </View>
                  <Text style={styles.subscriptionStatus}>Active</Text>
                </>
              ) : (
                <>
                  <Text style={styles.freeBadge}>Free Plan</Text>
                  <Text style={styles.subscriptionStatus}>
                    {dailyQueriesUsed}/{FREE_TIER_LIMITS.dailyQueries} queries used today
                  </Text>
                </>
              )}
            </View>

            {isPro ? (
              <TouchableOpacity style={styles.manageButton} onPress={handleManageSubscription}>
                <Text style={styles.manageButtonText}>Manage Subscription</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                style={styles.upgradeButton}
                onPress={() => navigation.navigate('Paywall')}
              >
                <Text style={styles.upgradeButtonText}>Upgrade to Pro</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Appearance */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.textTertiary }]}>Appearance</Text>

          <View style={[styles.themeCard, { backgroundColor: theme.backgroundSecondary }]}>
            <TouchableOpacity
              style={[
                styles.themeOption,
                mode === 'dark' && styles.themeOptionActive,
              ]}
              onPress={() => handleThemeChange('dark')}
            >
              <Ionicons
                name="moon"
                size={20}
                color={mode === 'dark' ? theme.primary : theme.textSecondary}
              />
              <Text
                style={[
                  styles.themeOptionText,
                  { color: mode === 'dark' ? theme.primary : theme.textSecondary },
                ]}
              >
                Dark
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.themeOption,
                mode === 'light' && styles.themeOptionActive,
              ]}
              onPress={() => handleThemeChange('light')}
            >
              <Ionicons
                name="sunny"
                size={20}
                color={mode === 'light' ? theme.primary : theme.textSecondary}
              />
              <Text
                style={[
                  styles.themeOptionText,
                  { color: mode === 'light' ? theme.primary : theme.textSecondary },
                ]}
              >
                Light
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.themeOption,
                mode === 'system' && styles.themeOptionActive,
              ]}
              onPress={() => handleThemeChange('system')}
            >
              <Ionicons
                name="phone-portrait"
                size={20}
                color={mode === 'system' ? theme.primary : theme.textSecondary}
              />
              <Text
                style={[
                  styles.themeOptionText,
                  { color: mode === 'system' ? theme.primary : theme.textSecondary },
                ]}
              >
                System
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Account */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.textTertiary }]}>Account</Text>

          <TouchableOpacity
            style={[styles.menuItem, { backgroundColor: theme.backgroundSecondary }]}
            onPress={handleRestorePurchases}
          >
            <View style={styles.menuItemLeft}>
              <Ionicons name="refresh" size={22} color={theme.textSecondary} />
              <Text style={[styles.menuItemText, { color: theme.text }]}>Restore Purchases</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={theme.textTertiary} />
          </TouchableOpacity>
        </View>

        {/* Legal */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.textTertiary }]}>Legal</Text>

          <TouchableOpacity
            style={[styles.menuItem, { backgroundColor: theme.backgroundSecondary }]}
            onPress={() => navigation.navigate('PrivacyPolicy')}
          >
            <View style={styles.menuItemLeft}>
              <Ionicons name="shield-checkmark-outline" size={22} color={theme.textSecondary} />
              <Text style={[styles.menuItemText, { color: theme.text }]}>Privacy Policy</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={theme.textTertiary} />
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.menuItem, { backgroundColor: theme.backgroundSecondary }]}
            onPress={() => navigation.navigate('TermsOfService')}
          >
            <View style={styles.menuItemLeft}>
              <Ionicons name="document-text-outline" size={22} color={theme.textSecondary} />
              <Text style={[styles.menuItemText, { color: theme.text }]}>Terms of Service</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={theme.textTertiary} />
          </TouchableOpacity>
        </View>

        {/* Support */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.textTertiary }]}>Support</Text>

          <TouchableOpacity
            style={[styles.menuItem, { backgroundColor: theme.backgroundSecondary }]}
            onPress={() => Linking.openURL('mailto:support@gamespace.app')}
          >
            <View style={styles.menuItemLeft}>
              <Ionicons name="mail-outline" size={22} color={theme.textSecondary} />
              <Text style={[styles.menuItemText, { color: theme.text }]}>Contact Support</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={theme.textTertiary} />
          </TouchableOpacity>
        </View>

        {/* App Info */}
        <View style={styles.appInfo}>
          <Text style={[styles.appName, { color: theme.textTertiary }]}>GameSpace</Text>
          <Text style={[styles.appVersion, { color: theme.textTertiary }]}>Version 1.0.0</Text>
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
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2e',
  },
  backButton: {
    padding: 8,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
  },
  placeholder: {
    width: 40,
  },
  scrollView: {
    flex: 1,
  },
  section: {
    paddingTop: 24,
    paddingHorizontal: 16,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  subscriptionCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
  },
  subscriptionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  proBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(251, 191, 36, 0.1)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    gap: 6,
  },
  proBadgeText: {
    fontSize: 14,
    color: '#fbbf24',
    fontWeight: '700',
  },
  freeBadge: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  subscriptionStatus: {
    fontSize: 14,
    color: '#9ca3af',
  },
  manageButton: {
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  manageButtonText: {
    color: '#6366f1',
    fontSize: 15,
    fontWeight: '600',
  },
  upgradeButton: {
    backgroundColor: '#6366f1',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  upgradeButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  themeCard: {
    flexDirection: 'row',
    borderRadius: 12,
    padding: 4,
  },
  themeOption: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderRadius: 8,
    gap: 6,
  },
  themeOptionActive: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
  },
  themeOptionText: {
    fontSize: 14,
    fontWeight: '500',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  menuItemLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  menuItemText: {
    fontSize: 16,
    color: '#fff',
  },
  appInfo: {
    alignItems: 'center',
    paddingVertical: 32,
  },
  appName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#6b7280',
    marginBottom: 4,
  },
  appVersion: {
    fontSize: 14,
    color: '#4b5563',
  },
});
