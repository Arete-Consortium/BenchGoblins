import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Terms of Service - Bench Goblins',
  description: 'BenchGoblins Terms of Service — rules and guidelines for using our platform.',
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-dark-950 text-dark-100 py-12 px-4">
      <div className="max-w-3xl mx-auto">
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-dark-400 hover:text-dark-200 mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Settings
        </Link>

        <h1 className="text-3xl font-bold text-primary-400 mb-2">Terms of Service</h1>
        <p className="text-dark-400 text-sm mb-8">Last updated: January 14, 2026</p>

        <div className="prose-dark space-y-8">
          <p>
            Welcome to BenchGoblins! These Terms of Service (&ldquo;Terms&rdquo;) govern your use of the
            BenchGoblins application (&ldquo;App&rdquo;) and related services provided by BenchGoblins
            (&ldquo;we,&rdquo; &ldquo;us,&rdquo; or &ldquo;our&rdquo;). By downloading, installing, or
            using our App, you agree to be bound by these Terms.
          </p>

          <div className="p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-dark-200">
            <strong>Important:</strong> Please read these Terms carefully before using BenchGoblins. If
            you do not agree to these Terms, do not use the App.
          </div>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">1. Acceptance of Terms</h2>
            <p className="mb-2">By accessing or using BenchGoblins, you confirm that:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>You are at least 18 years old or the age of majority in your jurisdiction</li>
              <li>You have the legal capacity to enter into a binding agreement</li>
              <li>You are not prohibited from using the App under applicable laws</li>
              <li>You will comply with these Terms and all applicable laws and regulations</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">2. Description of Service</h2>
            <p className="mb-2">BenchGoblins is a fantasy sports decision assistance tool that provides:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>AI-powered analysis for fantasy sports roster decisions</li>
              <li>Player comparisons and recommendations</li>
              <li>Statistical analysis and projections</li>
              <li>Risk-adjusted scoring across multiple fantasy sports</li>
            </ul>
            <p className="mt-2 text-dark-300">
              BenchGoblins is designed to assist with fantasy sports decisions only. We do not facilitate,
              promote, or enable real-money gambling or sports betting.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">3. User Accounts</h2>
            <p className="mb-2">To access certain features, you may need to create an account. You agree to:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Provide accurate and complete registration information</li>
              <li>Maintain the security of your account credentials</li>
              <li>Promptly notify us of any unauthorized account access</li>
              <li>Accept responsibility for all activities under your account</li>
            </ul>
            <p className="mt-2 text-dark-300">
              We reserve the right to suspend or terminate accounts that violate these Terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">4. Subscription and Payments</h2>
            <p className="mb-2">BenchGoblins offers subscription-based premium features:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">Free Tier:</strong> Limited access to basic features</li>
              <li><strong className="text-dark-100">Premium Tier:</strong> Full access to all features and AI analysis</li>
            </ul>
            <p className="mt-4 mb-2">Subscription terms:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Subscriptions are billed through Apple&apos;s App Store or web payment providers</li>
              <li>Payment is charged to your account at confirmation of purchase</li>
              <li>Subscriptions automatically renew unless canceled at least 24 hours before the end of the current period</li>
              <li>You can manage and cancel subscriptions in your account settings</li>
              <li>No refunds are provided for partial subscription periods</li>
            </ul>
            <p className="mt-2 text-dark-300">
              Prices are subject to change. We will notify you of any price changes before they take effect.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">5. Acceptable Use</h2>
            <p className="mb-2">You agree NOT to:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Use the App for any illegal purpose or in violation of any laws</li>
              <li>Use the App to facilitate real-money gambling where prohibited</li>
              <li>Attempt to reverse engineer, decompile, or disassemble the App</li>
              <li>Interfere with or disrupt the App&apos;s servers or networks</li>
              <li>Use automated systems or bots to access the App</li>
              <li>Scrape, harvest, or collect data from the App without permission</li>
              <li>Impersonate any person or entity</li>
              <li>Share your account credentials with others</li>
              <li>Use the App in any way that could harm minors</li>
              <li>Violate the intellectual property rights of others</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">6. Intellectual Property</h2>
            <p className="mb-2">
              All content, features, and functionality of BenchGoblins, including but not limited to:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Software code and algorithms</li>
              <li>Text, graphics, logos, and icons</li>
              <li>User interface design</li>
              <li>Scoring methodologies and analysis frameworks</li>
            </ul>
            <p className="mt-2 text-dark-300">
              are owned by BenchGoblins or our licensors and protected by copyright, trademark, and other
              intellectual property laws. You may not copy, modify, distribute, sell, or lease any part of
              the App without our written permission.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">7. Third-Party Services and Data</h2>
            <p className="mb-2">BenchGoblins integrates with third-party services:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">ESPN:</strong> Player statistics and sports data</li>
              <li><strong className="text-dark-100">Anthropic (Claude AI):</strong> AI-powered analysis</li>
              <li><strong className="text-dark-100">RevenueCat:</strong> Subscription management</li>
              <li><strong className="text-dark-100">Apple:</strong> App distribution and payments</li>
            </ul>
            <p className="mt-2 text-dark-300">
              Your use of these services is subject to their respective terms and policies. We are not
              responsible for third-party content, accuracy, or availability.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">8. Disclaimer of Warranties</h2>
            <div className="p-4 rounded-lg bg-red-500/10 border-l-4 border-red-500 text-dark-200 mb-4">
              <strong>THE APP IS PROVIDED &ldquo;AS IS&rdquo; AND &ldquo;AS AVAILABLE&rdquo; WITHOUT
              WARRANTIES OF ANY KIND.</strong>
            </div>
            <p className="mb-2">
              We expressly disclaim all warranties, whether express, implied, or statutory, including:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Warranties of merchantability and fitness for a particular purpose</li>
              <li>Warranties regarding the accuracy, reliability, or completeness of any analysis or recommendations</li>
              <li>Warranties that the App will be uninterrupted, error-free, or secure</li>
              <li>Warranties regarding the results you may obtain from using the App</li>
            </ul>
            <p className="mt-4 text-dark-300">
              <strong className="text-dark-100">Fantasy Sports Disclaimer:</strong> BenchGoblins provides
              analysis and recommendations for entertainment and informational purposes only. We do not
              guarantee any particular outcome in fantasy sports competitions. Past performance does not
              guarantee future results. You are solely responsible for your fantasy sports decisions.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">9. Limitation of Liability</h2>
            <p className="mb-2 font-medium">TO THE MAXIMUM EXTENT PERMITTED BY LAW:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>BenchGoblins shall not be liable for any indirect, incidental, special, consequential, or punitive damages</li>
              <li>Our total liability shall not exceed the amount you paid for the App in the 12 months preceding the claim</li>
              <li>We are not liable for any losses in fantasy sports competitions or any financial decisions you make based on our analysis</li>
            </ul>
            <p className="mt-2 text-dark-300">
              Some jurisdictions do not allow certain liability limitations, so some of the above may not
              apply to you.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">10. Indemnification</h2>
            <p className="mb-2">
              You agree to indemnify, defend, and hold harmless BenchGoblins and its officers, directors,
              employees, and agents from any claims, damages, losses, or expenses (including reasonable
              attorneys&apos; fees) arising from:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Your use of the App</li>
              <li>Your violation of these Terms</li>
              <li>Your violation of any third-party rights</li>
              <li>Any content you submit through the App</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">11. Modifications to Service</h2>
            <p className="mb-2">We reserve the right to:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Modify, suspend, or discontinue any aspect of the App at any time</li>
              <li>Add or remove features without notice</li>
              <li>Update these Terms at our discretion</li>
            </ul>
            <p className="mt-2 text-dark-300">
              Continued use of the App after changes constitutes acceptance of the modified Terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">12. Termination</h2>
            <p className="mb-2">
              We may terminate or suspend your access to the App immediately, without prior notice, for:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Violation of these Terms</li>
              <li>Conduct that we determine is harmful to other users or our business</li>
              <li>Any reason at our sole discretion</li>
            </ul>
            <p className="mt-2 text-dark-300">
              Upon termination, your right to use the App ceases immediately. Provisions that by their
              nature should survive termination will remain in effect.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">13. Governing Law and Disputes</h2>
            <p className="mb-2 text-dark-300">
              These Terms are governed by the laws of the State of California, United States, without
              regard to conflict of law principles.
            </p>
            <p className="mb-2 text-dark-300">
              Any disputes arising from these Terms or your use of the App shall be resolved through:
            </p>
            <ol className="list-decimal pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">Informal Resolution:</strong> Contact us first to attempt to resolve the dispute informally</li>
              <li><strong className="text-dark-100">Binding Arbitration:</strong> If informal resolution fails, disputes will be resolved through binding arbitration under the rules of the American Arbitration Association</li>
            </ol>
            <p className="mt-2 text-dark-300">
              You agree to waive any right to a jury trial or to participate in a class action lawsuit.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">14. Severability</h2>
            <p className="text-dark-300">
              If any provision of these Terms is found to be unenforceable, the remaining provisions will
              continue in full force and effect.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">15. Entire Agreement</h2>
            <p className="text-dark-300">
              These Terms, together with our{' '}
              <Link href="/privacy" className="text-primary-400 hover:underline">Privacy Policy</Link>,
              constitute the entire agreement between you and BenchGoblins regarding your use of the App.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">16. Contact Information</h2>
            <p className="mb-2 text-dark-300">For questions about these Terms of Service, please contact us:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>
                <strong className="text-dark-100">Email:</strong>{' '}
                <a href="mailto:legal@benchgoblins.app" className="text-primary-400 hover:underline">
                  legal@benchgoblins.app
                </a>
              </li>
            </ul>
          </section>

          <footer className="pt-8 border-t border-dark-800 text-dark-500 text-sm">
            <p>&copy; 2026 BenchGoblins. All rights reserved.</p>
            <p className="mt-1">
              <Link href="/privacy" className="text-dark-400 hover:text-dark-200">Privacy Policy</Link>
              {' | '}
              <Link href="/terms" className="text-dark-400 hover:text-dark-200">Terms of Service</Link>
            </p>
          </footer>
        </div>
      </div>
    </div>
  );
}
