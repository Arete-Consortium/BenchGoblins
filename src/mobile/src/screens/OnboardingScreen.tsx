import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  Dimensions,
  ViewToken,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';

const { width } = Dimensions.get('window');

const ONBOARDING_KEY = 'benchgoblins_onboarding_complete';

interface OnboardingSlide {
  id: string;
  icon: keyof typeof Ionicons.glyphMap;
  iconColor: string;
  title: string;
  subtitle: string;
  bullets: string[];
}

const SLIDES: OnboardingSlide[] = [
  {
    id: 'welcome',
    icon: 'analytics',
    iconColor: '#818cf8',
    title: 'Welcome to BenchGoblins',
    subtitle: 'Fantasy sports decisions, powered by data',
    bullets: [
      'AI-powered start/sit, trade, and draft advice',
      'Real player stats from ESPN, Yahoo, and Sleeper',
      'Works for NBA, NFL, MLB, NHL, and Soccer',
    ],
  },
  {
    id: 'indices',
    icon: 'bar-chart',
    iconColor: '#22c55e',
    title: 'Five-Index Scoring',
    subtitle: 'Every recommendation is backed by 5 proprietary indices',
    bullets: [
      'SCI — Space Creation: how players generate usable space',
      'GIS — Gravity Impact: defensive attention drawn',
      'OD — Opportunity Delta: trending role changes',
      'MSF — Matchup Space Fit: opponent defensibility',
      'RMI — Role Motion: scheme dependency',
    ],
  },
  {
    id: 'modes',
    icon: 'speedometer',
    iconColor: '#fbbf24',
    title: 'Risk Modes',
    subtitle: 'Tailor recommendations to your strategy',
    bullets: [
      'Floor — Minimize downside, prioritize safe starters',
      'Median — Maximize expected value (default)',
      'Ceiling — Chase upside, accept higher variance',
    ],
  },
  {
    id: 'tiers',
    icon: 'star',
    iconColor: '#f97316',
    title: 'Free vs Pro',
    subtitle: 'Start free, upgrade when you need more',
    bullets: [
      'Free: 5 queries per week, NBA only',
      'Pro: Unlimited queries across all sports',
      'Pro: Trade analyzer, draft assistant, and more',
    ],
  },
];

interface OnboardingScreenProps {
  onComplete: () => void;
}

export default function OnboardingScreen({ onComplete }: OnboardingScreenProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatListRef = useRef<FlatList>(null);

  const onViewableItemsChanged = useRef(
    ({ viewableItems }: { viewableItems: ViewToken[] }) => {
      if (viewableItems.length > 0 && viewableItems[0].index != null) {
        setCurrentIndex(viewableItems[0].index);
      }
    },
  ).current;

  const viewabilityConfig = useRef({ viewAreaCoveragePercentThreshold: 50 }).current;

  const handleNext = () => {
    if (currentIndex < SLIDES.length - 1) {
      flatListRef.current?.scrollToIndex({ index: currentIndex + 1 });
    } else {
      handleFinish();
    }
  };

  const handleFinish = async () => {
    await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    onComplete();
  };

  const renderSlide = ({ item }: { item: OnboardingSlide }) => (
    <View style={styles.slide}>
      <View style={[styles.iconCircle, { backgroundColor: `${item.iconColor}20` }]}>
        <Ionicons name={item.icon} size={56} color={item.iconColor} />
      </View>
      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.subtitle}>{item.subtitle}</Text>
      <View style={styles.bulletList}>
        {item.bullets.map((bullet, idx) => (
          <View key={idx} style={styles.bulletRow}>
            <View style={[styles.bulletDot, { backgroundColor: item.iconColor }]} />
            <Text style={styles.bulletText}>{bullet}</Text>
          </View>
        ))}
      </View>
    </View>
  );

  const isLast = currentIndex === SLIDES.length - 1;

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.skipRow}>
        <TouchableOpacity onPress={handleFinish}>
          <Text style={styles.skipText}>Skip</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        ref={flatListRef}
        data={SLIDES}
        renderItem={renderSlide}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onViewableItemsChanged={onViewableItemsChanged}
        viewabilityConfig={viewabilityConfig}
      />

      <View style={styles.footer}>
        <View style={styles.dots}>
          {SLIDES.map((_, idx) => (
            <View
              key={idx}
              style={[
                styles.dot,
                idx === currentIndex ? styles.dotActive : styles.dotInactive,
              ]}
            />
          ))}
        </View>

        <TouchableOpacity style={styles.nextButton} onPress={handleNext}>
          <Text style={styles.nextButtonText}>
            {isLast ? 'Get Started' : 'Next'}
          </Text>
          {!isLast && <Ionicons name="arrow-forward" size={18} color="#fff" />}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

export { ONBOARDING_KEY };

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  skipRow: {
    alignItems: 'flex-end',
    paddingHorizontal: 20,
    paddingTop: 8,
  },
  skipText: {
    color: '#64748b',
    fontSize: 16,
    fontWeight: '500',
    padding: 8,
  },
  slide: {
    width,
    paddingHorizontal: 32,
    paddingTop: 40,
    alignItems: 'center',
  },
  iconCircle: {
    width: 110,
    height: 110,
    borderRadius: 55,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 32,
  },
  title: {
    fontSize: 26,
    fontWeight: '700',
    color: '#fff',
    textAlign: 'center',
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 15,
    color: '#94a3b8',
    textAlign: 'center',
    marginBottom: 32,
    lineHeight: 22,
  },
  bulletList: {
    alignSelf: 'stretch',
    gap: 14,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  bulletDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginTop: 6,
  },
  bulletText: {
    fontSize: 15,
    color: '#cbd5e1',
    flex: 1,
    lineHeight: 22,
  },
  footer: {
    paddingHorizontal: 32,
    paddingBottom: 24,
    gap: 20,
    alignItems: 'center',
  },
  dots: {
    flexDirection: 'row',
    gap: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  dotActive: {
    backgroundColor: '#818cf8',
    width: 24,
  },
  dotInactive: {
    backgroundColor: '#334155',
  },
  nextButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#4f46e5',
    paddingHorizontal: 32,
    paddingVertical: 16,
    borderRadius: 12,
    width: '100%',
    gap: 8,
  },
  nextButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '600',
  },
});
