import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Goblin Verdict — Weekly Lineup Swap Recommendations',
  description:
    'Get AI-powered weekly lineup verdicts with swap recommendations. The Goblin analyzes your roster across Floor, Median, and Ceiling risk modes.',
  openGraph: {
    title: 'Goblin Verdict — Weekly Lineup Swap Recommendations',
    description:
      'The Goblin has spoken. AI-powered lineup verdicts with swap recommendations for your fantasy roster.',
    type: 'website',
    url: 'https://benchgoblins.com/verdict',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Goblin Verdict — AI Lineup Analysis',
    description:
      'Get weekly swap recommendations from the Goblin. Floor, Median, and Ceiling risk modes.',
  },
};

export default function VerdictLayout({ children }: { children: React.ReactNode }) {
  return children;
}
