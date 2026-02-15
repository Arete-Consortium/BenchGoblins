'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import { useAppStore } from '@/stores/appStore';
import api from '@/lib/api';
import { UsageStats, HealthResponse } from '@/types';
import { getSportDisplayName } from '@/lib/utils';
import {
  MessageSquare,
  TrendingUp,
  Zap,
  Activity,
  Server,
  CheckCircle,
  XCircle,
  Clock,
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
  icon: typeof MessageSquare;
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

export default function DashboardPage() {
  const { sport, messages } = useAppStore();
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [usageData, healthData] = await Promise.all([
          api.getUsage().catch(() => null),
          api.getHealth().catch(() => null),
        ]);
        setUsage(usageData);
        setHealth(healthData);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

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
            <p className="text-dark-400 mt-1">
              Your fantasy decision analytics for {getSportDisplayName(sport)}
            </p>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard
              title="Queries Today"
              value={usage?.queries_today ?? todayQueries}
              subtitle={usage ? `${usage.queries_limit - usage.queries_today} remaining` : undefined}
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
              value={usage?.tokens_used.toLocaleString() ?? '—'}
              subtitle={usage ? `$${usage.cost_usd.toFixed(4)}` : undefined}
              icon={Zap}
              color="bg-orange-500/20 text-orange-400"
            />
            <StatCard
              title="Success Rate"
              value="—"
              subtitle="Coming soon"
              icon={TrendingUp}
              color="bg-green-500/20 text-green-400"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Quick Actions */}
            <div className="lg:col-span-2 bg-dark-800/50 border border-dark-700 rounded-xl p-6">
              <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
              <div className="grid grid-cols-2 gap-4">
                <Link
                  href="/"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <MessageSquare className="w-5 h-5 text-primary-400" />
                  <div>
                    <div className="font-medium">New Decision</div>
                    <div className="text-sm text-dark-400">Ask a question</div>
                  </div>
                </Link>
                <Link
                  href="/history"
                  className="flex items-center gap-3 p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                >
                  <Clock className="w-5 h-5 text-blue-400" />
                  <div>
                    <div className="font-medium">View History</div>
                    <div className="text-sm text-dark-400">Past decisions</div>
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
                  <StatusIndicator status={health.components.database} label="Database" />
                  <StatusIndicator status={health.components.redis} label="Cache (Redis)" />
                  <StatusIndicator status={health.components.claude} label="Claude AI" />
                  <StatusIndicator status={health.components.espn} label="ESPN API" />
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
        </div>
      </main>
    </div>
  );
}
