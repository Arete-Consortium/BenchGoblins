import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { RiskMode } from '../types';
import { useAppStore } from '../stores/appStore';

const modes: { key: RiskMode; label: string; description: string }[] = [
  { key: 'floor', label: 'FLOOR', description: 'Minimize downside' },
  { key: 'median', label: 'MEDIAN', description: 'Balanced approach' },
  { key: 'ceiling', label: 'CEILING', description: 'Maximize upside' },
];

export function RiskModeSelector() {
  const { riskMode, setRiskMode } = useAppStore();

  return (
    <View style={styles.container}>
      {modes.map((mode) => (
        <TouchableOpacity
          key={mode.key}
          style={[styles.button, riskMode === mode.key && styles.activeButton]}
          onPress={() => setRiskMode(mode.key)}
        >
          <Text style={[styles.label, riskMode === mode.key && styles.activeLabel]}>
            {mode.label}
          </Text>
          <Text style={[styles.description, riskMode === mode.key && styles.activeDescription]}>
            {mode.description}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    gap: 8,
    padding: 16,
  },
  button: {
    flex: 1,
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#1a1a2e',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  activeButton: {
    borderColor: '#4f46e5',
    backgroundColor: '#1e1b4b',
  },
  label: {
    fontSize: 14,
    fontWeight: '700',
    color: '#94a3b8',
  },
  activeLabel: {
    color: '#818cf8',
  },
  description: {
    fontSize: 10,
    color: '#64748b',
    marginTop: 4,
  },
  activeDescription: {
    color: '#a5b4fc',
  },
});
