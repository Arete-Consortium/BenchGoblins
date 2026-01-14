import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { Sport } from '../types';
import { useAppStore } from '../stores/appStore';

const sports: { key: Sport; label: string; icon: string }[] = [
  { key: 'nba', label: 'NBA', icon: '🏀' },
  { key: 'nfl', label: 'NFL', icon: '🏈' },
  { key: 'mlb', label: 'MLB', icon: '⚾' },
  { key: 'nhl', label: 'NHL', icon: '🏒' },
];

export function SportSelector() {
  const { sport, setSport } = useAppStore();

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.container}>
      {sports.map((s) => (
        <TouchableOpacity
          key={s.key}
          style={[styles.chip, sport === s.key && styles.activeChip]}
          onPress={() => setSport(s.key)}
        >
          <Text style={styles.icon}>{s.icon}</Text>
          <Text style={[styles.label, sport === s.key && styles.activeLabel]}>{s.label}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#1a1a2e',
    marginRight: 8,
    gap: 6,
  },
  activeChip: {
    backgroundColor: '#4f46e5',
  },
  icon: {
    fontSize: 16,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#94a3b8',
  },
  activeLabel: {
    color: '#ffffff',
  },
});
