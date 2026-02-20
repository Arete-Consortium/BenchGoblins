'use client';

import { useEffect, useState, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw, Target, TrendingUp, BarChart3, Layers } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

interface AccuracyData {
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

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color = 'text-primary-400',
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={cn('h-4 w-4', color)} />
        <span className="text-sm text-dark-400">{label}</span>
      </div>
      <div className="text-3xl font-bold">{value}</div>
      {sub && <div className="text-sm text-dark-500 mt-1">{sub}</div>}
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

export default function AccuracyPage() {
  const [data, setData] = useState<AccuracyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const metrics = await api.getAccuracyMetrics();
      setData(metrics);
    } catch {
      setError('Failed to load accuracy metrics.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await api.syncOutcomes(2);
      await fetchMetrics();
    } catch {
      setError('Failed to sync outcomes.');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold">Accuracy</h1>
              <p className="text-dark-400 mt-1">How well is the Goblin doing?</p>
            </div>
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

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-primary-400" />
            </div>
          ) : error ? (
            <div className="text-center py-20 text-dark-400">{error}</div>
          ) : data ? (
            <div className="space-y-6">
              {/* Top stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  label="Win Rate"
                  value={`${data.accuracy_pct.toFixed(1)}%`}
                  sub={`${data.correct_decisions} correct`}
                  icon={Target}
                  color="text-green-400"
                />
                <StatCard
                  label="Decisions"
                  value={String(data.total_decisions)}
                  sub={`${data.decisions_with_outcomes} with outcomes`}
                  icon={BarChart3}
                />
                <StatCard
                  label="Coverage"
                  value={`${data.coverage_pct.toFixed(0)}%`}
                  sub="outcomes recorded"
                  icon={Layers}
                  color="text-blue-400"
                />
                <StatCard
                  label="Pushes"
                  value={String(data.pushes)}
                  sub="within 1 point"
                  icon={TrendingUp}
                  color="text-yellow-400"
                />
              </div>

              {/* Confidence breakdown */}
              <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                <h2 className="text-lg font-semibold mb-4">By Confidence</h2>
                <div className="space-y-4">
                  {(['high', 'medium', 'low'] as const).map((level) => {
                    const conf = data.by_confidence[level];
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

              {/* Source comparison */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4">By Source</h2>
                  <div className="space-y-3">
                    {Object.entries(data.by_source).map(([source, stats]) => {
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

                {/* Sport breakdown */}
                <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4">By Sport</h2>
                  {Object.keys(data.by_sport).length === 0 ? (
                    <p className="text-sm text-dark-500">No sport data yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {Object.entries(data.by_sport).map(([sport, stats]) => {
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
              {data.total_decisions === 0 && (
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
      </main>
    </div>
  );
}
