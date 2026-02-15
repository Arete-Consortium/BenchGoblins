import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Privacy Policy - Bench Goblins',
  description: 'BenchGoblins Privacy Policy — how we collect, use, and protect your information.',
};

export default function PrivacyPage() {
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

        <h1 className="text-3xl font-bold text-primary-400 mb-2">Privacy Policy</h1>
        <p className="text-dark-400 text-sm mb-8">Last updated: January 14, 2026</p>

        <div className="prose-dark space-y-8">
          <p>
            BenchGoblins (&ldquo;we,&rdquo; &ldquo;our,&rdquo; or &ldquo;us&rdquo;) is committed to
            protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and
            safeguard your information when you use our application.
          </p>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">1. Information We Collect</h2>

            <h3 className="text-lg font-medium mb-2">1.1 Information You Provide</h3>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">Account Information:</strong> When you create an account, we may collect your email address and username.</li>
              <li><strong className="text-dark-100">Queries:</strong> The fantasy sports questions you submit to the app for analysis.</li>
              <li><strong className="text-dark-100">Subscription Information:</strong> Payment and subscription status (processed securely through Apple and RevenueCat).</li>
            </ul>

            <h3 className="text-lg font-medium mt-4 mb-2">1.2 Automatically Collected Information</h3>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">Usage Data:</strong> How you interact with the app, including features used and query frequency.</li>
              <li><strong className="text-dark-100">Device Information:</strong> Device type, operating system version, and unique device identifiers.</li>
              <li><strong className="text-dark-100">Analytics:</strong> Aggregated, anonymized data about app performance and usage patterns.</li>
            </ul>

            <h3 className="text-lg font-medium mt-4 mb-2">1.3 Information from Third Parties</h3>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">Sports Data:</strong> We retrieve publicly available player statistics from ESPN to power our analysis.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">2. How We Use Your Information</h2>
            <p className="mb-2">We use the collected information to:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Provide fantasy sports analysis and recommendations</li>
              <li>Process and manage your subscription</li>
              <li>Improve and optimize our services</li>
              <li>Communicate with you about updates or issues</li>
              <li>Enforce our terms and prevent abuse</li>
              <li>Comply with legal obligations</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">3. Third-Party Services</h2>
            <p className="mb-4">We work with the following third-party services:</p>

            <h3 className="text-lg font-medium mb-2">3.1 Anthropic (Claude AI)</h3>
            <p className="text-dark-300 mb-4">
              Your queries may be processed by Anthropic&apos;s Claude AI to generate fantasy sports
              recommendations. Anthropic&apos;s privacy policy applies to this processing. We do not share
              personal identifying information with Anthropic beyond the query content.
            </p>

            <h3 className="text-lg font-medium mb-2">3.2 RevenueCat</h3>
            <p className="text-dark-300 mb-4">
              We use RevenueCat to manage subscriptions. RevenueCat receives anonymized purchase data
              from Apple. See{' '}
              <a href="https://www.revenuecat.com/privacy" className="text-primary-400 hover:underline" target="_blank" rel="noopener noreferrer">
                RevenueCat&apos;s Privacy Policy
              </a>.
            </p>

            <h3 className="text-lg font-medium mb-2">3.3 ESPN</h3>
            <p className="text-dark-300 mb-4">
              We retrieve publicly available sports statistics from ESPN&apos;s public APIs. No personal data
              is shared with ESPN.
            </p>

            <h3 className="text-lg font-medium mb-2">3.4 Apple</h3>
            <p className="text-dark-300">
              Payments are processed through Apple&apos;s App Store. Apple&apos;s privacy policy governs
              payment processing.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">4. Data Retention</h2>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">Query History:</strong> Stored for up to 90 days to provide history features, then deleted.</li>
              <li><strong className="text-dark-100">Account Data:</strong> Retained while your account is active. Deleted within 30 days of account deletion request.</li>
              <li><strong className="text-dark-100">Analytics:</strong> Aggregated, anonymized data may be retained indefinitely.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">5. Data Security</h2>
            <p className="mb-2">We implement appropriate technical and organizational measures to protect your data, including:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li>Encryption in transit (HTTPS/TLS)</li>
              <li>Secure cloud infrastructure</li>
              <li>Access controls and authentication</li>
              <li>Regular security assessments</li>
            </ul>
            <p className="mt-2 text-dark-300">
              However, no method of transmission over the Internet is 100% secure. We cannot guarantee
              absolute security.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">6. Your Rights</h2>
            <p className="mb-2">Depending on your location, you may have the right to:</p>
            <ul className="list-disc pl-6 space-y-2 text-dark-300">
              <li><strong className="text-dark-100">Access:</strong> Request a copy of your personal data</li>
              <li><strong className="text-dark-100">Correction:</strong> Request correction of inaccurate data</li>
              <li><strong className="text-dark-100">Deletion:</strong> Request deletion of your personal data</li>
              <li><strong className="text-dark-100">Portability:</strong> Request your data in a portable format</li>
              <li><strong className="text-dark-100">Opt-out:</strong> Opt out of certain data processing</li>
            </ul>
            <p className="mt-2 text-dark-300">
              To exercise these rights, contact us at{' '}
              <a href="mailto:privacy@benchgoblins.app" className="text-primary-400 hover:underline">
                privacy@benchgoblins.app
              </a>.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">7. Children&apos;s Privacy</h2>
            <p className="text-dark-300">
              BenchGoblins is not intended for children under 13. We do not knowingly collect personal
              information from children under 13. If you believe we have collected such information,
              please contact us immediately.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">8. International Users</h2>
            <p className="text-dark-300">
              If you access BenchGoblins from outside the United States, your data may be transferred to
              and processed in the United States, where data protection laws may differ from those in your
              country.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">9. Changes to This Policy</h2>
            <p className="text-dark-300">
              We may update this Privacy Policy from time to time. We will notify you of material changes
              by posting the new policy in the app and updating the &ldquo;Last updated&rdquo; date. Your
              continued use of the app after changes constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">10. Contact Us</h2>
            <p className="text-dark-300">
              If you have questions about this Privacy Policy, please contact us:
            </p>
            <ul className="list-disc pl-6 mt-2 text-dark-300">
              <li>
                Email:{' '}
                <a href="mailto:privacy@benchgoblins.app" className="text-primary-400 hover:underline">
                  privacy@benchgoblins.app
                </a>
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">11. California Privacy Rights (CCPA)</h2>
            <p className="text-dark-300">
              California residents have additional rights under the CCPA, including the right to know what
              personal information is collected, request deletion, and opt out of the sale of personal
              information. We do not sell personal information.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-primary-400 mb-4">12. European Privacy Rights (GDPR)</h2>
            <p className="text-dark-300">
              If you are in the European Economic Area, you have rights under GDPR including access,
              rectification, erasure, restriction, portability, and objection. Our legal basis for
              processing is contract performance (providing the service) and legitimate interests
              (improving our services).
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
