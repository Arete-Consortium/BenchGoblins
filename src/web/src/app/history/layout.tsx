import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Your Bench Goblins Decision History',
  description:
    'Review your past fantasy sports decisions and track outcomes. See how AI recommendations performed across NBA, NFL, MLB, NHL, and Soccer.',
  openGraph: {
    title: 'Your Bench Goblins Decision History',
    description:
      'Track your fantasy decisions and outcomes with Bench Goblins.',
  },
};

export default function HistoryLayout({ children }: { children: React.ReactNode }) {
  return children;
}
