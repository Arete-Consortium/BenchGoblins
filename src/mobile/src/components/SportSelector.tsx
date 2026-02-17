import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Sport } from '../types';
import { useAppStore } from '../stores/appStore';

const sports: { key: Sport; label: string; icon: string }[] = [
  { key: 'nba', label: 'NBA', icon: '🏀' },
  { key: 'nfl', label: 'NFL', icon: '🏈' },
  { key: 'mlb', label: 'MLB', icon: '⚾' },
  { key: 'nhl', label: 'NHL', icon: '🏒' },
  { key: 'soccer', label: 'Soccer', icon: '⚽' },
];

interface SportSelectorProps {
  availableSports?: readonly Sport[];
}

export function SportSelector({ availableSports }: SportSelectorProps) {
  const { sport, setSport } = useAppStore();

  const isAvailable = (sportKey: Sport) => {
    if (!availableSports) return true;
    return availableSports.includes(sportKey);
  };

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.container}>
      {sports.map((s) => {
        const available = isAvailable(s.key);
        const isActive = sport === s.key;

        return (
          <TouchableOpacity
            key={s.key}
            style={[
              styles.chip,
              isActive && styles.activeChip,
              !available && styles.lockedChip,
            ]}
            onPress={() => available && setSport(s.key)}
            disabled={!available}
          >
            <Text style={styles.icon}>{s.icon}</Text>
            <Text style={[styles.label, isActive && styles.activeLabel]}>{s.label}</Text>
            {!available && (
              <Ionicons name="lock-closed" size={12} color="#6b7280" style={styles.lockIcon} />
            )}
          </TouchableOpacity>
        );
      })}
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
  lockedChip: {
    opacity: 0.5,
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
  lockIcon: {
    marginLeft: 2,
  },
});
