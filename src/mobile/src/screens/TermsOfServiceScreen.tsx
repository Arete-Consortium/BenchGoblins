import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useThemeStore } from '../stores/themeStore';

type TermsOfServiceScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

export default function TermsOfServiceScreen({ navigation }: TermsOfServiceScreenProps) {
  const { theme } = useThemeStore();

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <View style={[styles.header, { borderBottomColor: theme.border }]}>
        <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
          <Ionicons name="arrow-back" size={24} color={theme.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: theme.text }]}>Terms of Service</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView style={styles.scrollView} contentContainerStyle={styles.content}>
        <Text style={[styles.lastUpdated, { color: theme.textTertiary }]}>Last Updated: January 2026</Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>1. Acceptance of Terms</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          By accessing or using BenchGoblins, you agree to be bound by these Terms of Service.
          If you do not agree to these terms, do not use the app.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>2. Description of Service</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          BenchGoblins is a fantasy sports decision engine that provides analysis and
          recommendations for start/sit, waiver, and trade decisions. The service is
          for entertainment and informational purposes only.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>3. No Guarantee of Results</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          BenchGoblins provides probabilistic analysis, not predictions or guarantees. Fantasy
          sports involve uncertainty, and our recommendations are based on available data
          and analytical models. We do not guarantee any specific outcomes or results.
          Past performance is not indicative of future results.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>4. User Accounts</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          You are responsible for maintaining the confidentiality of your account credentials.
          You agree to notify us immediately of any unauthorized use of your account.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>5. Subscriptions and Payments</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          BenchGoblins offers subscription plans that provide access to premium features.
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Payment will be charged to your Apple ID account at confirmation of purchase
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Subscriptions automatically renew unless auto-renew is turned off at least
          24 hours before the end of the current period
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Your account will be charged for renewal within 24 hours prior to the end
          of the current period
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} You can manage or cancel your subscription in your App Store account settings
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} No refunds will be provided for partial subscription periods
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>6. Acceptable Use</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          You agree not to:
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Use the service for any illegal purpose
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Attempt to reverse engineer or extract source code
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Interfere with or disrupt the service
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Share your account credentials with others
        </Text>
        <Text style={[styles.bulletPoint, { color: theme.textSecondary }]}>
          {'\u2022'} Use automated systems to access the service
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>7. Intellectual Property</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          All content, features, and functionality of BenchGoblins are owned by us and are
          protected by copyright, trademark, and other intellectual property laws. You
          may not copy, modify, distribute, or create derivative works without our
          prior written consent.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>8. Disclaimer of Warranties</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          BENCHGOBLINS IS PROVIDED "AS IS" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED.
          WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR SECURE.
          WE DISCLAIM ALL WARRANTIES, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR
          PURPOSE, AND NON-INFRINGEMENT.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>9. Limitation of Liability</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          TO THE MAXIMUM EXTENT PERMITTED BY LAW, WE SHALL NOT BE LIABLE FOR ANY INDIRECT,
          INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING LOSS OF PROFITS,
          DATA, OR OTHER INTANGIBLE LOSSES, RESULTING FROM YOUR USE OF THE SERVICE.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>10. Changes to Terms</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          We reserve the right to modify these terms at any time. We will notify you of
          significant changes through the app or via email. Your continued use of the
          service after changes constitutes acceptance of the new terms.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>11. Governing Law</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          These Terms shall be governed by and construed in accordance with the laws of
          the State of Delaware, without regard to its conflict of law provisions.
        </Text>

        <Text style={[styles.sectionTitle, { color: theme.text }]}>12. Contact Us</Text>
        <Text style={[styles.paragraph, { color: theme.textSecondary }]}>
          If you have questions about these Terms, please contact us at:
        </Text>
        <Text style={[styles.contactInfo, { color: theme.primary }]}>legal@benchgoblins.app</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2e',
  },
  backButton: {
    padding: 8,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
  },
  placeholder: {
    width: 40,
  },
  scrollView: {
    flex: 1,
  },
  content: {
    padding: 24,
  },
  lastUpdated: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginTop: 24,
    marginBottom: 12,
  },
  paragraph: {
    fontSize: 15,
    color: '#d1d5db',
    lineHeight: 24,
    marginBottom: 12,
  },
  bulletPoint: {
    fontSize: 15,
    color: '#d1d5db',
    lineHeight: 24,
    marginLeft: 16,
    marginBottom: 4,
  },
  contactInfo: {
    fontSize: 15,
    color: '#6366f1',
    marginTop: 8,
  },
});
