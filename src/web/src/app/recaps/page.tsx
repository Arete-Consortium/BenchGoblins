'use client';

import { useEffect, useState, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import { cn, getSportDisplayName } from '@/lib/utils';
import { useAuthStore } from '@/stores/authStore';
import { useSubscriptionStore } from '@/stores/subscriptionStore';
import api from '@/lib/api';
import type { WeeklyRecap, Sport } from '@/types';
import {
  BookOpen,
  TrendingUp,
  CheckCircle,
  XCircle,
  Clock,
  Sparkles,
  RefreshCw,
} from 'lucide-react';
import { ProBanner } from '@/components/ProBanner';

function formatWeekRange(start: string, end: string): string {
  try {
    const s = new Date(start);
    const e = new Date(end);
    const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
    return `${s.toLocaleDateString('en-US', opts)} - ${e.toLocaleDateString('en-US', { ...opts, year: 'numeric' })}`;
  } catch {
    return 'Unknown week';
  }
}

function StatCard({ label, value, icon: Icon, color }: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="flex items-center gap-3 p-3 bg-dark-800/50 border border-dark-700 rounded-lg">
      <Icon className={cn('w-5 h-5', color)} />
      <div>
        <p className="text-xs text-dark-400">{label}</p>
        <p className="text-lg font-bold text-dark-100">{value}</p>
      </div>
    </div>
  );
}

function RecapCard({ recap }: { recap: WeeklyRecap }) {
  const [expanded, setExpanded] = useState(false);
  const decided = recap.correct_decisions + recap.incorrect_decisions;

  return (
    <div className="bg-dark-800/50 border border-dark-700 rounded-xl overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 text-left hover:bg-dark-700/30 transition-colors"
      >
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-dark-100">
              {formatWeekRange(recap.week_start, recap.week_end)}
            </h3>
            <p className="text-sm text-dark-400 mt-0.5">
              {recap.total_decisions} decisions
              {recap.most_asked_sport && (
                <> &middot; Most active: {getSportDisplayName(recap.most_asked_sport as Sport)}</>
              )}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {recap.accuracy_pct !== null && (
              <span className={cn(
                'text-xl font-bold',
                recap.accuracy_pct >= 60 ? 'text-green-400' :
                recap.accuracy_pct >= 40 ? 'text-yellow-400' : 'text-red-400'
              )}>
                {recap.accuracy_pct}%
              </span>
            )}
            <BookOpen className={cn(
              'w-5 h-5 transition-transform text-dark-400',
              expanded && 'rotate-90'
            )} />
          </div>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-dark-700">
          {/* Stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
            <StatCard label="Correct" value={recap.correct_decisions} icon={CheckCircle} color="text-green-400" />
            <StatCard label="Incorrect" value={recap.incorrect_decisions} icon={XCircle} color="text-red-400" />
            <StatCard label="Pending" value={recap.pending_decisions} icon={Clock} color="text-yellow-400" />
            <StatCard
              label="Accuracy"
              value={decided > 0 ? `${recap.accuracy_pct}%` : 'N/A'}
              icon={TrendingUp}
              color="text-primary-400"
            />
          </div>

          {/* Highlights */}
          {recap.highlights && (
            <div className="mt-4 p-3 bg-dark-900/50 border border-dark-600 rounded-lg">
              <p className="text-sm text-dark-300">{recap.highlights}</p>
            </div>
          )}

          {/* AI Narrative */}
          <div className="mt-4 prose prose-invert prose-sm max-w-none">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-4 h-4 text-primary-400" />
              <span className="text-xs font-medium text-primary-400 uppercase tracking-wide">
                AI Analysis
              </span>
            </div>
            <div
              className="text-dark-200 leading-relaxed whitespace-pre-wrap"
              dangerouslySetInnerHTML={{
                __html: recap.narrative
                  .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                  .replace(/\n/g, '<br />')
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default function RecapsPage() {
  const { isAuthenticated } = useAuthStore();
  const { isPro } = useSubscriptionStore();
  const [recaps, setRecaps] = useState<WeeklyRecap[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRecaps = useCallback(async () => {
    if (!isAuthenticated) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getWeeklyRecaps();
      setRecaps(data);
    } catch (err: unknown) {
      // 403 = pro gate — global UpgradePrompt handles it
      if (typeof err === 'object' && err !== null && 'response' in err) {
        const resp = (err as { response?: { status?: number } }).response;
        if (resp?.status === 403) {
          setError(null);
          return;
        }
      }
      console.error('Failed to fetch recaps:', err);
      setError('Failed to load recaps');
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchRecaps();
  }, [fetchRecaps]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const recap = await api.generateWeeklyRecap();
      if (recap) {
        // Add to top of list or replace existing for same week
        setRecaps((prev) => {
          const filtered = prev.filter((r) => r.week_start !== recap.week_start);
          return [recap, ...filtered];
        });
      } else {
        setError('No decisions found this week. Make some calls first!');
      }
    } catch (err: unknown) {
      if (typeof err === 'object' && err !== null && 'response' in err) {
        const resp = (err as { response?: { status?: number } }).response;
        if (resp?.status === 403) {
          setError(null);
          return;
        }
      }
      const msg = (err instanceof Error ? err.message : null) || 'Failed to generate recap';
      setError(msg);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="text-3xl font-bold">Weekly Recaps</h1>
              <p className="text-dark-400 mt-1">
                AI-generated analysis of your fantasy decisions
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={fetchRecaps}
                disabled={isLoading}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 rounded-lg',
                  'bg-dark-800 text-dark-300 hover:bg-dark-700 transition-all',
                  isLoading && 'opacity-50 cursor-not-allowed'
                )}
              >
                <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
                Refresh
              </button>
              {isPro && (
                <button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg',
                    'bg-primary-600 text-white hover:bg-primary-500 transition-all',
                    isGenerating && 'opacity-50 cursor-not-allowed'
                  )}
                >
                  <Sparkles className={cn('w-4 h-4', isGenerating && 'animate-pulse')} />
                  {isGenerating ? 'Generating...' : 'Generate This Week'}
                </button>
              )}
            </div>
          </div>

          {/* Pro gate */}
          <div className="mb-6">
            <ProBanner feature="weekly AI recaps" />
          </div>

          {/* Not authenticated */}
          {!isAuthenticated && (
            <div className="text-center py-16">
              <BookOpen className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">Sign in to view recaps</h2>
              <p className="text-dark-500 mt-2">
                Weekly recaps are personalized to your decision history.
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-4 p-4 bg-red-900/20 border border-red-700/50 rounded-xl text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Loading skeleton */}
          {isLoading && recaps.length === 0 && (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 animate-pulse">
                  <div className="h-5 bg-dark-700 rounded w-1/3 mb-3" />
                  <div className="h-4 bg-dark-700 rounded w-1/2" />
                </div>
              ))}
            </div>
          )}

          {/* Recaps list */}
          {isAuthenticated && isPro && !isLoading && recaps.length === 0 && !error && (
            <div className="text-center py-16">
              <BookOpen className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">No recaps yet</h2>
              <p className="text-dark-500 mt-2">
                Click &quot;Generate This Week&quot; to create your first weekly recap.
              </p>
            </div>
          )}

          {recaps.length > 0 && (
            <div className="space-y-4">
              {recaps.map((recap) => (
                <RecapCard key={recap.id} recap={recap} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
