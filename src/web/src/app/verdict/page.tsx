'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import { useAppStore } from '@/stores/appStore';
import useAuthStore from '@/stores/authStore';
import api from '@/lib/api';
import { GoblinVerdict, RiskMode, SwapRecommendation } from '@/types';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Clock,
  RefreshCw,
  Share2,
  Shield,
  Sparkles,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { ShareCard, VerdictShareData } from '@/components/ShareCard';

// ---------------------------------------------------------------------------
// Risk Mode Config
// ---------------------------------------------------------------------------

const RISK_MODES: { key: RiskMode; label: string; desc: string; icon: typeof Shield; color: string }[] = [
  {
    key: 'floor',
    label: 'Floor',
    desc: 'Safe plays, guaranteed volume',
    icon: Shield,
    color: 'text-green-400 bg-green-500/20 border-green-500/30',
  },
  {
    key: 'median',
    label: 'Median',
    desc: 'Balanced, expected value',
    icon: TrendingUp,
    color: 'text-blue-400 bg-blue-500/20 border-blue-500/30',
  },
  {
    key: 'ceiling',
    label: 'Ceiling',
    desc: 'Max upside, chase the spike',
    icon: Zap,
    color: 'text-orange-400 bg-orange-500/20 border-orange-500/30',
  },
];

const URGENCY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  critical: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'CRITICAL' },
  recommended: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: 'RECOMMENDED' },
  optional: { bg: 'bg-dark-600/50', text: 'text-dark-300', label: 'OPTIONAL' },
};

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function SwapCard({ swap }: { swap: SwapRecommendation }) {
  const urgency = URGENCY_STYLES[swap.urgency] || URGENCY_STYLES.recommended;

  return (
    <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-5 hover:border-dark-600 transition-all">
      {/* Urgency + Confidence header */}
      <div className="flex items-center justify-between mb-3">
        <span className={`text-xs font-bold px-2 py-0.5 rounded ${urgency.bg} ${urgency.text}`}>
          {urgency.label}
        </span>
        <span className="text-sm text-dark-400">
          Confidence: <span className="text-white font-semibold">{swap.confidence}%</span>
        </span>
      </div>

      {/* Swap visual */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex-1">
          <p className="text-xs text-dark-500 uppercase tracking-wider">Bench</p>
          <p className="text-lg font-bold text-red-400">{swap.bench_player}</p>
        </div>
        <ArrowRight className="w-5 h-5 text-dark-500 flex-shrink-0" />
        <div className="flex-1 text-right">
          <p className="text-xs text-dark-500 uppercase tracking-wider">Start</p>
          <p className="text-lg font-bold text-green-400">{swap.start_player}</p>
        </div>
      </div>

      {/* Reasoning */}
      <p className="text-sm text-dark-300 leading-relaxed italic">
        &ldquo;{swap.reasoning}&rdquo;
      </p>

      {/* Confidence bar */}
      <div className="mt-3 h-1.5 bg-dark-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${swap.confidence}%`,
            backgroundColor: swap.confidence >= 75 ? '#4ade80' : swap.confidence >= 60 ? '#facc15' : '#f87171',
          }}
        />
      </div>
    </div>
  );
}

function RiskModeSelector({
  selected,
  onSelect,
  disabled,
}: {
  selected: RiskMode;
  onSelect: (mode: RiskMode) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex gap-2">
      {RISK_MODES.map((mode) => {
        const Icon = mode.icon;
        const isSelected = selected === mode.key;
        return (
          <button
            key={mode.key}
            onClick={() => onSelect(mode.key)}
            disabled={disabled}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-all
              ${isSelected
                ? mode.color
                : 'border-dark-700 text-dark-400 hover:border-dark-600 hover:text-dark-300'
              }
              ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
          >
            <Icon className="w-4 h-4" />
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}

function VerdictSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-8 bg-dark-700 rounded w-3/4" />
      <div className="h-5 bg-dark-700 rounded w-1/2" />
      <div className="space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="bg-dark-800/50 border border-dark-700 rounded-xl p-5 space-y-3">
            <div className="h-4 bg-dark-700 rounded w-1/4" />
            <div className="h-6 bg-dark-700 rounded w-2/3" />
            <div className="h-12 bg-dark-700 rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-16">
      <Sparkles className="w-16 h-16 text-dark-600 mx-auto mb-4" />
      <h2 className="text-2xl font-bold mb-2">The Goblin awaits your roster</h2>
      <p className="text-dark-400 mb-6 max-w-md mx-auto">
        Connect your Sleeper league to get a personalized lineup verdict
        with swap recommendations every week.
      </p>
      <Link
        href="/leagues"
        className="inline-flex items-center gap-2 px-6 py-3 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-600 transition-colors"
      >
        Connect League
        <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function VerdictPage() {
  const { isAuthenticated } = useAuthStore();
  const { riskMode: appRiskMode, setRiskMode: setAppRiskMode } = useAppStore();

  const [verdict, setVerdict] = useState<GoblinVerdict | null>(null);
  const [loading, setLoading] = useState(isAuthenticated);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [riskMode, setRiskMode] = useState<RiskMode>(appRiskMode);
  const [showShareCard, setShowShareCard] = useState(false);

  const fetchVerdict = useCallback(async (mode: RiskMode, forceGenerate = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = forceGenerate
        ? await api.generateGoblinVerdict(mode)
        : await api.getGoblinVerdict(mode);
      setVerdict(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load verdict';
      // 404 = no league connected
      if (typeof err === 'object' && err !== null && 'response' in err) {
        const resp = (err as { response?: { status?: number; data?: { detail?: string } } }).response;
        if (resp?.status === 404) {
          setVerdict(null);
          setError(null); // Show empty state, not error
          return;
        }
        if (resp?.status === 403) {
          // Pro gate — the global UpgradePrompt handles the dialog
          setVerdict(null);
          setError(null);
          return;
        }
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchVerdict(riskMode);
  }, [isAuthenticated, riskMode, fetchVerdict]);

  const handleRiskModeChange = (mode: RiskMode) => {
    setRiskMode(mode);
    setAppRiskMode(mode);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchVerdict(riskMode, true);
    setRefreshing(false);
  };

  const handleShare = () => {
    if (!verdict || verdict.swaps.length === 0) return;
    setShowShareCard(true);
  };

  const shareCardData: VerdictShareData | null = verdict && verdict.swaps.length > 0
    ? {
        type: 'verdict',
        headline: verdict.verdict_headline,
        teamName: verdict.team_name ?? undefined,
        week: verdict.week,
        riskMode,
        swaps: verdict.swaps.map((s) => ({
          bench: s.bench_player,
          start: s.start_player,
          confidence: s.confidence,
        })),
      }
    : null;

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="pt-20 pb-8 px-4">
          <div className="max-w-4xl mx-auto text-center py-16">
            <Sparkles className="w-16 h-16 text-dark-600 mx-auto mb-4" />
            <h1 className="text-3xl font-bold mb-2">Sign in to see your verdict</h1>
            <p className="text-dark-400 mb-6">The Goblin needs to know your roster first.</p>
            <Link
              href="/auth/login"
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-600 transition-colors"
            >
              Sign In
            </Link>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
            <div>
              <div className="flex items-center gap-2 text-green-400 text-xs font-bold uppercase tracking-widest mb-1">
                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                The Goblin Has Spoken
              </div>
              <h1 className="text-3xl font-bold">
                {verdict ? `Week ${verdict.week} Verdict` : 'Goblin Verdict'}
              </h1>
              {verdict?.team_name && (
                <p className="text-dark-400 mt-0.5">for {verdict.team_name}</p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleRefresh}
                disabled={refreshing || loading}
                className="flex items-center gap-2 px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-sm text-dark-300 hover:text-white hover:border-dark-600 transition-all disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                {refreshing ? 'Generating...' : 'Refresh'}
              </button>
              {verdict && verdict.swaps.length > 0 && (
                <button
                  onClick={handleShare}
                  className="flex items-center gap-2 px-3 py-2 bg-primary-500/20 border border-primary-500/30 rounded-lg text-sm text-primary-400 hover:bg-primary-500/30 transition-all"
                >
                  <Share2 className="w-4 h-4" />
                  Share
                </button>
              )}
            </div>
          </div>

          {/* Risk Mode Selector */}
          <div className="mb-6">
            <RiskModeSelector
              selected={riskMode}
              onSelect={handleRiskModeChange}
              disabled={loading || refreshing}
            />
          </div>

          {/* Content */}
          {loading ? (
            <VerdictSkeleton />
          ) : error ? (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
              <AlertTriangle className="w-10 h-10 text-red-400 mx-auto mb-3" />
              <p className="text-red-400 font-medium">{error}</p>
              <button
                onClick={() => fetchVerdict(riskMode)}
                className="mt-3 text-sm text-dark-400 hover:text-white"
              >
                Try again
              </button>
            </div>
          ) : !verdict ? (
            <EmptyState />
          ) : (
            <div className="space-y-6">
              {/* Headline Card */}
              <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                <div className="flex items-start gap-3">
                  {verdict.swaps.length > 0 ? (
                    <AlertTriangle className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" />
                  ) : (
                    <CheckCircle className="w-6 h-6 text-green-400 flex-shrink-0 mt-0.5" />
                  )}
                  <div>
                    <h2 className="text-xl font-bold">{verdict.verdict_headline}</h2>
                    {verdict.overall_outlook && (
                      <p className="text-dark-300 mt-2 leading-relaxed">{verdict.overall_outlook}</p>
                    )}
                  </div>
                </div>

                {/* Meta */}
                <div className="flex items-center gap-4 mt-4 pt-4 border-t border-dark-700 text-xs text-dark-500">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(verdict.generated_at).toLocaleString()}
                  </span>
                  {verdict.cached && (
                    <span className="flex items-center gap-1 text-green-500">
                      <Zap className="w-3 h-3" />
                      Pre-generated
                    </span>
                  )}
                </div>
              </div>

              {/* Swap Cards */}
              {verdict.swaps.length > 0 ? (
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                    <ArrowRight className="w-5 h-5 text-primary-400" />
                    Swap Recommendations ({verdict.swaps.length})
                  </h3>
                  <div className="space-y-4">
                    {verdict.swaps.map((swap, i) => (
                      <SwapCard key={i} swap={swap} />
                    ))}
                  </div>
                </div>
              ) : (
                <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-6 text-center">
                  <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-3" />
                  <p className="text-green-400 font-medium text-lg">Your lineup looks solid</p>
                  <p className="text-dark-400 text-sm mt-1">
                    The Goblin has no swaps to recommend this week. Ride your starters.
                  </p>
                </div>
              )}

              {/* Full Lineup link */}
              <div className="flex justify-center pt-4">
                <Link
                  href="/leagues"
                  className="text-sm text-dark-400 hover:text-primary-400 transition-colors"
                >
                  View Full Roster &rarr;
                </Link>
              </div>
            </div>
          )}
        </div>
      </main>

      {showShareCard && shareCardData && (
        <ShareCard data={shareCardData} onClose={() => setShowShareCard(false)} />
      )}
    </div>
  );
}
