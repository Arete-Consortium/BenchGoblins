'use client';

import { useState, useCallback } from 'react';

import Link from 'next/link';
import { CreditCard, Check, Zap, Crown, ArrowLeft, Loader2, RefreshCw, AlertCircle, Calendar, Users2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/stores/authStore';
import { useSubscriptionStore } from '@/stores/subscriptionStore';
import { RC_ENTITLEMENT_ID } from '@/lib/revenuecat';

const FREE_FEATURES = [
  '5 queries per week',
  'All sports (NBA, NFL, MLB, NHL, Soccer)',
  'Basic AI recommendations',
  'Start/sit decisions',
];

const PAID_PLANS = [
  {
    name: 'Weekly',
    price: '$2.99',
    period: '/week',
    packageId: '$rc_weekly',
    features: ['Unlimited queries', 'All 5 sports', 'Advanced AI analysis', 'Trade & waiver recs', 'Cancel anytime'],
    highlight: false,
    badge: null,
  },
  {
    name: 'Monthly',
    price: '$7.99',
    period: '/month',
    packageId: '$rc_monthly',
    features: ['Unlimited queries', 'All 5 sports', 'Advanced AI analysis', 'Trade & waiver recs', 'Priority response', 'Cancel anytime'],
    highlight: true,
    badge: 'Most Popular',
  },
  {
    name: 'Annual',
    price: '$79.99',
    period: '/year',
    packageId: '$rc_annual',
    features: ['Unlimited queries', 'All 5 sports', 'Advanced AI analysis', 'Trade & waiver recs', 'Priority response', 'Decision history export'],
    highlight: false,
    badge: 'Best Value — ~$6.67/mo',
  },
];

const SPECIALIZED_PLANS = [
  {
    name: 'Seasonal Pass',
    price: '$29.99',
    period: '/season',
    packageId: '$rc_seasonal',
    features: ['One sport, unlimited queries', 'Advanced AI analysis', 'Trade & waiver recs'],
    icon: Calendar,
    iconBg: 'bg-orange-500/20',
    iconColor: 'text-orange-400',
    priceColor: 'text-orange-400',
    checkColor: 'text-orange-400',
    btnClass: 'border-orange-500/50 text-orange-400 hover:bg-orange-500/10',
  },
  {
    name: 'League Plan',
    price: '$4.99',
    period: '/mo per league',
    packageId: '$rc_league',
    features: ['One league, unlimited queries', 'League-scoped analysis', 'Trade & waiver recs'],
    icon: Users2,
    iconBg: 'bg-blue-500/20',
    iconColor: 'text-blue-400',
    priceColor: 'text-blue-400',
    checkColor: 'text-blue-400',
    btnClass: 'border-blue-500/50 text-blue-400 hover:bg-blue-500/10',
  },
];

export default function BillingPage() {
  const { user, isAuthenticated } = useAuthStore();
  const {
    isPro,
    isLoading: subscriptionLoading,
    customerInfo,
    offerings,
    error: subscriptionError,
    refreshCustomerInfo,
    purchase,
  } = useSubscriptionStore();

  const [purchaseLoading, setPurchaseLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleManualPurchase = useCallback(async (packageId: string) => {
    if (!offerings?.current) return;

    const pkg =
      offerings.current.availablePackages.find(
        (p) => p.identifier === packageId
      ) ?? null;

    if (!pkg) {
      setError(`Package "${packageId}" not found in current offering.`);
      return;
    }

    setPurchaseLoading(true);
    setError(null);

    const success = await purchase(pkg, user?.email);
    setPurchaseLoading(false);

    if (!success) {
      // User cancelled or error already set in store
    }
  }, [offerings, purchase, user?.email]);

  // Active subscription details from customer info
  const activeEntitlement = customerInfo?.entitlements.active[RC_ENTITLEMENT_ID];
  const expiresDate = activeEntitlement?.expirationDate
    ? new Date(activeEntitlement.expirationDate).toLocaleDateString()
    : null;

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

        {(error || subscriptionError) && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-center flex items-center justify-center gap-2">
            <AlertCircle className="h-4 w-4" />
            {error || subscriptionError}
          </div>
        )}

        <>
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
                <CardDescription>Perfect for casual players — $0</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {FREE_FEATURES.map((feature) => (
                    <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                      <Check className="h-4 w-4 text-dark-500" />
                      {feature}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {/* Paid Plans Grid */}
            <div className="grid md:grid-cols-3 gap-6 mt-6">
              {PAID_PLANS.map((plan) => (
                <Card
                  key={plan.name}
                  className={`bg-dark-900/80 ${plan.highlight ? 'border-primary-500/50 ring-2 ring-primary-500/30' : 'border-dark-700'}`}
                >
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Crown className="h-5 w-5 text-primary-400" />
                        <CardTitle className={plan.highlight ? 'gradient-text' : ''}>{plan.name}</CardTitle>
                      </div>
                      {plan.badge && (
                        <span className={`text-xs font-medium px-2 py-1 rounded-full ${plan.name === 'Annual' ? 'bg-green-500/20 text-green-400' : 'bg-primary-500/20 text-primary-400'}`}>
                          {plan.badge}
                        </span>
                      )}
                    </div>
                    <CardDescription>
                      <span className={`text-2xl font-bold ${plan.highlight ? 'gradient-text' : plan.name === 'Annual' ? 'text-green-400' : 'text-dark-200'}`}>
                        {plan.price}
                      </span>
                      <span className="text-dark-400">{plan.period}</span>
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <ul className="space-y-2">
                      {plan.features.map((feature) => (
                        <li key={feature} className="flex items-center gap-2 text-sm text-dark-200">
                          <Check className="h-4 w-4 text-primary-400" />
                          {feature}
                        </li>
                      ))}
                    </ul>

                    {!isAuthenticated ? (
                      <Button
                        asChild
                        className={`w-full gap-2 ${plan.name === 'Annual' ? 'bg-green-600 hover:bg-green-700' : 'bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-400 hover:to-primary-500'}`}
                      >
                        <Link href="/auth/login">
                          <Crown className="h-4 w-4" />
                          Sign in to Subscribe
                        </Link>
                      </Button>
                    ) : isPro ? (
                      <Button
                        onClick={() => refreshCustomerInfo()}
                        variant="outline"
                        className="w-full gap-2"
                        disabled={subscriptionLoading}
                      >
                        {subscriptionLoading ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <>
                            <RefreshCw className="h-4 w-4" />
                            Refresh Status
                          </>
                        )}
                      </Button>
                    ) : (
                      <Button
                        onClick={() => handleManualPurchase(plan.packageId)}
                        className={`w-full gap-2 ${plan.name === 'Annual' ? 'bg-green-600 hover:bg-green-700' : 'bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-400 hover:to-primary-500'}`}
                        disabled={purchaseLoading || subscriptionLoading}
                      >
                        {purchaseLoading || subscriptionLoading ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <>
                            <Crown className="h-4 w-4" />
                            Choose {plan.name}
                          </>
                        )}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Specialized Plans */}
            <div className="mt-10">
              <h3 className="text-lg font-semibold text-center mb-6 text-dark-300">Specialized Plans</h3>
              <div className="grid md:grid-cols-2 gap-6">
                {SPECIALIZED_PLANS.map((plan) => (
                  <Card key={plan.name} className="bg-dark-900/80 border-dark-700">
                    <CardContent className="pt-6 flex gap-4">
                      <div className="shrink-0">
                        <div className={`w-12 h-12 rounded-full ${plan.iconBg} flex items-center justify-center`}>
                          <plan.icon className={`h-6 w-6 ${plan.iconColor}`} />
                        </div>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-lg font-bold">{plan.name}</h4>
                        <div className="mb-3">
                          <span className={`text-2xl font-bold ${plan.priceColor}`}>{plan.price}</span>
                          <span className="text-dark-500 text-sm">{plan.period}</span>
                        </div>
                        <ul className="space-y-2 mb-4">
                          {plan.features.map((feature) => (
                            <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                              <Check className={`h-3.5 w-3.5 ${plan.checkColor} shrink-0`} />
                              {feature}
                            </li>
                          ))}
                        </ul>
                        {!isAuthenticated ? (
                          <Button
                            asChild
                            variant="outline"
                            className={`w-full ${plan.btnClass}`}
                          >
                            <Link href="/auth/login">
                              <Crown className="h-4 w-4 mr-2" />
                              Sign in to Subscribe
                            </Link>
                          </Button>
                        ) : isPro ? (
                          <Button
                            onClick={() => refreshCustomerInfo()}
                            variant="outline"
                            className="w-full gap-2"
                            disabled={subscriptionLoading}
                          >
                            {subscriptionLoading ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <>
                                <RefreshCw className="h-4 w-4" />
                                Refresh Status
                              </>
                            )}
                          </Button>
                        ) : (
                          <Button
                            onClick={() => handleManualPurchase(plan.packageId)}
                            variant="outline"
                            className={`w-full ${plan.btnClass}`}
                            disabled={purchaseLoading || subscriptionLoading}
                          >
                            {purchaseLoading || subscriptionLoading ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <>
                                <Crown className="h-4 w-4 mr-2" />
                                Choose {plan.name}
                              </>
                            )}
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>

            {/* Usage Stats */}
            {user && (
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
            )}

            {/* Subscription Management */}
            {isPro && customerInfo && (
              <Card className="mt-8 bg-dark-900/50 border-dark-700">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <CreditCard className="h-5 w-5" />
                    Subscription Details
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-dark-400">Status</span>
                    <span className="text-green-400 font-medium">Active</span>
                  </div>
                  {expiresDate && (
                    <div className="flex justify-between text-sm">
                      <span className="text-dark-400">Next renewal</span>
                      <span className="text-dark-200">{expiresDate}</span>
                    </div>
                  )}
                  <p className="text-xs text-dark-500 pt-2">
                    To manage or cancel your subscription, visit your payment provider&apos;s subscription management page.
                  </p>
                </CardContent>
              </Card>
            )}
        </>

        {/* FAQ */}
        <div className="mt-12 text-center text-sm text-dark-500">
          <p>Questions? Contact us at support@benchgoblin.ai</p>
          <p className="mt-2">Cancel anytime. No hidden fees.</p>
        </div>
      </div>
    </div>
  );
}
