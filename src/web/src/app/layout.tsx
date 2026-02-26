import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { ThemeProvider } from '@/components/providers/ThemeProvider';
import { QueryProvider } from '@/components/providers/QueryProvider';
import { GoogleAuthProviderWrapper } from '@/components/providers/GoogleAuthProvider';
import { RevenueCatProvider } from '@/components/providers/RevenueCatProvider';
import { I18nProvider } from '@/i18n/I18nProvider';
import { ToastProvider, ToastViewport } from '@/components/ui/toast';
import GoogleAnalytics from '@/components/GoogleAnalytics';
import CookieConsent from '@/components/CookieConsent';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: {
    default: 'Bench Goblins — AI Fantasy Sports Start/Sit, Trade & Waiver Decisions',
    template: '%s | Bench Goblins',
  },
  description:
    'AI-powered fantasy sports decisions for NBA, NFL, MLB, NHL, and Soccer. Start/sit, trade, and waiver recommendations with Five-Index scoring. Available in 9 languages.',
  keywords: [
    'fantasy sports',
    'AI fantasy advice',
    'NBA',
    'NFL',
    'MLB',
    'NHL',
    'soccer',
    'FPL',
    'start sit',
    'trade analyzer',
    'waiver wire',
    'fantasy football',
    'fantasy basketball',
    'fantasy baseball',
    'fantasy hockey',
    'fantasy soccer',
  ],
  authors: [{ name: 'Bench Goblins' }],
  metadataBase: new URL('https://benchgoblins.com'),
  openGraph: {
    title: 'Bench Goblins — AI Fantasy Sports Start/Sit, Trade & Waiver Decisions',
    description:
      'The only AI fantasy engine with transparent Five-Index scoring, situational risk modes, and five-sport coverage across 9 languages.',
    type: 'website',
    siteName: 'Bench Goblins',
    url: 'https://benchgoblins.com',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Bench Goblins — AI Fantasy Sports Decision Engine',
    description:
      'AI-powered start/sit, trade, and waiver decisions for NBA, NFL, MLB, NHL, and Soccer.',
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <GoogleAnalytics />
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
                    <CookieConsent />
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
