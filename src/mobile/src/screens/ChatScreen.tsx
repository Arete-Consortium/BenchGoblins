import React from 'react';
import { View, FlatList, StyleSheet, Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAppStore } from '../stores/appStore';
import { RiskModeSelector, SportSelector, MessageBubble, ChatInput } from '../components';
import { Message } from '../types';

export function ChatScreen() {
  const { messages } = useAppStore();

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

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <SportSelector />
        <RiskModeSelector />
      </View>

      <FlatList
        data={messages}
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.messageList}
        ListEmptyComponent={renderEmptyState}
        inverted={messages.length > 0}
      />

      <ChatInput />
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
});
