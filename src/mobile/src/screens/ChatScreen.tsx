import React from 'react';
import { View, FlatList, StyleSheet, Text, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAppStore } from '../stores/appStore';
import { useSubscriptionStore, getAvailableSports } from '../stores/subscriptionStore';
import { RiskModeSelector, SportSelector, MessageBubble, ChatInput } from '../components';
import { Message } from '../types';
import { FREE_TIER_LIMITS } from '../services/purchases';

export function ChatScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<any>>();
  const { messages } = useAppStore();
  const { isPro, getRemainingQueries, dailyQueriesUsed } = useSubscriptionStore();

  const remainingQueries = getRemainingQueries();
  const availableSports = getAvailableSports(isPro);

  const renderMessage = ({ item }: { item: Message }) => <MessageBubble message={item} />;

  const renderEmptyState = () => (
    <View style={styles.emptyContainer}>
      <Text style={styles.emptyTitle}>GameSpace</Text>
      <Text style={styles.emptySubtitle}>Fantasy sports decision engine</Text>
      <View style={styles.examplesContainer}>
        <Text style={styles.examplesHeader}>Try asking:</Text>
        <Text style={styles.example}>"Should I start Jalen Brunson or Tyrese Maxey?"</Text>
        <Text style={styles.example}>"Is Shai Gilgeous-Alexander a good ceiling play?"</Text>
        <Text style={styles.example}>"Who should I start at flex: Puka or Deebo?"</Text>
      </View>
    </View>
  );

  const renderHeader = () => (
    <View style={styles.header}>
      <View style={styles.headerTop}>
        <View style={styles.headerLeft}>
          {!isPro && (
            <View style={styles.queriesContainer}>
              <Text style={styles.queriesText}>
                {remainingQueries}/{FREE_TIER_LIMITS.dailyQueries} queries left
              </Text>
            </View>
          )}
          {isPro && (
            <View style={styles.proBadge}>
              <Ionicons name="star" size={12} color="#fbbf24" />
              <Text style={styles.proBadgeText}>PRO</Text>
            </View>
          )}
        </View>
        <TouchableOpacity
          style={styles.settingsButton}
          onPress={() => navigation.navigate('Settings')}
        >
          <Ionicons name="settings-outline" size={24} color="#9ca3af" />
        </TouchableOpacity>
      </View>
      <SportSelector availableSports={availableSports} />
      <RiskModeSelector />
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {renderHeader()}

      {!isPro && remainingQueries === 0 && (
        <TouchableOpacity
          style={styles.upgradePrompt}
          onPress={() => navigation.navigate('Paywall')}
        >
          <View style={styles.upgradeContent}>
            <Ionicons name="lock-closed" size={20} color="#fbbf24" />
            <View style={styles.upgradeTextContainer}>
              <Text style={styles.upgradeTitle}>Daily limit reached</Text>
              <Text style={styles.upgradeSubtitle}>Upgrade to Pro for unlimited queries</Text>
            </View>
          </View>
          <Ionicons name="chevron-forward" size={24} color="#6366f1" />
        </TouchableOpacity>
      )}

      <FlatList
        data={messages}
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.messageList}
        ListEmptyComponent={renderEmptyState}
        inverted={messages.length > 0}
      />

      <ChatInput disabled={!isPro && remainingQueries === 0} />

      {!isPro && remainingQueries > 0 && (
        <TouchableOpacity
          style={styles.upgradeButton}
          onPress={() => navigation.navigate('Paywall')}
        >
          <Text style={styles.upgradeButtonText}>Upgrade to Pro</Text>
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
});
