'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { ArrowLeft, ArrowRight, Link2, Check, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SportSelector } from '@/components/SportSelector';
import { RiskModeSelector } from '@/components/RiskModeSelector';
import { LeagueConnectDialog } from '@/components/LeagueConnectDialog';
import { useAppStore } from '@/stores/appStore';
import { useAuthStore } from '@/stores/authStore';
import { useLeagueStore } from '@/stores/leagueStore';
import { cn, getSportDisplayName } from '@/lib/utils';
import type { Sport } from '@/types';

const SPORT_ICONS: Record<Sport, string> = {
  nba: '🏀',
  nfl: '🏈',
  mlb: '⚾',
  nhl: '🏒',
  soccer: '⚽',
};

const RISK_LABELS: Record<string, string> = {
  floor: 'Floor (safe picks)',
  median: 'Median (balanced)',
  ceiling: 'Ceiling (high upside)',
};

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={cn(
            'w-2 h-2 rounded-full transition-all',
            i === current ? 'w-6 bg-primary-500' : i < current ? 'bg-primary-600' : 'bg-dark-600'
          )}
        />
      ))}
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const { isAuthenticated, onboardingComplete, completeOnboarding } = useAuthStore();
  const { sport, riskMode, setSport, setRiskMode } = useAppStore();
  const { connection, selectedLeagueIds } = useLeagueStore();

  const [step, setStep] = useState(0);
  const [leagueDialogOpen, setLeagueDialogOpen] = useState(false);

  // Guards
  useEffect(() => {
    if (!isAuthenticated) {
      router.replace('/auth/login');
    } else if (onboardingComplete) {
      router.replace('/ask');
    }
  }, [isAuthenticated, onboardingComplete, router]);

  const handleSkip = () => {
    completeOnboarding();
    router.push('/ask');
  };

  const handleFinish = () => {
    completeOnboarding();
    router.push('/ask');
  };

  const isLeagueConnected = !!(connection && selectedLeagueIds[sport]);

  // Don't render while redirecting
  if (!isAuthenticated || onboardingComplete) return null;

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950">
      {/* Header */}
      <div className="flex items-center justify-between p-4">
        <div className="flex items-center gap-2">
          <Image src="/logo.png" alt="Bench Goblins" width={32} height={32} className="rounded" />
          <span className="text-lg font-bold gradient-text">Bench Goblins</span>
        </div>
        <button onClick={handleSkip} className="text-sm text-dark-400 hover:text-dark-200 transition-colors">
          Skip setup
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          {/* Step indicator */}
          <div className="flex justify-center mb-8">
            <StepIndicator current={step} total={3} />
          </div>

          {/* Step 1: Sport & Risk Mode */}
          {step === 0 && (
            <div className="space-y-8">
              <div className="text-center">
                <h1 className="text-3xl font-bold mb-2">Welcome to Bench Goblins</h1>
                <p className="text-dark-400">Pick your sport and play style to get started.</p>
              </div>

              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-dark-300 mb-3">
                    What sport do you play?
                  </label>
                  <SportSelector value={sport} onChange={setSport} />
                </div>

                <div>
                  <label className="block text-sm font-medium text-dark-300 mb-3">
                    How do you like to play?
                  </label>
                  <RiskModeSelector value={riskMode} onChange={setRiskMode} />
                </div>
              </div>

              <Button onClick={() => setStep(1)} className="w-full gap-2">
                Continue
                <ArrowRight className="w-4 h-4" />
              </Button>
            </div>
          )}

          {/* Step 2: Connect League */}
          {step === 1 && (
            <div className="space-y-8">
              <div className="text-center">
                <h1 className="text-3xl font-bold mb-2">Connect Your League</h1>
                <p className="text-dark-400">
                  Import your roster for personalized {getSportDisplayName(sport)} recommendations.
                </p>
              </div>

              <div className="space-y-3">
                {(['sleeper', 'espn', 'yahoo'] as const).map((platform) => {
                  const labels = { sleeper: 'Sleeper', espn: 'ESPN Fantasy', yahoo: 'Yahoo Fantasy' };
                  const connected = platform === 'sleeper' && isLeagueConnected;
                  return (
                    <button
                      key={platform}
                      onClick={() => setLeagueDialogOpen(true)}
                      className={cn(
                        'w-full flex items-center gap-4 p-4 rounded-xl border-2 transition-all text-left',
                        connected
                          ? 'border-primary-500 bg-primary-500/10'
                          : 'border-dark-700 bg-dark-800/50 hover:border-dark-600'
                      )}
                    >
                      <Link2 className={cn('w-5 h-5', connected ? 'text-primary-400' : 'text-dark-400')} />
                      <div className="flex-1">
                        <div className="font-medium">{labels[platform]}</div>
                        {connected && (
                          <div className="text-xs text-primary-400 mt-0.5">Connected</div>
                        )}
                      </div>
                      {connected ? (
                        <Check className="w-5 h-5 text-primary-400" />
                      ) : (
                        <ArrowRight className="w-4 h-4 text-dark-500" />
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep(0)} className="gap-2">
                  <ArrowLeft className="w-4 h-4" />
                  Back
                </Button>
                <Button onClick={() => setStep(2)} className="flex-1 gap-2">
                  {isLeagueConnected ? 'Continue' : 'Skip for now'}
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Summary */}
          {step === 2 && (
            <div className="space-y-8">
              <div className="text-center">
                <div className="w-16 h-16 rounded-2xl bg-primary-600/20 flex items-center justify-center mx-auto mb-4">
                  <Sparkles className="w-8 h-8 text-primary-400" />
                </div>
                <h1 className="text-3xl font-bold mb-2">You&apos;re All Set!</h1>
                <p className="text-dark-400">Here&apos;s what we&apos;ve got for you.</p>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-3 p-4 rounded-xl bg-dark-800/50 border border-dark-700">
                  <span className="text-2xl">{SPORT_ICONS[sport]}</span>
                  <div>
                    <div className="font-medium">{getSportDisplayName(sport)}</div>
                    <div className="text-xs text-dark-400">Default sport</div>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-4 rounded-xl bg-dark-800/50 border border-dark-700">
                  <div className="w-8 h-8 rounded-lg bg-dark-700 flex items-center justify-center text-sm">
                    {riskMode === 'floor' ? '🛡' : riskMode === 'median' ? '🎯' : '🚀'}
                  </div>
                  <div>
                    <div className="font-medium">{RISK_LABELS[riskMode]}</div>
                    <div className="text-xs text-dark-400">Risk mode</div>
                  </div>
                </div>
                {isLeagueConnected && (
                  <div className="flex items-center gap-3 p-4 rounded-xl bg-dark-800/50 border border-dark-700">
                    <Link2 className="w-6 h-6 text-primary-400" />
                    <div>
                      <div className="font-medium">{connection?.sleeperUsername}</div>
                      <div className="text-xs text-dark-400">Sleeper league connected</div>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep(1)} className="gap-2">
                  <ArrowLeft className="w-4 h-4" />
                  Back
                </Button>
                <Button onClick={handleFinish} className="flex-1 gap-2">
                  Start Asking
                  <Sparkles className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <LeagueConnectDialog open={leagueDialogOpen} onOpenChange={setLeagueDialogOpen} />
    </div>
  );
}
