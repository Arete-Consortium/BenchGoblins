import React from 'react';
import { View, FlatList, StyleSheet, Text, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAppStore } from '../stores/appStore';
import { useSubscriptionStore, getAvailableSports } from '../stores/subscriptionStore';
import { useThemeStore } from '../stores/themeStore';
import { RiskModeSelector, SportSelector, MessageBubble, ChatInput, SkeletonMessage } from '../components';
import { Message } from '../types';
import { FREE_TIER_LIMITS } from '../services/purchases';

export function ChatScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<any>>();
  const { messages, isLoading, lastError, retryLastMessage } = useAppStore();
  const { isPro, getRemainingQueries, dailyQueriesUsed } = useSubscriptionStore();
  const { theme } = useThemeStore();

  const remainingQueries = getRemainingQueries();
  const availableSports = getAvailableSports(isPro);

  const renderMessage = ({ item }: { item: Message }) => <MessageBubble message={item} />;

  const renderLoadingSkeleton = () => {
    if (!isLoading) return null;
    return (
      <View style={styles.skeletonContainer}>
        <SkeletonMessage />
      </View>
    );
  };

  const renderRetryBanner = () => {
    if (!lastError?.retryable || isLoading) return null;
    return (
      <View style={[styles.retryBanner, { backgroundColor: 'rgba(239, 68, 68, 0.1)', borderColor: '#ef4444' }]}>
        <View style={styles.retryContent}>
          <Ionicons name="warning-outline" size={18} color="#ef4444" />
          <Text style={[styles.retryText, { color: theme.textSecondary }]}>
            {lastError.message}
          </Text>
        </View>
        <TouchableOpacity
          style={styles.retryButton}
          onPress={retryLastMessage}
        >
          <Ionicons name="refresh" size={16} color={theme.primaryLight} />
          <Text style={[styles.retryButtonText, { color: theme.primaryLight }]}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  };

  const renderEmptyState = () => (
    <View style={styles.emptyContainer}>
      <Text style={[styles.emptyTitle, { color: theme.primaryLight }]}>BenchGoblins</Text>
      <Text style={[styles.emptySubtitle, { color: theme.textTertiary }]}>Fantasy sports decision engine</Text>
      <View style={styles.examplesContainer}>
        <Text style={[styles.examplesHeader, { color: theme.textSecondary }]}>Try asking:</Text>
        <Text style={[styles.example, { color: theme.textTertiary }]}>"Should I start Jalen Brunson or Tyrese Maxey?"</Text>
        <Text style={[styles.example, { color: theme.textTertiary }]}>"Is Shai Gilgeous-Alexander a good ceiling play?"</Text>
        <Text style={[styles.example, { color: theme.textTertiary }]}>"Who should I start at flex: Puka or Deebo?"</Text>
      </View>
    </View>
  );

  const renderHeader = () => (
    <View style={[styles.header, { borderBottomColor: theme.border }]}>
      <View style={styles.headerTop}>
        <View style={styles.headerLeft}>
          {!isPro && (
            <View style={styles.queriesContainer}>
              <Text style={[styles.queriesText, { color: theme.primaryLight }]}>
                {remainingQueries}/{FREE_TIER_LIMITS.dailyQueries} queries left
              </Text>
            </View>
          )}
          {isPro && (
            <View style={styles.proBadge}>
              <Ionicons name="star" size={12} color={theme.warning} />
              <Text style={[styles.proBadgeText, { color: theme.warning }]}>PRO</Text>
            </View>
          )}
        </View>
        <TouchableOpacity
          style={styles.settingsButton}
          onPress={() => navigation.navigate('Settings')}
        >
          <Ionicons name="settings-outline" size={24} color={theme.textSecondary} />
        </TouchableOpacity>
      </View>
      <SportSelector availableSports={availableSports} />
      <RiskModeSelector />
    </View>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]} edges={['top']}>
      {renderHeader()}

      {!isPro && remainingQueries === 0 && (
        <TouchableOpacity
          style={[styles.upgradePrompt, { backgroundColor: theme.backgroundSecondary, borderColor: theme.primary }]}
          onPress={() => navigation.navigate('Paywall')}
        >
          <View style={styles.upgradeContent}>
            <Ionicons name="lock-closed" size={20} color={theme.warning} />
            <View style={styles.upgradeTextContainer}>
              <Text style={[styles.upgradeTitle, { color: theme.text }]}>Daily limit reached</Text>
              <Text style={[styles.upgradeSubtitle, { color: theme.textSecondary }]}>Upgrade to Pro for unlimited queries</Text>
            </View>
          </View>
          <Ionicons name="chevron-forward" size={24} color={theme.primary} />
        </TouchableOpacity>
      )}

      {renderRetryBanner()}

      <FlatList
        data={messages}
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.messageList}
        ListEmptyComponent={renderEmptyState}
        ListHeaderComponent={renderLoadingSkeleton}
        inverted={messages.length > 0}
      />

      <ChatInput disabled={!isPro && remainingQueries === 0} />

      {!isPro && remainingQueries > 0 && (
        <TouchableOpacity
          style={[styles.upgradeButton, { borderColor: theme.primary }]}
          onPress={() => navigation.navigate('Paywall')}
        >
          <Text style={[styles.upgradeButtonText, { color: theme.primary }]}>Upgrade to Pro</Text>
        </TouchableOpacity>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  header: {
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2e',
  },
  headerTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  queriesContainer: {
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  queriesText: {
    fontSize: 13,
    color: '#818cf8',
    fontWeight: '500',
  },
  proBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(251, 191, 36, 0.1)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 4,
  },
  proBadgeText: {
    fontSize: 12,
    color: '#fbbf24',
    fontWeight: '700',
  },
  settingsButton: {
    padding: 8,
  },
  retryBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: 16,
    marginTop: 8,
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
  },
  retryContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  retryText: {
    fontSize: 13,
    flex: 1,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
  },
  retryButtonText: {
    fontSize: 13,
    fontWeight: '600',
  },
  upgradePrompt: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1a1a2e',
    marginHorizontal: 16,
    marginTop: 12,
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
  upgradeTextContainer: {
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
  messageList: {
    flexGrow: 1,
    paddingVertical: 12,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    transform: [{ scaleY: -1 }],
  },
  emptyTitle: {
    fontSize: 32,
    fontWeight: '700',
    color: '#818cf8',
    marginBottom: 8,
  },
  emptySubtitle: {
    fontSize: 16,
    color: '#64748b',
    marginBottom: 32,
  },
  examplesContainer: {
    alignItems: 'flex-start',
    width: '100%',
  },
  examplesHeader: {
    fontSize: 14,
    color: '#94a3b8',
    marginBottom: 12,
  },
  example: {
    fontSize: 14,
    color: '#64748b',
    marginBottom: 8,
    fontStyle: 'italic',
  },
  upgradeButton: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#6366f1',
    marginHorizontal: 16,
    marginBottom: 8,
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  upgradeButtonText: {
    color: '#6366f1',
    fontSize: 14,
    fontWeight: '600',
  },
  skeletonContainer: {
    transform: [{ scaleY: -1 }],
  },
});
