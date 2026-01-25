import React, { useMemo, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAppStore } from '../stores/appStore';
import { useThemeStore } from '../stores/themeStore';
import { Message, DecisionResponse } from '../types';
import { hapticWarning } from '../utils/haptics';

interface DecisionHistoryItem {
  id: string;
  userQuery: string;
  decision: DecisionResponse;
  timestamp: Date;
}

interface PlayerDetail {
  name: string;
  score: number | string;
}

function getPlayerDetail(details: Record<string, unknown> | undefined, key: string): PlayerDetail | null {
  if (!details || !details[key]) return null;
  const player = details[key] as Record<string, unknown>;
  return {
    name: String(player.name || ''),
    score: String(player.score || ''),
  };
}

export function HistoryScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<any>>();
  const { messages, clearMessages } = useAppStore();
  const { theme } = useThemeStore();
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    // Simulate refresh - in future this could sync with backend
    setTimeout(() => {
      setRefreshing(false);
    }, 500);
  }, []);

  // Extract decisions from messages
  const decisions = useMemo(() => {
    const items: DecisionHistoryItem[] = [];

    for (let i = 0; i < messages.length; i++) {
      const message = messages[i];
      if (message.role === 'assistant' && message.decision) {
        // Find the preceding user message
        const userMessage = i > 0 ? messages[i - 1] : null;
        const userQuery = userMessage?.role === 'user' ? userMessage.content : 'Unknown query';

        items.push({
          id: message.id,
          userQuery,
          decision: message.decision,
          timestamp: message.timestamp,
        });
      }
    }

    // Return in reverse chronological order
    return items.reverse();
  }, [messages]);

  const formatDate = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - new Date(date).getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);

    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days}d ago`;

    return new Date(date).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  const getConfidenceColor = (confidence: string) => {
    switch (confidence) {
      case 'high':
        return '#22c55e';
      case 'medium':
        return '#fbbf24';
      case 'low':
        return '#ef4444';
      default:
        return '#9ca3af';
    }
  };

  const renderPlayerComparison = (details: Record<string, unknown> | undefined) => {
    const playerA = getPlayerDetail(details, 'player_a');
    const playerB = getPlayerDetail(details, 'player_b');

    if (!playerA || !playerB) return null;

    return (
      <View style={[styles.detailsRow, { borderTopColor: theme.borderLight }]}>
        <View style={styles.playerScore}>
          <Text style={[styles.playerName, { color: theme.textSecondary }]}>{playerA.name}</Text>
          <Text style={[styles.playerScoreValue, { color: theme.primaryLight }]}>{playerA.score}</Text>
        </View>
        <Text style={[styles.vsText, { color: theme.textTertiary }]}>vs</Text>
        <View style={styles.playerScore}>
          <Text style={[styles.playerName, { color: theme.textSecondary }]}>{playerB.name}</Text>
          <Text style={[styles.playerScoreValue, { color: theme.primaryLight }]}>{playerB.score}</Text>
        </View>
      </View>
    );
  };

  const renderItem = ({ item }: { item: DecisionHistoryItem }) => (
    <View style={[styles.card, { backgroundColor: theme.backgroundSecondary }]}>
      <View style={styles.cardHeader}>
        <View style={styles.cardHeaderLeft}>
          <View
            style={[
              styles.sourceIcon,
              item.decision.source === 'claude' ? styles.sourceIconClaude : styles.sourceIconLocal,
            ]}
          >
            <Ionicons
              name={item.decision.source === 'claude' ? 'sparkles' : 'flash'}
              size={14}
              color={item.decision.source === 'claude' ? '#a78bfa' : theme.primaryLight}
            />
          </View>
          <Text style={[styles.timestamp, { color: theme.textTertiary }]}>{formatDate(item.timestamp)}</Text>
        </View>
        <View
          style={[
            styles.confidenceBadge,
            { backgroundColor: `${getConfidenceColor(item.decision.confidence)}20` },
          ]}
        >
          <View
            style={[
              styles.confidenceDot,
              { backgroundColor: getConfidenceColor(item.decision.confidence) },
            ]}
          />
          <Text
            style={[
              styles.confidenceText,
              { color: getConfidenceColor(item.decision.confidence) },
            ]}
          >
            {item.decision.confidence}
          </Text>
        </View>
      </View>

      <Text style={[styles.userQuery, { color: theme.textSecondary }]} numberOfLines={2}>
        {item.userQuery}
      </Text>

      <View style={styles.decisionRow}>
        <Ionicons name="checkmark-circle" size={20} color={theme.success} />
        <Text style={[styles.decisionText, { color: theme.text }]}>{item.decision.decision}</Text>
      </View>

      <Text style={[styles.rationale, { color: theme.textSecondary }]} numberOfLines={3}>
        {item.decision.rationale}
      </Text>

      {renderPlayerComparison(item.decision.details)}
    </View>
  );

  const renderEmptyState = () => (
    <View style={styles.emptyContainer}>
      <Ionicons name="time-outline" size={64} color={theme.textTertiary} />
      <Text style={[styles.emptyTitle, { color: theme.text }]}>No decisions yet</Text>
      <Text style={[styles.emptySubtitle, { color: theme.textTertiary }]}>
        Your decision history will appear here after you ask GameSpace for advice
      </Text>
      <TouchableOpacity
        style={[styles.askButton, { backgroundColor: theme.primary }]}
        onPress={() => {
          // @ts-ignore - nested navigation
          navigation.navigate('Ask');
        }}
      >
        <Ionicons name="chatbubbles" size={20} color="#fff" />
        <Text style={styles.askButtonText}>Ask GameSpace</Text>
      </TouchableOpacity>
    </View>
  );

  const renderHeader = () => (
    <View style={[styles.header, { borderBottomColor: theme.border }]}>
      <View style={styles.headerTop}>
        <Text style={[styles.headerTitle, { color: theme.text }]}>Decision History</Text>
        <TouchableOpacity
          style={styles.settingsButton}
          onPress={() => navigation.navigate('Settings')}
        >
          <Ionicons name="settings-outline" size={24} color={theme.textSecondary} />
        </TouchableOpacity>
      </View>
      {decisions.length > 0 && (
        <View style={[styles.statsRow, { backgroundColor: theme.backgroundSecondary }]}>
          <View style={styles.statItem}>
            <Text style={[styles.statValue, { color: theme.primaryLight }]}>{decisions.length}</Text>
            <Text style={[styles.statLabel, { color: theme.textTertiary }]}>Decisions</Text>
          </View>
          <View style={[styles.statDivider, { backgroundColor: theme.borderLight }]} />
          <View style={styles.statItem}>
            <Text style={[styles.statValue, { color: theme.primaryLight }]}>
              {decisions.filter((d) => d.decision.source === 'local').length}
            </Text>
            <Text style={[styles.statLabel, { color: theme.textTertiary }]}>Local</Text>
          </View>
          <View style={[styles.statDivider, { backgroundColor: theme.borderLight }]} />
          <View style={styles.statItem}>
            <Text style={[styles.statValue, { color: theme.primaryLight }]}>
              {decisions.filter((d) => d.decision.source === 'claude').length}
            </Text>
            <Text style={[styles.statLabel, { color: theme.textTertiary }]}>Claude</Text>
          </View>
          <View style={[styles.statDivider, { backgroundColor: theme.borderLight }]} />
          <View style={styles.statItem}>
            <Text style={[styles.statValue, { color: theme.primaryLight }]}>
              {decisions.filter((d) => d.decision.confidence === 'high').length}
            </Text>
            <Text style={[styles.statLabel, { color: theme.textTertiary }]}>High Conf.</Text>
          </View>
        </View>
      )}
    </View>
  );

  const renderFooter = () => {
    if (decisions.length === 0) return null;

    return (
      <TouchableOpacity style={styles.clearButton} onPress={() => { hapticWarning(); clearMessages(); }}>
        <Ionicons name="trash-outline" size={18} color="#ef4444" />
        <Text style={styles.clearButtonText}>Clear History</Text>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]} edges={['top']}>
      {renderHeader()}
      <FlatList
        data={decisions}
        renderItem={renderItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={renderEmptyState}
        ListFooterComponent={renderFooter}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={theme.primaryLight}
            colors={[theme.primaryLight]}
          />
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  header: {
    paddingHorizontal: 20,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2e',
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#fff',
  },
  settingsButton: {
    padding: 8,
  },
  statsRow: {
    flexDirection: 'row',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 20,
    fontWeight: '700',
    color: '#818cf8',
  },
  statLabel: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 4,
  },
  statDivider: {
    width: 1,
    backgroundColor: '#2d2d44',
  },
  listContent: {
    padding: 20,
    paddingBottom: 40,
    flexGrow: 1,
  },
  card: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  cardHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  sourceIcon: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sourceIconLocal: {
    backgroundColor: 'rgba(129, 140, 248, 0.2)',
  },
  sourceIconClaude: {
    backgroundColor: 'rgba(167, 139, 250, 0.2)',
  },
  timestamp: {
    fontSize: 13,
    color: '#64748b',
  },
  confidenceBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 6,
  },
  confidenceDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  confidenceText: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  userQuery: {
    fontSize: 14,
    color: '#9ca3af',
    marginBottom: 12,
    fontStyle: 'italic',
  },
  decisionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  decisionText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    flex: 1,
  },
  rationale: {
    fontSize: 14,
    color: '#9ca3af',
    lineHeight: 20,
  },
  detailsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
    gap: 16,
  },
  playerScore: {
    alignItems: 'center',
  },
  playerName: {
    fontSize: 13,
    color: '#9ca3af',
    marginBottom: 2,
  },
  playerScoreValue: {
    fontSize: 18,
    fontWeight: '700',
    color: '#818cf8',
  },
  vsText: {
    fontSize: 12,
    color: '#64748b',
    fontWeight: '500',
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#fff',
    marginTop: 16,
  },
  emptySubtitle: {
    fontSize: 14,
    color: '#64748b',
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 20,
  },
  askButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#6366f1',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 24,
    marginTop: 24,
    gap: 8,
  },
  askButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  clearButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    gap: 8,
  },
  clearButtonText: {
    fontSize: 14,
    color: '#ef4444',
    fontWeight: '500',
  },
});
