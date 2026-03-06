'use client';

import { useRouter } from 'next/navigation';
import { Zap, ArrowRight } from 'lucide-react';
import { useSubscriptionStore } from '@/stores/subscriptionStore';
import { useAuthStore } from '@/stores/authStore';

interface ProBannerProps {
  feature: string;
  compact?: boolean;
}

export function ProBanner({ feature, compact = false }: ProBannerProps) {
  const { isPro } = useSubscriptionStore();
  const { isAuthenticated } = useAuthStore();
  const router = useRouter();

  // Don't show if already pro or not signed in
  if (isPro || !isAuthenticated) return null;

  const handleClick = () => {
    router.push('/billing');
  };

  if (compact) {
    return (
      <button
        onClick={handleClick}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r from-yellow-500/10 to-primary-500/10 border border-yellow-500/20 text-sm hover:border-yellow-500/40 transition-all w-full"
      >
        <Zap className="w-4 h-4 text-yellow-400 flex-shrink-0" />
        <span className="text-dark-200">
          <span className="font-medium text-yellow-400">Upgrade to Pro</span>
          {' '}to unlock {feature}
        </span>
        <ArrowRight className="w-4 h-4 text-dark-500 ml-auto flex-shrink-0" />
      </button>
    );
  }

  return (
    <div className="relative overflow-hidden rounded-xl border border-yellow-500/20 bg-gradient-to-br from-yellow-500/5 via-primary-500/5 to-transparent p-6">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-lg bg-yellow-500/20 flex items-center justify-center flex-shrink-0">
          <Zap className="w-5 h-5 text-yellow-400" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-dark-100">
            Unlock {feature} with Pro
          </h3>
          <p className="text-sm text-dark-400 mt-1">
            Get unlimited queries, weekly verdicts, commissioner tools, and more for $9.99/month.
          </p>
          <button
            onClick={handleClick}
            className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-primary-500 to-primary-600 text-white text-sm font-medium hover:from-primary-400 hover:to-primary-500 transition-all"
          >
            Upgrade to Pro
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
