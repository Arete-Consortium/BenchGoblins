import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Ask Bench Goblins — AI-Powered Fantasy Lineup Advice',
  description:
    'Get instant AI-powered start/sit, trade, and waiver recommendations for NBA, NFL, MLB, NHL, and Soccer. Five-Index scoring with three risk modes.',
  openGraph: {
    title: 'Ask Bench Goblins — AI-Powered Fantasy Lineup Advice',
    description:
      'Ask any fantasy sports question and get AI-powered recommendations with Five-Index scoring analysis.',
  },
};

export default function AskLayout({ children }: { children: React.ReactNode }) {
  return children;
}
