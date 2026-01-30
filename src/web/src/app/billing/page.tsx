'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { CreditCard, Check, Zap, Crown, ArrowLeft, Loader2, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/stores/authStore';
import api from '@/lib/api';

const FREE_FEATURES = [
  '5 queries per day',
  'All sports (NBA, NFL, MLB, NHL)',
  'Basic AI recommendations',
  'Start/sit decisions',
];

const PRO_FEATURES = [
  'Unlimited queries',
  'All sports (NBA, NFL, MLB, NHL)',
  'Advanced AI analysis',
  'Trade & waiver recommendations',
  'Priority response time',
  'Decision history export',
];

export default function BillingPage() {
  const router = useRouter();
  const { user, isAuthenticated, refreshUser } = useAuthStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/auth/login');
    }
  }, [isAuthenticated, router]);

  const handleUpgrade = async () => {
    if (!user) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await api.createCheckoutSession();
      if (response.checkout_url) {
        window.location.href = response.checkout_url;
      }
    } catch (err) {
      console.error('Checkout error:', err);
      setError('Failed to create checkout session. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleManageSubscription = async () => {
    if (!user) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await api.createPortalSession();
      if (response.portal_url) {
        window.location.href = response.portal_url;
      }
    } catch (err) {
      console.error('Portal error:', err);
      setError('Failed to open billing portal. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-400" />
      </div>
    );
  }

  const isPro = user.subscription_tier === 'pro';

  return (
    <div className="min-h-screen bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950 pt-20 pb-12 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Back button */}
        <Link href="/ask" className="inline-flex items-center gap-2 text-dark-400 hover:text-dark-200 mb-8">
          <ArrowLeft className="h-4 w-4" />
          Back to Ask
        </Link>

        <div className="text-center mb-12">
          <h1 className="text-3xl font-bold mb-2">Choose Your Plan</h1>
          <p className="text-dark-400">Unlock unlimited AI-powered fantasy decisions</p>
        </div>

        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-center">
            {error}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          {/* Free Plan */}
          <Card className={`bg-dark-900/80 border-dark-700 ${!isPro ? 'ring-2 ring-primary-500' : ''}`}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap className="h-5 w-5 text-dark-400" />
                  <CardTitle>Free</CardTitle>
                </div>
                {!isPro && (
                  <span className="text-xs font-medium px-2 py-1 rounded-full bg-primary-500/20 text-primary-400">
                    Current Plan
                  </span>
                )}
              </div>
              <CardDescription>Perfect for casual players</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <span className="text-4xl font-bold">$0</span>
                <span className="text-dark-400">/month</span>
              </div>

              <ul className="space-y-3">
                {FREE_FEATURES.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                    <Check className="h-4 w-4 text-dark-500" />
                    {feature}
                  </li>
                ))}
              </ul>

              {!isPro && (
                <Button variant="outline" className="w-full" disabled>
                  Current Plan
                </Button>
              )}
            </CardContent>
          </Card>

          {/* Pro Plan */}
          <Card className={`bg-dark-900/80 border-primary-500/50 ${isPro ? 'ring-2 ring-primary-500' : ''}`}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Crown className="h-5 w-5 text-primary-400" />
                  <CardTitle className="gradient-text">Pro</CardTitle>
                </div>
                {isPro && (
                  <span className="text-xs font-medium px-2 py-1 rounded-full bg-primary-500/20 text-primary-400">
                    Current Plan
                  </span>
                )}
              </div>
              <CardDescription>For serious fantasy managers</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <span className="text-4xl font-bold gradient-text">$9.99</span>
                <span className="text-dark-400">/month</span>
              </div>

              <ul className="space-y-3">
                {PRO_FEATURES.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-dark-200">
                    <Check className="h-4 w-4 text-primary-400" />
                    {feature}
                  </li>
                ))}
              </ul>

              {isPro ? (
                <Button
                  onClick={handleManageSubscription}
                  variant="outline"
                  className="w-full gap-2"
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <CreditCard className="h-4 w-4" />
                      Manage Subscription
                      <ExternalLink className="h-3 w-3" />
                    </>
                  )}
                </Button>
              ) : (
                <Button
                  onClick={handleUpgrade}
                  className="w-full gap-2 bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-400 hover:to-primary-500"
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Crown className="h-4 w-4" />
                      Upgrade to Pro
                    </>
                  )}
                </Button>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Usage Stats */}
        <Card className="mt-8 bg-dark-900/50 border-dark-700">
          <CardHeader>
            <CardTitle className="text-lg">Your Usage Today</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-500 rounded-full transition-all"
                    style={{
                      width: isPro ? '0%' : `${Math.min((user.queries_today / user.queries_limit) * 100, 100)}%`,
                    }}
                  />
                </div>
              </div>
              <div className="text-sm text-dark-300">
                {isPro ? (
                  <span className="text-primary-400">Unlimited</span>
                ) : (
                  <>
                    <span className="font-medium">{user.queries_today}</span>
                    <span className="text-dark-500"> / {user.queries_limit} queries</span>
                  </>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* FAQ */}
        <div className="mt-12 text-center text-sm text-dark-500">
          <p>Questions? Contact us at support@benchgoblin.ai</p>
          <p className="mt-2">Cancel anytime. No hidden fees.</p>
        </div>
      </div>
    </div>
  );
}
