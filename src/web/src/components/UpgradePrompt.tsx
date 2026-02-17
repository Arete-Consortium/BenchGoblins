'use client';

import { useRef, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles, Zap, Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAuthStore } from '@/stores/authStore';
import { useSubscriptionStore } from '@/stores/subscriptionStore';
import { presentPaywall } from '@/lib/revenuecat';

interface UpgradePromptProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const FREE_FEATURES = [
  '5 queries per week',
  'Basic fantasy analysis',
  'NBA, NFL, MLB, NHL, Soccer support',
];

const PRO_FEATURES = [
  'Unlimited queries',
  'Advanced AI analysis',
  'Priority response times',
  'Historical data access',
  'Custom risk profiles',
  'Export recommendations',
];

export function UpgradePrompt({ open, onOpenChange }: UpgradePromptProps) {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const { refreshCustomerInfo, isInitialized } = useSubscriptionStore();
  const [showPaywall, setShowPaywall] = useState(false);
  const [paywallLoading, setPaywallLoading] = useState(false);
  const paywallRef = useRef<HTMLDivElement>(null);

  const handleUpgrade = useCallback(async () => {
    if (!isAuthenticated) {
      router.push('/auth/login?redirect=/billing');
      onOpenChange(false);
      return;
    }

    // If RevenueCat isn't initialized, fall back to billing page
    if (!isInitialized) {
      router.push('/billing');
      onOpenChange(false);
      return;
    }

    // Show paywall inline in the dialog
    setShowPaywall(true);
    setPaywallLoading(true);

    // Wait for the DOM to update with the paywall container
    await new Promise((resolve) => setTimeout(resolve, 50));

    if (!paywallRef.current) {
      router.push('/billing');
      onOpenChange(false);
      return;
    }

    try {
      await presentPaywall(paywallRef.current);
      await refreshCustomerInfo();
      onOpenChange(false);
    } catch {
      // User cancelled or error — just close the paywall view
    } finally {
      setShowPaywall(false);
      setPaywallLoading(false);
    }
  }, [isAuthenticated, isInitialized, router, onOpenChange, refreshCustomerInfo]);

  const handleSignIn = () => {
    router.push('/auth/login');
    onOpenChange(false);
  };

  const handleClose = (isOpen: boolean) => {
    if (!isOpen) {
      setShowPaywall(false);
      setPaywallLoading(false);
    }
    onOpenChange(isOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className={showPaywall ? 'sm:max-w-2xl' : 'sm:max-w-md'}>
        {showPaywall ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-xl">
                <Sparkles className="h-5 w-5 text-primary-400" />
                Complete Your Upgrade
              </DialogTitle>
            </DialogHeader>
            <div ref={paywallRef} className="min-h-[300px]">
              {paywallLoading && (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-primary-400" />
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-xl">
                <Zap className="h-5 w-5 text-yellow-400" />
                Daily Limit Reached
              </DialogTitle>
              <DialogDescription>
                You&apos;ve used all 5 free queries for today. Upgrade to Pro for unlimited access.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6 py-4">
              {/* Comparison */}
              <div className="grid grid-cols-2 gap-4">
                {/* Free tier */}
                <div className="p-4 rounded-lg border border-dark-700 bg-dark-800/50">
                  <h4 className="font-medium text-dark-300 mb-3">Free</h4>
                  <ul className="space-y-2">
                    {FREE_FEATURES.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-dark-400">
                        <Check className="h-4 w-4 text-dark-500 shrink-0 mt-0.5" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Pro tier */}
                <div className="p-4 rounded-lg border border-primary-500/50 bg-primary-500/5">
                  <div className="flex items-center gap-2 mb-3">
                    <h4 className="font-medium text-primary-400">Pro</h4>
                    <span className="text-xs bg-primary-500/20 text-primary-400 px-2 py-0.5 rounded-full">
                      Popular
                    </span>
                  </div>
                  <ul className="space-y-2">
                    {PRO_FEATURES.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-dark-200">
                        <Check className="h-4 w-4 text-primary-400 shrink-0 mt-0.5" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Pricing */}
              <div className="text-center">
                <div className="text-3xl font-bold">
                  $9.99<span className="text-lg font-normal text-dark-400">/month</span>
                </div>
                <p className="text-sm text-dark-500 mt-1">Cancel anytime</p>
              </div>

              {/* Actions */}
              <div className="space-y-3">
                <Button
                  onClick={handleUpgrade}
                  className="w-full gap-2 h-12 bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-400 hover:to-primary-500"
                >
                  <Sparkles className="h-5 w-5" />
                  Upgrade to Pro
                </Button>

                {!isAuthenticated && (
                  <Button
                    onClick={handleSignIn}
                    variant="outline"
                    className="w-full border-dark-700 hover:bg-dark-800"
                  >
                    Sign in for free queries tomorrow
                  </Button>
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// Hook for managing upgrade prompt state
export function useUpgradePrompt() {
  const [isOpen, setIsOpen] = useState(false);

  const showUpgradePrompt = useCallback(() => {
    setIsOpen(true);
  }, []);

  const hideUpgradePrompt = useCallback(() => {
    setIsOpen(false);
  }, []);

  return {
    isOpen,
    setIsOpen,
    showUpgradePrompt,
    hideUpgradePrompt,
  };
}
