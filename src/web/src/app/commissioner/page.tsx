'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import { ProBanner } from '@/components/ProBanner';
import { useAuthStore } from '@/stores/authStore';
import { useSubscriptionStore } from '@/stores/subscriptionStore';
import api from '@/lib/api';
import {
  Crown,
  Shield,
  TrendingUp,
  Users,
  AlertTriangle,
  Scale,
  Loader2,
  BarChart3,
  Bell,
  Gavel,
  CheckCircle,
  XCircle,
  Clock,
  ArrowRight,
} from 'lucide-react';

type Tab = 'rankings' | 'trade' | 'roster' | 'activity' | 'alerts' | 'disputes';

const TABS: { key: Tab; label: string; icon: typeof Crown }[] = [
  { key: 'rankings', label: 'Power Rankings', icon: TrendingUp },
  { key: 'trade', label: 'Trade Check', icon: Scale },
  { key: 'roster', label: 'Roster Analysis', icon: BarChart3 },
  { key: 'activity', label: 'Activity', icon: Users },
  { key: 'alerts', label: 'Alerts', icon: Bell },
  { key: 'disputes', label: 'Disputes', icon: Gavel },
];

interface ManagedLeague {
  id: number;
  name: string;
  sport: string;
  season: string;
  role: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <div className="text-center py-16">
      <Loader2 className="w-12 h-12 text-primary-400 mx-auto mb-4 animate-spin" />
      <p className="text-dark-400">Loading...</p>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="text-center py-16">
      <AlertTriangle className="w-12 h-12 text-red-400 mx-auto mb-4" />
      <p className="text-red-400 font-medium">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-3 text-sm text-primary-400 hover:text-primary-300">
          Try again
        </button>
      )}
    </div>
  );
}

function PowerRankingsTab({ leagueId }: { leagueId: number }) {
  const [data, setData] = useState<{ league_name: string; rankings: { rank: number; owner_id: string; display_name: string | null; roster_size: number; strength_score: number }[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getPowerRankings(leagueId);
      setData(result);
    } catch {
      setError('Failed to load power rankings');
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetch} />;
  if (!data || data.rankings.length === 0) {
    return (
      <div className="text-center py-16">
        <TrendingUp className="w-16 h-16 text-dark-600 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-dark-300">No rankings available</h2>
        <p className="text-dark-500 mt-2">Power rankings will appear once rosters are loaded.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.rankings.map((r) => (
        <div key={r.owner_id} className={`flex items-center gap-4 p-4 rounded-xl ${
          r.rank <= 3 ? 'bg-dark-800/80 border border-dark-600' : 'bg-dark-800/40 border border-dark-700/50'
        }`}>
          <div className={`text-2xl font-bold w-8 text-center ${
            r.rank === 1 ? 'text-yellow-400' : r.rank === 2 ? 'text-gray-300' : r.rank === 3 ? 'text-amber-600' : 'text-dark-500'
          }`}>{r.rank}</div>
          <div className="flex-1">
            <div className="font-semibold text-dark-100">{r.display_name || `Owner ${r.owner_id.slice(0, 8)}`}</div>
            <div className="text-xs text-dark-500">{r.roster_size} players</div>
          </div>
          <div className="text-xl font-bold text-primary-400">{r.strength_score}</div>
        </div>
      ))}
    </div>
  );
}

function TradeCheckTab({ leagueId }: { leagueId: number }) {
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [result, setResult] = useState<{ fairness_score: number; verdict: string; reasoning: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCheck = async () => {
    if (!teamA.trim() || !teamB.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.checkTradeFairness(
        leagueId,
        teamA.split(',').map((s) => s.trim()).filter(Boolean),
        teamB.split(',').map((s) => s.trim()).filter(Boolean),
      );
      setResult(data);
    } catch {
      setError('Trade analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const fairnessColor = result
    ? result.fairness_score >= 40 && result.fairness_score <= 60
      ? 'text-green-400'
      : result.fairness_score >= 25 || result.fairness_score <= 75
        ? 'text-yellow-400'
        : 'text-red-400'
    : '';

  return (
    <div className="space-y-6">
      <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
        <h3 className="font-semibold text-dark-100 mb-4">Analyze a Trade</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="text-sm text-dark-400 mb-1 block">Team A gives up</label>
            <input
              type="text"
              value={teamA}
              onChange={(e) => setTeamA(e.target.value)}
              placeholder="Player 1, Player 2..."
              className="w-full px-4 py-3 bg-dark-700 border border-dark-600 rounded-lg text-dark-100 placeholder:text-dark-500 focus:outline-none focus:border-primary-500"
            />
          </div>
          <div>
            <label className="text-sm text-dark-400 mb-1 block">Team B gives up</label>
            <input
              type="text"
              value={teamB}
              onChange={(e) => setTeamB(e.target.value)}
              placeholder="Player 3, Player 4..."
              className="w-full px-4 py-3 bg-dark-700 border border-dark-600 rounded-lg text-dark-100 placeholder:text-dark-500 focus:outline-none focus:border-primary-500"
            />
          </div>
        </div>
        <button
          onClick={handleCheck}
          disabled={loading || !teamA.trim() || !teamB.trim()}
          className="mt-4 flex items-center gap-2 px-6 py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Scale className="w-4 h-4" />}
          {loading ? 'Analyzing...' : 'Check Trade'}
        </button>
      </div>

      {error && <ErrorState message={error} />}

      {result && (
        <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-dark-100">Result</h3>
            <span className={`text-3xl font-bold ${fairnessColor}`}>{result.fairness_score}/100</span>
          </div>
          <div className={`inline-block px-3 py-1 rounded-full text-sm font-medium mb-3 ${
            result.verdict === 'Fair' ? 'bg-green-500/20 text-green-400' :
            result.verdict === 'Slightly Lopsided' ? 'bg-yellow-500/20 text-yellow-400' :
            'bg-red-500/20 text-red-400'
          }`}>{result.verdict}</div>
          <p className="text-dark-300 leading-relaxed">{result.reasoning}</p>
        </div>
      )}
    </div>
  );
}

function RosterAnalysisTab({ leagueId }: { leagueId: number }) {
  const [teams, setTeams] = useState<{ owner_id: string; display_name: string | null; roster_size: number; starters_count: number; strengths: string[]; weaknesses: string[] }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getRosterAnalysis(leagueId);
      setTeams(data.teams);
    } catch {
      setError('Failed to load roster analysis');
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetch} />;
  if (teams.length === 0) {
    return (
      <div className="text-center py-16">
        <BarChart3 className="w-16 h-16 text-dark-600 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-dark-300">No roster data</h2>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {teams.map((t) => (
        <div key={t.owner_id} className="bg-dark-800/50 border border-dark-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="font-semibold text-dark-100">{t.display_name || `Owner ${t.owner_id.slice(0, 8)}`}</div>
            <div className="text-sm text-dark-400">{t.roster_size} players &middot; {t.starters_count} starters</div>
          </div>
          <div className="flex gap-4">
            {t.strengths.length > 0 && (
              <div className="flex-1">
                {t.strengths.map((s) => (
                  <span key={s} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-500/10 text-green-400 mr-2 mb-1">
                    <CheckCircle className="w-3 h-3" />{s}
                  </span>
                ))}
              </div>
            )}
            {t.weaknesses.length > 0 && (
              <div className="flex-1">
                {t.weaknesses.map((w) => (
                  <span key={w} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-500/10 text-red-400 mr-2 mb-1">
                    <XCircle className="w-3 h-3" />{w}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function ActivityTab({ leagueId }: { leagueId: number }) {
  const [data, setData] = useState<{ total_members: number; active_members: number; members: { user_id: number; name: string; queries_this_week: number; last_active: string | null; is_active: boolean }[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getLeagueActivity(leagueId);
      setData(result);
    } catch {
      setError('Failed to load activity');
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetch} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 text-center">
          <div className="text-3xl font-bold text-primary-400">{data.active_members}</div>
          <div className="text-sm text-dark-400">Active this week</div>
        </div>
        <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 text-center">
          <div className="text-3xl font-bold text-dark-200">{data.total_members}</div>
          <div className="text-sm text-dark-400">Total members</div>
        </div>
      </div>
      <div className="space-y-2">
        {data.members.map((m) => (
          <div key={m.user_id} className="flex items-center gap-4 p-4 bg-dark-800/40 border border-dark-700/50 rounded-xl">
            <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${m.is_active ? 'bg-green-400' : 'bg-dark-600'}`} />
            <div className="flex-1 min-w-0">
              <div className="font-medium text-dark-100 truncate">{m.name}</div>
              <div className="text-xs text-dark-500">
                {m.last_active ? `Last active ${new Date(m.last_active).toLocaleDateString()}` : 'Never active'}
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-medium text-dark-200">{m.queries_this_week}</div>
              <div className="text-[10px] text-dark-500">queries</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AlertsTab({ leagueId }: { leagueId: number }) {
  const [alerts, setAlerts] = useState<{ category: string; severity: string; message: string; details?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getLeagueAlerts(leagueId);
      setAlerts(result.alerts || []);
    } catch {
      setError('Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetch} />;
  if (alerts.length === 0) {
    return (
      <div className="text-center py-16">
        <CheckCircle className="w-16 h-16 text-green-500/50 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-dark-300">No alerts</h2>
        <p className="text-dark-500 mt-2">Your league looks healthy!</p>
      </div>
    );
  }

  const severityStyle: Record<string, string> = {
    critical: 'border-red-500/30 bg-red-500/5',
    warning: 'border-yellow-500/30 bg-yellow-500/5',
    info: 'border-blue-500/30 bg-blue-500/5',
  };
  const severityIcon: Record<string, string> = {
    critical: 'text-red-400',
    warning: 'text-yellow-400',
    info: 'text-blue-400',
  };

  return (
    <div className="space-y-3">
      {alerts.map((a, i) => (
        <div key={i} className={`border rounded-xl p-4 ${severityStyle[a.severity] || severityStyle.info}`}>
          <div className="flex items-start gap-3">
            <AlertTriangle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${severityIcon[a.severity] || severityIcon.info}`} />
            <div>
              <div className="font-medium text-dark-100">{a.message}</div>
              {a.details && <p className="text-sm text-dark-400 mt-1">{a.details}</p>}
              <span className="text-xs text-dark-500 mt-1 inline-block">{a.category}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DisputesTab({ leagueId }: { leagueId: number }) {
  const [data, setData] = useState<{ total: number; open: number; resolved: number; disputes: { id: number; category: string; subject: string; description: string; status: string; filed_by_name: string | null; created_at: string; resolution: string | null }[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getDisputes(leagueId);
      setData(result);
    } catch {
      setError('Failed to load disputes');
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetch} />;
  if (!data || data.disputes.length === 0) {
    return (
      <div className="text-center py-16">
        <Gavel className="w-16 h-16 text-dark-600 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-dark-300">No disputes</h2>
        <p className="text-dark-500 mt-2">No disputes have been filed in this league.</p>
      </div>
    );
  }

  const statusStyle: Record<string, { bg: string; text: string }> = {
    open: { bg: 'bg-yellow-500/20', text: 'text-yellow-400' },
    under_review: { bg: 'bg-blue-500/20', text: 'text-blue-400' },
    resolved: { bg: 'bg-green-500/20', text: 'text-green-400' },
    dismissed: { bg: 'bg-dark-600/50', text: 'text-dark-400' },
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-4 text-sm">
        <span className="text-dark-400">Total: <span className="text-dark-200 font-medium">{data.total}</span></span>
        <span className="text-yellow-400">Open: {data.open}</span>
        <span className="text-green-400">Resolved: {data.resolved}</span>
      </div>
      <div className="space-y-3">
        {data.disputes.map((d) => {
          const style = statusStyle[d.status] || statusStyle.open;
          return (
            <div key={d.id} className="bg-dark-800/50 border border-dark-700 rounded-xl p-5">
              <div className="flex items-center justify-between mb-2">
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${style.bg} ${style.text}`}>
                  {d.status.toUpperCase().replace('_', ' ')}
                </span>
                <span className="text-xs text-dark-500">{d.category}</span>
              </div>
              <h4 className="font-semibold text-dark-100">{d.subject}</h4>
              <p className="text-sm text-dark-400 mt-1">{d.description}</p>
              {d.resolution && (
                <p className="text-sm text-green-400/80 mt-2 italic">&ldquo;{d.resolution}&rdquo;</p>
              )}
              <div className="flex items-center gap-3 mt-3 text-xs text-dark-500">
                {d.filed_by_name && <span>Filed by {d.filed_by_name}</span>}
                <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(d.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CommissionerPage() {
  const { isAuthenticated } = useAuthStore();
  const { isPro } = useSubscriptionStore();
  const [leagues, setLeagues] = useState<ManagedLeague[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>('rankings');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated) return;
    const fetch = async () => {
      try {
        const data = await api.getManagedLeagues();
        const commish = data.filter((l: ManagedLeague) => l.role === 'commissioner');
        setLeagues(commish);
        if (commish.length > 0) setSelectedLeague(commish[0].id);
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="pt-20 pb-8 px-4">
          <div className="max-w-4xl mx-auto text-center py-16">
            <Crown className="w-16 h-16 text-dark-600 mx-auto mb-4" />
            <h1 className="text-3xl font-bold mb-2">Commissioner Tools</h1>
            <p className="text-dark-400 mb-6">Sign in to access league management tools.</p>
            <Link
              href="/auth/login"
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-600 transition-colors"
            >
              Sign In <ArrowRight className="w-4 h-4" />
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
          <div className="mb-6">
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Crown className="w-8 h-8 text-yellow-400" />
              Commissioner Tools
            </h1>
            <p className="text-dark-400 mt-2">
              League analytics, trade checks, and dispute management.
            </p>
          </div>

          {/* Pro Banner */}
          <div className="mb-6">
            <ProBanner feature="commissioner tools" />
          </div>

          {loading ? (
            <LoadingState />
          ) : leagues.length === 0 ? (
            <div className="text-center py-16">
              <Shield className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">No commissioner leagues</h2>
              <p className="text-dark-500 mt-2">
                You need to be a commissioner of a connected league to use these tools.
              </p>
              <Link
                href="/leagues"
                className="inline-flex items-center gap-2 mt-4 text-primary-400 hover:text-primary-300 text-sm"
              >
                Manage Leagues <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          ) : (
            <>
              {/* League Selector */}
              {leagues.length > 1 && (
                <div className="flex items-center gap-2 mb-4 flex-wrap">
                  <span className="text-dark-400 text-sm">League:</span>
                  {leagues.map((l) => (
                    <button
                      key={l.id}
                      onClick={() => setSelectedLeague(l.id)}
                      className={`px-3 py-1 rounded-full text-sm font-medium transition-all ${
                        selectedLeague === l.id
                          ? 'bg-primary-600 text-white'
                          : 'bg-dark-700 text-dark-300 hover:bg-dark-600'
                      }`}
                    >
                      {l.name}
                    </button>
                  ))}
                </div>
              )}

              {/* Tab Selector */}
              <div className="flex gap-1 mb-6 bg-dark-800/50 rounded-lg p-1 border border-dark-700 overflow-x-auto">
                {TABS.map((t) => {
                  const Icon = t.icon;
                  const isSelected = tab === t.key;
                  return (
                    <button
                      key={t.key}
                      onClick={() => setTab(t.key)}
                      className={`flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-md text-sm font-medium transition-all whitespace-nowrap ${
                        isSelected
                          ? 'bg-dark-700 text-white shadow-sm'
                          : 'text-dark-400 hover:text-dark-200'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      <span className="hidden sm:inline">{t.label}</span>
                    </button>
                  );
                })}
              </div>

              {/* Tab Content */}
              {!isPro ? (
                <div className="text-center py-16">
                  <Crown className="w-16 h-16 text-yellow-500/30 mx-auto mb-4" />
                  <h2 className="text-xl font-semibold text-dark-300">Pro feature</h2>
                  <p className="text-dark-500 mt-2">Upgrade to Pro to access commissioner tools.</p>
                  <Link
                    href="/billing"
                    className="inline-flex items-center gap-2 mt-4 px-6 py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-500 transition-all"
                  >
                    Upgrade to Pro <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              ) : selectedLeague ? (
                <>
                  {tab === 'rankings' && <PowerRankingsTab leagueId={selectedLeague} />}
                  {tab === 'trade' && <TradeCheckTab leagueId={selectedLeague} />}
                  {tab === 'roster' && <RosterAnalysisTab leagueId={selectedLeague} />}
                  {tab === 'activity' && <ActivityTab leagueId={selectedLeague} />}
                  {tab === 'alerts' && <AlertsTab leagueId={selectedLeague} />}
                  {tab === 'disputes' && <DisputesTab leagueId={selectedLeague} />}
                </>
              ) : null}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
