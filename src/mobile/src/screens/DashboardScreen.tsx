import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAppStore } from '../stores/appStore';
import { useSubscriptionStore } from '../stores/subscriptionStore';
import { FREE_TIER_LIMITS } from '../services/purchases';
import { Message } from '../types';

type QuickAction = {
  id: string;
  title: string;
  subtitle: string;
  icon: keyof typeof Ionicons.glyphMap;
  query: string;
};

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: 'start-sit',
    title: 'Start/Sit',
    subtitle: 'Compare two players',
    icon: 'swap-horizontal',
    query: 'Should I start ',
  },
  {
    id: 'ceiling',
    title: 'Ceiling Play',
    subtitle: 'Max upside pick',
    icon: 'trending-up',
    query: 'Who has the highest ceiling this week: ',
  },
  {
    id: 'floor',
    title: 'Safe Floor',
    subtitle: 'Reliable starter',
    icon: 'shield-checkmark',
    query: 'Who has the safest floor: ',
  },
  {
    id: 'matchup',
    title: 'Matchup Check',
    subtitle: 'Analyze opponent',
    icon: 'analytics',
    query: 'How does the matchup look for ',
  },
];

export function DashboardScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<any>>();
  const { messages, sport, riskMode } = useAppStore();
  const { isPro, getRemainingQueries } = useSubscriptionStore();

  const remainingQueries = getRemainingQueries();

  // Get recent decisions (last 5)
  const recentDecisions = messages
    .filter((m: Message) => m.role === 'assistant' && m.decision)
    .slice(-5)
    .reverse();

  const handleQuickAction = (action: QuickAction) => {
    // Navigate to Ask tab
    // @ts-ignore - nested navigation
    navigation.navigate('Ask');
  };

  const sportLabels: Record<string, string> = {
    nba: 'NBA',
    nfl: 'NFL',
    mlb: 'MLB',
    nhl: 'NHL',
  };

  const riskLabels: Record<string, string> = {
    floor: 'Floor',
    median: 'Median',
    ceiling: 'Ceiling',
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>GameSpace</Text>
            <Text style={styles.subtitle}>Fantasy decision engine</Text>
          </View>
          <TouchableOpacity
            style={styles.settingsButton}
            onPress={() => navigation.navigate('Settings')}
          >
            <Ionicons name="settings-outline" size={24} color="#9ca3af" />
          </TouchableOpacity>
        </View>

        {/* Status Bar */}
        <View style={styles.statusBar}>
          <View style={styles.statusItem}>
            <Text style={styles.statusLabel}>Sport</Text>
            <Text style={styles.statusValue}>{sportLabels[sport]}</Text>
          </View>
          <View style={styles.statusDivider} />
          <View style={styles.statusItem}>
            <Text style={styles.statusLabel}>Mode</Text>
            <Text style={styles.statusValue}>{riskLabels[riskMode]}</Text>
          </View>
          <View style={styles.statusDivider} />
          <View style={styles.statusItem}>
            <Text style={styles.statusLabel}>Queries</Text>
            <Text style={styles.statusValue}>
              {isPro ? 'Unlimited' : `${remainingQueries}/${FREE_TIER_LIMITS.dailyQueries}`}
            </Text>
          </View>
        </View>

        {/* Pro Upgrade Banner (for free users) */}
        {!isPro && (
          <TouchableOpacity
            style={styles.upgradeBanner}
            onPress={() => navigation.navigate('Paywall')}
          >
            <View style={styles.upgradeContent}>
              <Ionicons name="star" size={24} color="#fbbf24" />
              <View style={styles.upgradeText}>
                <Text style={styles.upgradeTitle}>Upgrade to Pro</Text>
                <Text style={styles.upgradeSubtitle}>
                  Unlimited queries + all sports
                </Text>
              </View>
            </View>
            <Ionicons name="chevron-forward" size={24} color="#6366f1" />
          </TouchableOpacity>
        )}

        {/* Quick Actions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Quick Actions</Text>
          <View style={styles.actionsGrid}>
            {QUICK_ACTIONS.map((action) => (
              <TouchableOpacity
                key={action.id}
                style={styles.actionCard}
                onPress={() => handleQuickAction(action)}
              >
                <View style={styles.actionIcon}>
                  <Ionicons name={action.icon} size={24} color="#818cf8" />
                </View>
                <Text style={styles.actionTitle}>{action.title}</Text>
                <Text style={styles.actionSubtitle}>{action.subtitle}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Recent Decisions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Recent Decisions</Text>
          {recentDecisions.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="chatbubbles-outline" size={48} color="#4b5563" />
              <Text style={styles.emptyText}>No decisions yet</Text>
              <Text style={styles.emptySubtext}>
                Ask GameSpace for your first recommendation
              </Text>
            </View>
          ) : (
            <View style={styles.decisionsList}>
              {recentDecisions.map((message: Message) => (
                <View key={message.id} style={styles.decisionCard}>
                  <View style={styles.decisionHeader}>
                    <Text style={styles.decisionText}>
                      {message.decision?.decision}
                    </Text>
                    <View
                      style={[
                        styles.confidenceBadge,
                        message.decision?.confidence === 'high' && styles.confidenceHigh,
                        message.decision?.confidence === 'medium' && styles.confidenceMedium,
                        message.decision?.confidence === 'low' && styles.confidenceLow,
                      ]}
                    >
                      <Text style={styles.confidenceText}>
                        {message.decision?.confidence}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.decisionRationale} numberOfLines={2}>
                    {message.decision?.rationale}
                  </Text>
                  <Text style={styles.decisionSource}>
                    via {message.decision?.source}
                  </Text>
                </View>
              ))}
            </View>
          )}
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  greeting: {
    fontSize: 28,
    fontWeight: '700',
    color: '#818cf8',
  },
  subtitle: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 2,
  },
  settingsButton: {
    padding: 8,
  },
  statusBar: {
    flexDirection: 'row',
    backgroundColor: '#1a1a2e',
    marginHorizontal: 20,
    borderRadius: 12,
    padding: 16,
  },
  statusItem: {
    flex: 1,
    alignItems: 'center',
  },
  statusLabel: {
    fontSize: 12,
    color: '#64748b',
    marginBottom: 4,
  },
  statusValue: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  statusDivider: {
    width: 1,
    backgroundColor: '#2d2d44',
  },
  upgradeBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    marginHorizontal: 20,
    marginTop: 16,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#6366f1',
  },
  upgradeContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  upgradeText: {
    gap: 2,
  },
  upgradeTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  upgradeSubtitle: {
    fontSize: 13,
    color: '#9ca3af',
  },
  section: {
    marginTop: 24,
    paddingHorizontal: 20,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
  },
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  actionCard: {
    width: '47%',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
  },
  actionIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(129, 140, 248, 0.1)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  actionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 4,
  },
  actionSubtitle: {
    fontSize: 13,
    color: '#64748b',
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 32,
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
  },
  emptyText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#9ca3af',
    marginTop: 12,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 4,
  },
  decisionsList: {
    gap: 12,
  },
  decisionCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
  },
  decisionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  decisionText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    flex: 1,
  },
  confidenceBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  confidenceHigh: {
    backgroundColor: 'rgba(34, 197, 94, 0.2)',
  },
  confidenceMedium: {
    backgroundColor: 'rgba(251, 191, 36, 0.2)',
  },
  confidenceLow: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
  },
  confidenceText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#fff',
    textTransform: 'capitalize',
  },
  decisionRationale: {
    fontSize: 14,
    color: '#9ca3af',
    lineHeight: 20,
  },
  decisionSource: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 8,
  },
});
