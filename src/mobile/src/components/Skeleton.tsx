import React, { useEffect, useRef } from 'react';
import { View, Animated, StyleSheet, ViewStyle } from 'react-native';

interface SkeletonProps {
  width?: number | `${number}%` | 'auto';
  height?: number;
  borderRadius?: number;
  style?: ViewStyle;
}

export function Skeleton({
  width = '100%' as const,
  height = 20,
  borderRadius = 8,
  style,
}: SkeletonProps) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 0.7,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.3,
          duration: 800,
          useNativeDriver: true,
        }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        styles.skeleton,
        {
          width,
          height,
          borderRadius,
          opacity,
        },
        style,
      ]}
    />
  );
}

// Pre-built skeleton layouts for common patterns
export function SkeletonCard() {
  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Skeleton width={40} height={40} borderRadius={20} />
        <View style={styles.cardHeaderText}>
          <Skeleton width={120} height={16} />
          <Skeleton width={80} height={12} style={{ marginTop: 6 }} />
        </View>
      </View>
      <Skeleton width="100%" height={14} style={{ marginTop: 12 }} />
      <Skeleton width="80%" height={14} style={{ marginTop: 8 }} />
    </View>
  );
}

export function SkeletonPlayerCard() {
  return (
    <View style={styles.playerCard}>
      <View style={styles.playerInfo}>
        <Skeleton width={150} height={18} />
        <View style={styles.playerMeta}>
          <Skeleton width={60} height={14} style={{ marginTop: 6 }} />
          <Skeleton width={40} height={14} style={{ marginTop: 6, marginLeft: 8 }} />
        </View>
      </View>
      <Skeleton width={24} height={24} borderRadius={12} />
    </View>
  );
}

export function SkeletonDecisionCard() {
  return (
    <View style={styles.decisionCard}>
      <View style={styles.decisionHeader}>
        <View style={styles.decisionHeaderLeft}>
          <Skeleton width={24} height={24} borderRadius={12} />
          <Skeleton width={60} height={12} style={{ marginLeft: 8 }} />
        </View>
        <Skeleton width={60} height={20} borderRadius={10} />
      </View>
      <Skeleton width="90%" height={14} style={{ marginTop: 12 }} />
      <View style={styles.decisionRow}>
        <Skeleton width={20} height={20} borderRadius={10} />
        <Skeleton width={180} height={16} style={{ marginLeft: 8 }} />
      </View>
      <Skeleton width="100%" height={14} style={{ marginTop: 8 }} />
      <Skeleton width="70%" height={14} style={{ marginTop: 6 }} />
    </View>
  );
}

export function SkeletonMessage() {
  return (
    <View style={styles.messageContainer}>
      <View style={styles.messageBubble}>
        <Skeleton width="100%" height={16} />
        <Skeleton width="85%" height={16} style={{ marginTop: 8 }} />
        <Skeleton width="60%" height={16} style={{ marginTop: 8 }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  skeleton: {
    backgroundColor: '#2d2d44',
  },
  card: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  cardHeaderText: {
    marginLeft: 12,
    flex: 1,
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
  playerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  decisionCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  decisionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  decisionHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  decisionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 12,
  },
  messageContainer: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  messageBubble: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    maxWidth: '85%',
  },
});
