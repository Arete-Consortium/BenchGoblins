import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';

type PrivacyPolicyScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

export default function PrivacyPolicyScreen({ navigation }: PrivacyPolicyScreenProps) {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Privacy Policy</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView style={styles.scrollView} contentContainerStyle={styles.content}>
        <Text style={styles.lastUpdated}>Last Updated: January 2026</Text>

        <Text style={styles.sectionTitle}>1. Information We Collect</Text>
        <Text style={styles.paragraph}>
          GameSpace collects information you provide directly to us, including:
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Account information (email address, username)
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Fantasy sports preferences and queries
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Usage data and app analytics
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Device information and identifiers
        </Text>

        <Text style={styles.sectionTitle}>2. How We Use Your Information</Text>
        <Text style={styles.paragraph}>
          We use the information we collect to:
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Provide and improve our fantasy sports decision engine
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Process your subscription and in-app purchases
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Send you notifications about your fantasy teams (if enabled)
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Analyze usage patterns to improve our service
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Comply with legal obligations
        </Text>

        <Text style={styles.sectionTitle}>3. Data Sharing</Text>
        <Text style={styles.paragraph}>
          We do not sell your personal information. We may share your information with:
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Service providers who assist in operating our app (e.g., cloud hosting, analytics)
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Payment processors for subscription management
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Law enforcement when required by law
        </Text>

        <Text style={styles.sectionTitle}>4. Data Security</Text>
        <Text style={styles.paragraph}>
          We implement appropriate technical and organizational measures to protect your
          personal information against unauthorized access, alteration, disclosure, or
          destruction. However, no method of transmission over the Internet is 100% secure.
        </Text>

        <Text style={styles.sectionTitle}>5. Your Rights</Text>
        <Text style={styles.paragraph}>
          Depending on your location, you may have the right to:
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Access your personal information
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Correct inaccurate data
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Delete your data
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Export your data
        </Text>
        <Text style={styles.bulletPoint}>
          {'\u2022'} Opt out of marketing communications
        </Text>

        <Text style={styles.sectionTitle}>6. Children's Privacy</Text>
        <Text style={styles.paragraph}>
          GameSpace is not intended for children under 13. We do not knowingly collect
          personal information from children under 13. If you believe we have collected
          information from a child under 13, please contact us.
        </Text>

        <Text style={styles.sectionTitle}>7. Changes to This Policy</Text>
        <Text style={styles.paragraph}>
          We may update this Privacy Policy from time to time. We will notify you of any
          changes by posting the new Privacy Policy on this page and updating the "Last
          Updated" date.
        </Text>

        <Text style={styles.sectionTitle}>8. Contact Us</Text>
        <Text style={styles.paragraph}>
          If you have questions about this Privacy Policy, please contact us at:
        </Text>
        <Text style={styles.contactInfo}>privacy@gamespace.app</Text>
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
