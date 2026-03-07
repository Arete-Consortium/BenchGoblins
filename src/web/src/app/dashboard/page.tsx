'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

// Actual shape from /health endpoint (flat, not nested)
interface HealthData {
  status: string;
  postgres_connected?: boolean;
  redis_connected?: boolean;
  claude_available?: boolean;
  sentry_enabled?: boolean;
}

// Actual shape returned by /usage endpoint
interface UsageResponse {
  today?: { input_tokens: number; output_tokens: number; total_decisions: number; estimated_cost_usd: number };
  this_week?: { input_tokens: number; output_tokens: number; total_decisions: number; estimated_cost_usd: number };
  error?: string;
}

interface AccuracyLeader {
  accuracy_pct: number;
  total_decisions: number;
  correct: number;
}

interface AccuracyMetrics {
  total_decisions: number;
  decisions_with_outcomes: number;
  correct_decisions: number;
  incorrect_decisions: number;
  pushes: number;
  accuracy_pct: number;
  coverage_pct: number;
  by_confidence: Record<string, { total: number; correct: number; accuracy: number }>;
  by_source: Record<string, { total: number; correct: number }>;
  by_sport: Record<string, { total: number; correct: number }>;
}

import {
  MessageSquare,
  TrendingUp,
  Zap,
  Activity,
  Server,
  CheckCircle,
  XCircle,
  Trophy,
  Crown,
  Target,
  BarChart3,
  Layers,
  Loader2,
  RefreshCw,
  Trash2,
  BookOpen,
  Sparkles,
} from 'lucide-react';

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-dark-400 text-sm">{title}</p>
          <p className="text-3xl font-bold mt-1">{value}</p>
          {subtitle && <p className="text-dark-500 text-sm mt-1">{subtitle}</p>}
        </div>
        <div className={`w-12 h-12 rounded-xl ${color} flex items-center justify-center`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  );
}

function StatusIndicator({ status, label }: { status: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      {status ? (
        <CheckCircle className="w-4 h-4 text-green-400" />
      ) : (
        <XCircle className="w-4 h-4 text-red-400" />
      )}
      <span className="text-sm text-dark-300">{label}</span>
    </div>
  );
}

function ConfidenceBar({
  level,
  total,
  correct,
  accuracy,
}: {
  level: string;
  total: number;
  correct: number;
  accuracy: number;
}) {
  const colors: Record<string, string> = {
    high: 'bg-green-500',
    medium: 'bg-yellow-500',
    low: 'bg-red-500',
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="capitalize font-medium">{level}</span>
        <span className="text-dark-400">
          {correct}/{total} ({accuracy.toFixed(0)}%)
        </span>
      </div>
      <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', colors[level] || 'bg-primary-500')}
          style={{ width: `${total > 0 ? accuracy : 0}%` }}
        />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { messages } = useAppStore();
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [topAccuracy, setTopAccuracy] = useState<AccuracyLeader | null>(null);
  const [loading, setLoading] = useState(true);

  // Accuracy section state
  const [accuracyData, setAccuracyData] = useState<AccuracyMetrics | null>(null);
  const [accuracyLoading, setAccuracyLoading] = useState(true);
  const [accuracyError, setAccuracyError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        const [usageData, healthData, accuracyLeaders] = await Promise.all([
          api.getUsage().catch(() => null),
          api.getHealth().catch(() => null),
          api.getAccuracyLeaders({ limit: 1 }).catch(() => null),
        ]);
        setUsage(usageData as UsageResponse | null);
        setHealth(healthData as HealthData | null);
        if (accuracyLeaders?.leaders?.length) {
          const top = accuracyLeaders.leaders[0];
          setTopAccuracy({
            accuracy_pct: top.accuracy_pct,
            total_decisions: top.total_decisions,
            correct: top.correct,
          });
        }
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const fetchAccuracyMetrics = useCallback(async () => {
    setAccuracyLoading(true);
    setAccuracyError(null);
    try {
      const metrics = await api.getAccuracyMetrics();
      setAccuracyData(metrics);
    } catch {
      setAccuracyError('Failed to load accuracy metrics.');
    } finally {
      setAccuracyLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccuracyMetrics();
  }, [fetchAccuracyMetrics]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await api.syncOutcomes(2);
      await fetchAccuracyMetrics();
    } catch {
      setAccuracyError('Failed to sync outcomes.');
    } finally {
      setSyncing(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Reset all your accuracy data? This cannot be undone.')) return;
    setResetting(true);
    try {
      await api.resetAccuracy();
      await fetchAccuracyMetrics();
    } catch {
      setAccuracyError('Failed to reset accuracy data.');
    } finally {
      setResetting(false);
    }
  };

  const todayQueries = messages.filter((m) => {
    const today = new Date();
    const messageDate = new Date(m.timestamp);
    return (
      m.role === 'user' &&
      messageDate.toDateString() === today.toDateString()
    );
  }).length;

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold">Dashboard</h1>
            <p className="text-dark-400 mt-1">Your fantasy decision analytics</p>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard
              title="Queries Today"
              value={usage?.today?.total_decisions ?? todayQueries}
              subtitle="decisions today"
              icon={MessageSquare}
              color="bg-primary-500/20 text-primary-400"
            />
            <StatCard
              title="Session Messages"
              value={messages.length}
              subtitle="This session"
              icon={Activity}
              color="bg-blue-500/20 text-blue-400"
            />
            <StatCard
              title="Tokens Used"
              value={usage?.today ? (usage.today.input_tokens + usage.today.output_tokens).toLocaleString() : '—'}
              subtitle={usage?.today ? `$${usage.today.estimated_cost_usd.toFixed(4)}` : undefined}
              icon={Zap}
              color="bg-orange-500/20 text-orange-400"
            />
            <StatCard
              title="Top Accuracy"
              value={topAccuracy ? `${topAccuracy.accuracy_pct.toFixed(0)}%` : '—'}
              subtitle={topAccuracy ? `${topAccuracy.correct}/${topAccuracy.total_decisions} correct` : 'No decisions yet'}
              icon={TrendingUp}
              color="bg-green-500/20 text-green-400"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Quick Actions */}
            <div className="lg:col-span-2 bg-dark-800/50 border border-dark-700 rounded-xl p-6">
              <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <Link
                  href="/ask"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <MessageSquare className="w-5 h-5 text-primary-400" />
                  <div>
                    <div className="font-medium">New Decision</div>
                    <div className="text-sm text-dark-400">Ask a question</div>
                  </div>
                </Link>
                <Link
                  href="/verdict"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <Sparkles className="w-5 h-5 text-purple-400" />
                  <div>
                    <div className="font-medium">Verdict</div>
                    <div className="text-sm text-dark-400">AI analysis</div>
                  </div>
                </Link>
                <Link
                  href="/leaderboard"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <Trophy className="w-5 h-5 text-yellow-400" />
                  <div>
                    <div className="font-medium">Leaderboard</div>
                    <div className="text-sm text-dark-400">Player rankings</div>
                  </div>
                </Link>
                <Link
                  href="/recaps"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <BookOpen className="w-5 h-5 text-blue-400" />
                  <div>
                    <div className="font-medium">Recaps</div>
                    <div className="text-sm text-dark-400">Game summaries</div>
                  </div>
                </Link>
                <Link
                  href="/commissioner"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <Crown className="w-5 h-5 text-purple-400" />
                  <div>
                    <div className="font-medium">Commissioner</div>
                    <div className="text-sm text-dark-400">League tools</div>
                  </div>
                </Link>
                <Link
                  href="/dossier"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <Activity className="w-5 h-5 text-orange-400" />
                  <div>
                    <div className="font-medium">Dossier</div>
                    <div className="text-sm text-dark-400">Player intel</div>
                  </div>
                </Link>
              </div>
            </div>

            {/* System Status */}
            <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
              <h2 className="text-xl font-semibold mb-4">System Status</h2>
              {loading ? (
                <div className="space-y-3 animate-pulse">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="h-6 bg-dark-700 rounded" />
                  ))}
                </div>
              ) : health ? (
                <div className="space-y-3">
                  <StatusIndicator status={!!health.postgres_connected} label="Database" />
                  <StatusIndicator status={!!health.redis_connected} label="Cache (Redis)" />
                  <StatusIndicator status={!!health.claude_available} label="Claude AI" />
                  <div className="pt-3 border-t border-dark-700 mt-3">
                    <div className="flex items-center gap-2">
                      <Server className="w-4 h-4 text-dark-400" />
                      <span className="text-sm">
                        Overall:{' '}
                        <span
                          className={
                            health.status === 'healthy'
                              ? 'text-green-400'
                              : health.status === 'degraded'
                              ? 'text-yellow-400'
                              : 'text-red-400'
                          }
                        >
                          {health.status.toUpperCase()}
                        </span>
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-dark-500 text-sm">Unable to fetch status</p>
              )}
            </div>
          </div>

          {/* Five-Index System Explainer */}
          <div className="mt-8 bg-dark-800/50 border border-dark-700 rounded-xl p-6">
            <h2 className="text-xl font-semibold mb-4">The Five-Index System</h2>
            <p className="text-dark-400 mb-6">
              BenchGoblin uses five qualitative indices to evaluate fantasy decisions,
              moving beyond simple projections to capture role stability, spatial opportunity,
              and matchup context.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              {[
                { name: 'SCI', title: 'Space Creation', desc: 'Ability to create scoring opportunities' },
                { name: 'RMI', title: 'Role Motion', desc: 'Dependence on scheme and teammates' },
                { name: 'GIS', title: 'Gravity Impact', desc: 'Defensive attention drawn' },
                { name: 'OD', title: 'Opportunity Delta', desc: 'Trends in usage and minutes' },
                { name: 'MSF', title: 'Matchup Space Fit', desc: 'Exploitable defensive weaknesses' },
              ].map((index) => (
                <div key={index.name} className="p-4 rounded-lg bg-dark-700/50">
                  <div className="text-primary-400 font-mono font-bold">{index.name}</div>
                  <div className="font-medium text-sm mt-1">{index.title}</div>
                  <div className="text-xs text-dark-400 mt-1">{index.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Accuracy Section */}
          <div className="mt-8">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-2xl font-bold">Accuracy</h2>
                <p className="text-dark-400 mt-1">How well is the Goblin doing?</p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  onClick={handleReset}
                  disabled={resetting || accuracyLoading}
                  variant="outline"
                  size="sm"
                  className="gap-2 border-red-500/30 text-red-400 hover:bg-red-500/10"
                >
                  {resetting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Reset
                </Button>
                <Button
                  onClick={handleSync}
                  disabled={syncing}
                  variant="outline"
                  size="sm"
                  className="gap-2"
                >
                  {syncing ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  Sync Outcomes
                </Button>
              </div>
            </div>

            {accuracyLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-primary-400" />
              </div>
            ) : accuracyError ? (
              <div className="text-center py-12 text-dark-400">{accuracyError}</div>
            ) : accuracyData ? (
              <div className="space-y-6">
                {/* Accuracy stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-2">
                      <Target className={cn('h-4 w-4', 'text-green-400')} />
                      <span className="text-sm text-dark-400">Win Rate</span>
                    </div>
                    <div className="text-3xl font-bold">{accuracyData.accuracy_pct.toFixed(1)}%</div>
                    <div className="text-sm text-dark-500 mt-1">{accuracyData.correct_decisions} correct</div>
                  </div>
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-2">
                      <BarChart3 className="h-4 w-4 text-primary-400" />
                      <span className="text-sm text-dark-400">Decisions</span>
                    </div>
                    <div className="text-3xl font-bold">{accuracyData.total_decisions}</div>
                    <div className="text-sm text-dark-500 mt-1">{accuracyData.decisions_with_outcomes} with outcomes</div>
                  </div>
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-2">
                      <Layers className="h-4 w-4 text-blue-400" />
                      <span className="text-sm text-dark-400">Coverage</span>
                    </div>
                    <div className="text-3xl font-bold">{accuracyData.coverage_pct.toFixed(0)}%</div>
                    <div className="text-sm text-dark-500 mt-1">outcomes recorded</div>
                  </div>
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp className="h-4 w-4 text-yellow-400" />
                      <span className="text-sm text-dark-400">Pushes</span>
                    </div>
                    <div className="text-3xl font-bold">{accuracyData.pushes}</div>
                    <div className="text-sm text-dark-500 mt-1">within 1 point</div>
                  </div>
                </div>

                {/* Confidence breakdown */}
                <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                  <h3 className="text-lg font-semibold mb-4">By Confidence</h3>
                  <div className="space-y-4">
                    {(['high', 'medium', 'low'] as const).map((level) => {
                      const conf = accuracyData.by_confidence[level];
                      if (!conf) return null;
                      return (
                        <ConfidenceBar
                          key={level}
                          level={level}
                          total={conf.total}
                          correct={conf.correct}
                          accuracy={conf.accuracy}
                        />
                      );
                    })}
                  </div>
                </div>

                {/* Source + Sport breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                    <h3 className="text-lg font-semibold mb-4">By Source</h3>
                    <div className="space-y-3">
                      {Object.entries(accuracyData.by_source).map(([source, stats]) => {
                        const pct = stats.total > 0 ? (stats.correct / stats.total) * 100 : 0;
                        return (
                          <div key={source} className="flex items-center justify-between">
                            <span className="capitalize font-medium">{source}</span>
                            <div className="text-sm text-dark-400">
                              {stats.correct}/{stats.total}
                              {stats.total > 0 && (
                                <span className="ml-1 text-dark-300">({pct.toFixed(0)}%)</span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                    <h3 className="text-lg font-semibold mb-4">By Sport</h3>
                    {Object.keys(accuracyData.by_sport).length === 0 ? (
                      <p className="text-sm text-dark-500">No sport data yet.</p>
                    ) : (
                      <div className="space-y-3">
                        {Object.entries(accuracyData.by_sport).map(([sport, stats]) => {
                          const pct = stats.total > 0 ? (stats.correct / stats.total) * 100 : 0;
                          return (
                            <div key={sport} className="flex items-center justify-between">
                              <span className="uppercase font-medium text-sm">{sport}</span>
                              <div className="text-sm text-dark-400">
                                {stats.correct}/{stats.total}
                                {stats.total > 0 && (
                                  <span className="ml-1 text-dark-300">({pct.toFixed(0)}%)</span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>

                {/* Empty state */}
                {accuracyData.total_decisions === 0 && (
                  <div className="text-center py-12">
                    <Target className="h-12 w-12 text-dark-600 mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-dark-300">No decisions yet</h3>
                    <p className="text-dark-500 mt-1">
                      Start asking the Goblin questions to build your accuracy history.
                    </p>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  );
}
