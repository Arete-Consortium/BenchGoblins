import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { ThemeProvider } from '@/components/providers/ThemeProvider';
import { QueryProvider } from '@/components/providers/QueryProvider';
import { GoogleAuthProviderWrapper } from '@/components/providers/GoogleAuthProvider';
import { RevenueCatProvider } from '@/components/providers/RevenueCatProvider';
import { I18nProvider } from '@/i18n/I18nProvider';
import { ToastProvider, ToastViewport } from '@/components/ui/toast';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Bench Goblins - Fantasy Sports Decision Engine',
  description:
    'Make smarter fantasy sports decisions with AI-powered analysis. Start/sit, trade, and waiver recommendations for NBA, NFL, MLB, and NHL.',
  keywords: ['fantasy sports', 'NBA', 'NFL', 'MLB', 'NHL', 'start sit', 'trade analyzer'],
  authors: [{ name: 'Bench Goblins' }],
  openGraph: {
    title: 'Bench Goblins - Fantasy Sports Decision Engine',
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
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-dark-950 text-dark-100 antialiased`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <I18nProvider>
            <GoogleAuthProviderWrapper>
              <QueryProvider>
                <RevenueCatProvider>
                  <ToastProvider>
                    {children}
                    <ToastViewport />
                  </ToastProvider>
                </RevenueCatProvider>
              </QueryProvider>
            </GoogleAuthProviderWrapper>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
