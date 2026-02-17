'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { Sparkles, Zap, Shield, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/stores/authStore';
import { LanguageSelector } from '@/components/LanguageSelector';
import { useTranslation } from '@/i18n/I18nProvider';

// Lazy load GoogleLogin to avoid SSR issues
import dynamic from 'next/dynamic';
const GoogleLoginButton = dynamic(
  () => import('@react-oauth/google').then((mod) => mod.GoogleLogin),
  { ssr: false, loading: () => <div className="h-10 w-[280px] bg-dark-700 rounded animate-pulse" /> }
);

export default function LoginPage() {
  const router = useRouter();
  const { signInWithGoogle, isAuthenticated, isLoading } = useAuthStore();
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/ask');
    }
  }, [isAuthenticated, router]);

  const handleGoogleSuccess = async (credentialResponse: { credential?: string }) => {
    setError(null);
    if (!credentialResponse.credential) {
      setError(t('login.noCredential'));
      return;
    }

    try {
      await signInWithGoogle(credentialResponse.credential);
      router.push('/ask');
    } catch (err) {
      console.error('Login failed:', err);
      setError(err instanceof Error ? err.message : t('login.signInFailed'));
    }
  };

  const handleGoogleError = () => {
    setError(t('login.googleError'));
  };

  const handleContinueAsGuest = () => {
    router.push('/ask');
  };

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950">
      {/* Language selector in top-right */}
      <div className="flex justify-end p-4">
        <LanguageSelector />
      </div>

      <div className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          {/* Logo */}
          <Link href="/" className="flex items-center justify-center gap-2 mb-8">
            <Image src="/logo.png" alt="Bench Goblins" width={48} height={48} className="rounded" />
            <span className="text-2xl font-bold gradient-text">Bench Goblins</span>
          </Link>

          <Card className="bg-dark-900/80 border-dark-800 backdrop-blur">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl">{t('login.welcome')}</CardTitle>
              <CardDescription>{t('login.subtitle')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Error Message */}
              {error && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <p className="text-sm">{error}</p>
                </div>
              )}

              {/* Google Sign-In */}
              <div className="flex flex-col items-center gap-4">
                <p className="text-sm text-dark-400">{t('login.signInPrompt')}</p>
                <div className="flex justify-center">
                  <GoogleLoginButton
                    onSuccess={handleGoogleSuccess}
                    onError={handleGoogleError}
                    theme="filled_black"
                    size="large"
                    text="signin_with"
                    shape="rectangular"
                    width={280}
                  />
                </div>
              </div>

              {/* Divider */}
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-dark-700" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-dark-900 px-2 text-dark-500">{t('common.or')}</span>
                </div>
              </div>

              {/* Continue as Guest */}
              <Button
                onClick={handleContinueAsGuest}
                variant="outline"
                className="w-full gap-3 h-12 text-base border-dark-700 hover:bg-dark-800"
                disabled={isLoading}
              >
                <Sparkles className="h-5 w-5" />
                {t('login.continueGuest')}
              </Button>

              {/* Features Grid */}
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="p-3 rounded-lg bg-dark-800/50 border border-dark-700 text-center">
                  <Zap className="h-5 w-5 text-primary-400 mx-auto mb-1" />
                  <div className="text-sm font-medium">{t('login.freeQueries')}</div>
                  <div className="text-xs text-dark-400">{t('login.freeQueriesNote')}</div>
                </div>
                <div className="p-3 rounded-lg bg-dark-800/50 border border-dark-700 text-center">
                  <Shield className="h-5 w-5 text-primary-400 mx-auto mb-1" />
                  <div className="text-sm font-medium">{t('login.unlimitedPro')}</div>
                  <div className="text-xs text-dark-400">{t('login.unlimitedProNote')}</div>
                </div>
              </div>

              <p className="text-center text-xs text-dark-500 pt-2">
                {t('login.termsNotice')}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
