import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAppStore } from '../stores/appStore';
import { useRosterStore } from '../stores/rosterStore';
import { searchPlayers } from '../services/api';
import { Player } from '../types';
import { hapticSuccess, hapticWarning } from '../utils/haptics';

export function RosterScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<any>>();
  const { sport } = useAppStore();
  const { roster, addPlayer, removePlayer } = useRosterStore();

  const [isSearching, setIsSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Player[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const sportRoster = roster[sport] || [];

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    // Simulate refresh - in future this could sync with league API
    setTimeout(() => {
      setRefreshing(false);
    }, 500);
  }, []);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setIsLoading(true);
    try {
      const results = await searchPlayers(searchQuery, sport, 10);
      setSearchResults(results);
    } catch (error) {
      Alert.alert('Error', 'Failed to search players. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddPlayer = (player: Player) => {
    hapticSuccess();
    addPlayer(sport, player);
    setSearchResults([]);
    setSearchQuery('');
    setIsSearching(false);
  };

  const handleRemovePlayer = (playerId: string) => {
    Alert.alert(
      'Remove Player',
      'Are you sure you want to remove this player from your roster?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: () => {
            hapticWarning();
            removePlayer(sport, playerId);
          },
        },
      ]
    );
  };

  const sportLabels: Record<string, string> = {
    nba: 'NBA',
    nfl: 'NFL',
    mlb: 'MLB',
    nhl: 'NHL',
  };

  const renderPlayer = ({ item }: { item: Player }) => (
    <View style={styles.playerCard}>
      <View style={styles.playerInfo}>
        <Text style={styles.playerName}>{item.name}</Text>
        <View style={styles.playerMeta}>
          <Text style={styles.playerTeam}>{item.team}</Text>
          <Text style={styles.playerPosition}>{item.position}</Text>
        </View>
      </View>
      <TouchableOpacity
        style={styles.removeButton}
        onPress={() => handleRemovePlayer(item.id)}
      >
        <Ionicons name="close-circle" size={24} color="#ef4444" />
      </TouchableOpacity>
    </View>
  );

  const renderSearchResult = ({ item }: { item: Player }) => {
    const isOnRoster = sportRoster.some((p) => p.id === item.id);

    return (
      <TouchableOpacity
        style={[styles.searchResultCard, isOnRoster && styles.searchResultDisabled]}
        onPress={() => !isOnRoster && handleAddPlayer(item)}
        disabled={isOnRoster}
      >
        <View style={styles.playerInfo}>
          <Text style={styles.playerName}>{item.name}</Text>
          <View style={styles.playerMeta}>
            <Text style={styles.playerTeam}>{item.team}</Text>
            <Text style={styles.playerPosition}>{item.position}</Text>
          </View>
        </View>
        {isOnRoster ? (
          <View style={styles.onRosterBadge}>
            <Text style={styles.onRosterText}>On Roster</Text>
          </View>
        ) : (
          <Ionicons name="add-circle" size={24} color="#22c55e" />
        )}
      </TouchableOpacity>
    );
  };

  const renderEmptyRoster = () => (
    <View style={styles.emptyContainer}>
      <Ionicons name="people-outline" size={64} color="#4b5563" />
      <Text style={styles.emptyTitle}>No players yet</Text>
      <Text style={styles.emptySubtitle}>
        Add players to your {sportLabels[sport]} roster to get quick comparisons
      </Text>
      <TouchableOpacity
        style={styles.addButton}
        onPress={() => setIsSearching(true)}
      >
        <Ionicons name="add" size={20} color="#fff" />
        <Text style={styles.addButtonText}>Add Players</Text>
      </TouchableOpacity>
    </View>
  );

  const renderHeader = () => (
    <View style={styles.header}>
      <View style={styles.headerTop}>
        <View>
          <Text style={styles.headerTitle}>My Roster</Text>
          <Text style={styles.headerSubtitle}>{sportLabels[sport]}</Text>
        </View>
        <View style={styles.headerActions}>
          {sportRoster.length > 0 && (
            <TouchableOpacity
              style={styles.addIconButton}
              onPress={() => setIsSearching(true)}
            >
              <Ionicons name="person-add" size={22} color="#818cf8" />
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={styles.settingsButton}
            onPress={() => navigation.navigate('Settings')}
          >
            <Ionicons name="settings-outline" size={24} color="#9ca3af" />
          </TouchableOpacity>
        </View>
      </View>
      {sportRoster.length > 0 && (
        <View style={styles.statsBar}>
          <Text style={styles.statsText}>
            {sportRoster.length} player{sportRoster.length !== 1 ? 's' : ''}
          </Text>
        </View>
      )}
    </View>
  );

  // Search mode view
  if (isSearching) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.searchHeader}>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => {
              setIsSearching(false);
              setSearchQuery('');
              setSearchResults([]);
            }}
          >
            <Ionicons name="arrow-back" size={24} color="#fff" />
          </TouchableOpacity>
          <View style={styles.searchInputContainer}>
            <Ionicons name="search" size={20} color="#64748b" />
            <TextInput
              style={styles.searchInput}
              placeholder={`Search ${sportLabels[sport]} players...`}
              placeholderTextColor="#64748b"
              value={searchQuery}
              onChangeText={setSearchQuery}
              onSubmitEditing={handleSearch}
              autoFocus
              returnKeyType="search"
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity onPress={() => setSearchQuery('')}>
                <Ionicons name="close-circle" size={20} color="#64748b" />
              </TouchableOpacity>
            )}
          </View>
        </View>

        {isLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#818cf8" />
            <Text style={styles.loadingText}>Searching...</Text>
          </View>
        ) : (
          <FlatList
            data={searchResults}
            renderItem={renderSearchResult}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.searchResultsList}
            ListEmptyComponent={
              searchQuery.length > 0 ? (
                <View style={styles.noResultsContainer}>
                  <Text style={styles.noResultsText}>
                    {searchResults.length === 0 && !isLoading
                      ? 'No players found. Try a different search.'
                      : 'Type to search for players'}
                  </Text>
                </View>
              ) : null
            }
          />
        )}
      </SafeAreaView>
    );
  }

  // Main roster view
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {renderHeader()}
      <FlatList
        data={sportRoster}
        renderItem={renderPlayer}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={renderEmptyRoster}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor="#818cf8"
            colors={['#818cf8']}
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
  headerSubtitle: {
    fontSize: 14,
    color: '#818cf8',
    marginTop: 2,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  addIconButton: {
    padding: 8,
    backgroundColor: 'rgba(129, 140, 248, 0.1)',
    borderRadius: 20,
  },
  settingsButton: {
    padding: 8,
  },
  statsBar: {
    backgroundColor: '#1a1a2e',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  statsText: {
    fontSize: 14,
    color: '#9ca3af',
  },
  listContent: {
    padding: 20,
    paddingBottom: 40,
    flexGrow: 1,
  },
  playerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  playerInfo: {
    flex: 1,
  },
  playerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  playerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
    gap: 8,
  },
  playerTeam: {
    fontSize: 13,
    color: '#9ca3af',
  },
  playerPosition: {
    fontSize: 13,
    color: '#818cf8',
    fontWeight: '500',
  },
  removeButton: {
    padding: 4,
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
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#6366f1',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 24,
    marginTop: 24,
    gap: 8,
  },
  addButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  // Search mode styles
  searchHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2e',
    gap: 12,
  },
  backButton: {
    padding: 4,
  },
  searchInputContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    paddingHorizontal: 12,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 16,
    color: '#fff',
    paddingVertical: 12,
  },
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  loadingText: {
    fontSize: 14,
    color: '#9ca3af',
  },
  searchResultsList: {
    padding: 16,
    flexGrow: 1,
  },
  searchResultCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  searchResultDisabled: {
    opacity: 0.6,
  },
  onRosterBadge: {
    backgroundColor: 'rgba(129, 140, 248, 0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
  },
  onRosterText: {
    fontSize: 12,
    color: '#818cf8',
    fontWeight: '500',
  },
  noResultsContainer: {
    alignItems: 'center',
    paddingVertical: 32,
  },
  noResultsText: {
    fontSize: 14,
    color: '#64748b',
  },
});
