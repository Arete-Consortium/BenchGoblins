import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Pricing — Bench Goblins Pro',
  description:
    'Unlock unlimited AI-powered fantasy sports decisions. Free and Pro plans available for NBA, NFL, MLB, NHL, and Soccer analysis.',
  openGraph: {
    title: 'Pricing — Bench Goblins Pro',
    description:
      'Upgrade to Bench Goblins Pro for unlimited queries, all risk modes, and advanced AI analysis.',
  },
};

export default function BillingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
