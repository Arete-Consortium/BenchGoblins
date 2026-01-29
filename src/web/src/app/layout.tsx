import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'GameSpace - Fantasy Sports Decision Engine',
  description:
    'Make smarter fantasy sports decisions with AI-powered analysis. Start/sit, trade, and waiver recommendations for NBA, NFL, MLB, and NHL.',
  keywords: ['fantasy sports', 'NBA', 'NFL', 'MLB', 'NHL', 'start sit', 'trade analyzer'],
  authors: [{ name: 'GameSpace' }],
  openGraph: {
    title: 'GameSpace - Fantasy Sports Decision Engine',
    description: 'Make smarter fantasy sports decisions with AI-powered analysis.',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-dark-950 text-dark-100 antialiased">
        {children}
      </body>
    </html>
  );
}
