'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles, Zap, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAuthStore } from '@/stores/authStore';

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
  'Weekly Goblin Verdicts',
  'Trash talk generator',
  'Weekly recaps & highlights',
  'Commissioner tools & alerts',
  'Start/sit AI analysis',
];

export function UpgradePrompt({ open, onOpenChange }: UpgradePromptProps) {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();

  const handleUpgrade = useCallback(() => {
    if (!isAuthenticated) {
      router.push('/auth/login?redirect=/billing');
    } else {
      router.push('/billing');
    }
    onOpenChange(false);
  }, [isAuthenticated, router, onOpenChange]);

  const handleSignIn = () => {
    router.push('/auth/login');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-xl">
                <Zap className="h-5 w-5 text-yellow-400" />
                Unlock Pro Features
              </DialogTitle>
              <DialogDescription>
                This feature requires a Pro subscription. Upgrade to unlock verdicts, recaps, commissioner tools, and more.
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
