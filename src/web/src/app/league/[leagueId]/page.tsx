'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Crown,
  Users2,
  Trophy,
  ArrowRightLeft,
  Activity,
  Copy,
  RefreshCw,
  Loader2,
  Check,
  Shield,
  Swords,
  Scale,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/stores/authStore';
import api from '@/lib/api';

type Tab = 'overview' | 'rivalries' | 'disputes' | 'rankings' | 'trade' | 'activity';

interface League {
  id: number;
  name: string;
  sport: string;
  season: string;
  platform: string;
  role: string;
  member_count: number;
  invite_code: string | null;
}

interface Member {
  user_id: number;
  email: string;
  name: string;
  role: string;
  status: string;
  joined_at: string;
}

interface Ranking {
  rank: number;
  owner_id: string;
  display_name: string | null;
  roster_size: number;
  strength_score: number;
}

interface TradeResult {
  fairness_score: number;
  verdict: string;
  reasoning: string;
}

interface ActivityMember {
  user_id: number;
  name: string;
  queries_this_week: number;
  is_active: boolean;
  last_active: string | null;
}

interface Dispute {
  id: number;
  league_id: number;
  filed_by_user_id: number;
  filed_by_name: string | null;
  against_user_id: number | null;
  against_name: string | null;
  category: string;
  subject: string;
  description: string;
  status: string;
  resolution: string | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  created_at: string;
}

interface Rivalry {
  owner_a: string;
  owner_b: string;
  games_played: number;
  wins_a: number;
  wins_b: number;
  ties: number;
  avg_margin: number;
  total_points_a: number;
  total_points_b: number;
}

export default function LeagueDashboard() {
  const params = useParams();
  const leagueId = Number(params.leagueId);
  const { isAuthenticated } = useAuthStore();

  const [tab, setTab] = useState<Tab>('overview');
  const [league, setLeague] = useState<League | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [rankings, setRankings] = useState<Ranking[]>([]);
  const [activity, setActivity] = useState<ActivityMember[]>([]);
  const [rivalries, setRivalries] = useState<Rivalry[]>([]);
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [disputeStats, setDisputeStats] = useState({ total: 0, open: 0, resolved: 0 });
  const [tradeResult, setTradeResult] = useState<TradeResult | null>(null);
  const [syncing, setSyncing] = useState(false);
  // Dispute form
  const [disputeCategory, setDisputeCategory] = useState('trade');
  const [disputeSubject, setDisputeSubject] = useState('');
  const [disputeDescription, setDisputeDescription] = useState('');
  const [resolutionText, setResolutionText] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Trade form state
  const [teamAPlayers, setTeamAPlayers] = useState('');
  const [teamBPlayers, setTeamBPlayers] = useState('');

  const isCommissioner = league?.role === 'commissioner';

  const fetchLeague = useCallback(async () => {
    try {
      const [leagueData, membersData] = await Promise.all([
        api.getManagedLeague(leagueId),
        api.getLeagueMembers(leagueId),
      ]);
      setLeague(leagueData);
      setMembers(membersData);
    } catch {
      setError('Failed to load league');
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => {
    if (isAuthenticated) fetchLeague();
  }, [isAuthenticated, fetchLeague]);

  const copyInviteLink = useCallback(async () => {
    if (!league?.invite_code) return;
    const url = `https://benchgoblins.com/leagues/join/${league.invite_code}`;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [league?.invite_code]);

  const regenerateInvite = useCallback(async () => {
    setActionLoading(true);
    try {
      const data = await api.generateInvite(leagueId);
      setLeague((prev) => prev ? { ...prev, invite_code: data.invite_code } : prev);
    } catch {
      setError('Failed to regenerate invite');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId]);

  const fetchRankings = useCallback(async () => {
    setActionLoading(true);
    try {
      const data = await api.getPowerRankings(leagueId);
      setRankings(data.rankings);
    } catch {
      setError('Failed to load power rankings');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId]);

  const fetchActivity = useCallback(async () => {
    setActionLoading(true);
    try {
      const data = await api.getLeagueActivity(leagueId);
      setActivity(data.members);
    } catch {
      setError('Failed to load activity');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId]);

  const fetchDisputes = useCallback(async () => {
    setActionLoading(true);
    try {
      const data = await api.getDisputes(leagueId);
      setDisputes(data.disputes);
      setDisputeStats({ total: data.total, open: data.open, resolved: data.resolved });
    } catch {
      setError('Failed to load disputes');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId]);

  const fileNewDispute = useCallback(async () => {
    if (!disputeSubject.trim() || !disputeDescription.trim()) return;
    setActionLoading(true);
    try {
      await api.fileDispute(leagueId, {
        category: disputeCategory,
        subject: disputeSubject,
        description: disputeDescription,
      });
      setDisputeSubject('');
      setDisputeDescription('');
      await fetchDisputes();
    } catch {
      setError('Failed to file dispute');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId, disputeCategory, disputeSubject, disputeDescription, fetchDisputes]);

  const resolveDispute = useCallback(async (disputeId: number, status: 'resolved' | 'dismissed') => {
    if (!resolutionText.trim()) return;
    setActionLoading(true);
    try {
      await api.resolveDispute(leagueId, disputeId, {
        status,
        resolution: resolutionText,
      });
      setResolutionText('');
      await fetchDisputes();
    } catch {
      setError('Failed to resolve dispute');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId, resolutionText, fetchDisputes]);

  const fetchRivalries = useCallback(async () => {
    setActionLoading(true);
    try {
      const data = await api.getLeagueRivalries(leagueId, league?.season);
      setRivalries(data);
    } catch {
      setError('Failed to load rivalries');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId, league?.season]);

  const syncRivalries = useCallback(async () => {
    setSyncing(true);
    try {
      await api.syncRivalries(leagueId, league?.season || '2025');
      await fetchRivalries();
    } catch {
      setError('Failed to sync matchup data');
    } finally {
      setSyncing(false);
    }
  }, [leagueId, league?.season, fetchRivalries]);

  const analyzeTrade = useCallback(async () => {
    if (!teamAPlayers.trim() || !teamBPlayers.trim()) return;
    setActionLoading(true);
    setTradeResult(null);
    try {
      const result = await api.checkTradeFairness(
        leagueId,
        teamAPlayers.split(',').map((s) => s.trim()).filter(Boolean),
        teamBPlayers.split(',').map((s) => s.trim()).filter(Boolean),
      );
      setTradeResult(result);
    } catch {
      setError('Trade analysis failed');
    } finally {
      setActionLoading(false);
    }
  }, [leagueId, teamAPlayers, teamBPlayers]);

  useEffect(() => {
    if (tab === 'rankings' && rankings.length === 0) fetchRankings();
    if (tab === 'activity' && activity.length === 0) fetchActivity();
    if (tab === 'rivalries' && rivalries.length === 0) fetchRivalries();
    if (tab === 'disputes' && disputes.length === 0) fetchDisputes();
  }, [tab, rankings.length, activity.length, rivalries.length, disputes.length, fetchRankings, fetchActivity, fetchRivalries, fetchDisputes]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-background p-6 text-center py-20">
        <p className="text-muted-foreground">Sign in to view league details.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex justify-center items-center">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error && !league) {
    return (
      <div className="min-h-screen bg-background p-6 text-center py-20 text-destructive">{error}</div>
    );
  }

  if (!league) return null;

  const tabs: { key: Tab; label: string; icon: typeof Trophy; commissionerOnly?: boolean }[] = [
    { key: 'overview', label: 'Overview', icon: Users2 },
    { key: 'rivalries', label: 'Rivalries', icon: Swords },
    { key: 'disputes', label: 'Disputes', icon: Scale },
    { key: 'rankings', label: 'Power Rankings', icon: Trophy, commissionerOnly: true },
    { key: 'trade', label: 'Trade Checker', icon: ArrowRightLeft, commissionerOnly: true },
    { key: 'activity', label: 'Activity', icon: Activity, commissionerOnly: true },
  ];

  const visibleTabs = tabs.filter((t) => !t.commissionerOnly || isCommissioner);

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Link href="/leagues">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              {isCommissioner ? (
                <Crown className="w-5 h-5 text-yellow-500" />
              ) : (
                <Shield className="w-5 h-5 text-blue-500" />
              )}
              <h1 className="text-2xl font-bold">{league.name}</h1>
            </div>
            <p className="text-sm text-muted-foreground">
              {league.sport.toUpperCase()} &middot; {league.season} &middot; {league.platform} &middot; {league.member_count} members
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto">
          {visibleTabs.map((t) => (
            <Button
              key={t.key}
              variant={tab === t.key ? 'default' : 'outline'}
              size="sm"
              onClick={() => setTab(t.key)}
            >
              <t.icon className="w-4 h-4 mr-1.5" />
              {t.label}
            </Button>
          ))}
        </div>

        {error && <p className="text-destructive text-sm mb-4">{error}</p>}

        {/* Overview Tab */}
        {tab === 'overview' && (
          <div className="grid gap-4 md:grid-cols-2">
            {/* Members Card */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Users2 className="w-5 h-5" />
                  Members
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {members.map((m) => (
                    <div key={m.user_id} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        {m.role === 'commissioner' ? (
                          <Crown className="w-4 h-4 text-yellow-500" />
                        ) : (
                          <Shield className="w-4 h-4 text-blue-400" />
                        )}
                        <span>{m.name || m.email}</span>
                      </div>
                      <span className="text-muted-foreground capitalize">{m.status}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Invite Card (Commissioner Only) */}
            {isCommissioner && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Invite Link</CardTitle>
                  <CardDescription>Share this link to invite members</CardDescription>
                </CardHeader>
                <CardContent>
                  {league.invite_code ? (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <code className="flex-1 text-xs bg-muted p-2 rounded truncate">
                          benchgoblins.com/leagues/join/{league.invite_code}
                        </code>
                        <Button variant="outline" size="icon" onClick={copyInviteLink}>
                          {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                        </Button>
                      </div>
                      <Button variant="ghost" size="sm" onClick={regenerateInvite} disabled={actionLoading}>
                        <RefreshCw className="w-4 h-4 mr-1.5" />
                        Regenerate
                      </Button>
                    </div>
                  ) : (
                    <Button onClick={regenerateInvite} disabled={actionLoading}>
                      Generate Invite Link
                    </Button>
                  )}
                </CardContent>
              </Card>
            )}

            {/* League Pro Card */}
            {isCommissioner && (
              <Card className="md:col-span-2">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Zap className="w-5 h-5 text-yellow-500" />
                    League Pro
                  </CardTitle>
                  <CardDescription>
                    Upgrade your league to give all members unlimited queries
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Link href="/billing">
                    <Button>
                      <Crown className="w-4 h-4 mr-2" />
                      Upgrade League — $4.99/mo
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Rivalries Tab */}
        {tab === 'rivalries' && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-lg">League Rivalries</CardTitle>
                <CardDescription>Head-to-head records between all members</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={syncRivalries} disabled={syncing}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Syncing...' : 'Sync from Sleeper'}
              </Button>
            </CardHeader>
            <CardContent>
              {actionLoading && rivalries.length === 0 ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin" />
                </div>
              ) : rivalries.length === 0 ? (
                <div className="text-center py-8">
                  <Swords className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
                  <p className="text-muted-foreground mb-3">No rivalry data yet</p>
                  <Button onClick={syncRivalries} disabled={syncing}>
                    {syncing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                    Sync Matchup Data
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {rivalries.map((r, i) => {
                    const dominantA = r.wins_a > r.wins_b;
                    const dominantB = r.wins_b > r.wins_a;
                    const tied = r.wins_a === r.wins_b;
                    return (
                      <div key={i} className="p-3 bg-muted/50 rounded-lg">
                        <div className="flex items-center justify-between mb-1">
                          <span className={`font-medium text-sm ${dominantA ? 'text-green-400' : ''}`}>
                            {r.owner_a.slice(0, 12)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {r.games_played} game{r.games_played !== 1 ? 's' : ''}
                          </span>
                          <span className={`font-medium text-sm ${dominantB ? 'text-green-400' : ''}`}>
                            {r.owner_b.slice(0, 12)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className={`text-lg font-bold ${dominantA ? 'text-green-400' : dominantB ? 'text-red-400' : ''}`}>
                            {r.wins_a}
                          </span>
                          <div className="flex-1 mx-3">
                            <div className="h-2 bg-dark-700 rounded-full overflow-hidden flex">
                              <div
                                className="bg-green-500 h-full"
                                style={{ width: r.games_played > 0 ? `${(r.wins_a / r.games_played) * 100}%` : '50%' }}
                              />
                              {r.ties > 0 && (
                                <div
                                  className="bg-yellow-500 h-full"
                                  style={{ width: `${(r.ties / r.games_played) * 100}%` }}
                                />
                              )}
                              <div className="bg-red-500 h-full flex-1" />
                            </div>
                          </div>
                          <span className={`text-lg font-bold ${dominantB ? 'text-green-400' : dominantA ? 'text-red-400' : ''}`}>
                            {r.wins_b}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                          <span>{r.total_points_a.toFixed(1)} pts</span>
                          {tied && r.ties > 0 && <span>{r.ties} tie{r.ties !== 1 ? 's' : ''}</span>}
                          <span>Avg margin: {r.avg_margin}</span>
                          <span>{r.total_points_b.toFixed(1)} pts</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Disputes Tab */}
        {tab === 'disputes' && (
          <div className="space-y-4">
            {/* File New Dispute */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">File a Dispute</CardTitle>
                <CardDescription>Report an issue for commissioner review</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <label className="text-sm font-medium mb-1 block">Category</label>
                  <select
                    className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm"
                    value={disputeCategory}
                    onChange={(e) => setDisputeCategory(e.target.value)}
                  >
                    <option value="trade">Trade</option>
                    <option value="roster">Roster</option>
                    <option value="scoring">Scoring</option>
                    <option value="conduct">Conduct</option>
                    <option value="other">Other</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium mb-1 block">Subject</label>
                  <input
                    type="text"
                    className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm"
                    placeholder="Brief summary of the dispute"
                    value={disputeSubject}
                    onChange={(e) => setDisputeSubject(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium mb-1 block">Description</label>
                  <textarea
                    className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm min-h-[80px]"
                    placeholder="Describe the issue in detail..."
                    value={disputeDescription}
                    onChange={(e) => setDisputeDescription(e.target.value)}
                  />
                </div>
                <Button
                  onClick={fileNewDispute}
                  disabled={actionLoading || !disputeSubject.trim() || !disputeDescription.trim()}
                >
                  {actionLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Scale className="w-4 h-4 mr-2" />}
                  Submit Dispute
                </Button>
              </CardContent>
            </Card>

            {/* Dispute List */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg">Disputes</CardTitle>
                  <CardDescription>
                    {disputeStats.total} total &middot; {disputeStats.open} open &middot; {disputeStats.resolved} resolved
                  </CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={fetchDisputes} disabled={actionLoading}>
                  <RefreshCw className={`w-4 h-4 mr-1.5 ${actionLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
              </CardHeader>
              <CardContent>
                {actionLoading && disputes.length === 0 ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin" />
                  </div>
                ) : disputes.length === 0 ? (
                  <div className="text-center py-8">
                    <Scale className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
                    <p className="text-muted-foreground">No disputes filed yet</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {disputes.map((d) => (
                      <div key={d.id} className="p-3 bg-muted/50 rounded-lg space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                              d.status === 'open' ? 'bg-yellow-500/20 text-yellow-400' :
                              d.status === 'resolved' ? 'bg-green-500/20 text-green-400' :
                              'bg-gray-500/20 text-gray-400'
                            }`}>
                              {d.status}
                            </span>
                            <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground capitalize">
                              {d.category}
                            </span>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {new Date(d.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="font-medium text-sm">{d.subject}</p>
                        <p className="text-sm text-muted-foreground">{d.description}</p>
                        <p className="text-xs text-muted-foreground">
                          Filed by {d.filed_by_name || `User #${d.filed_by_user_id}`}
                          {d.against_name && ` against ${d.against_name}`}
                        </p>

                        {d.resolution && (
                          <div className="mt-2 p-2 bg-background rounded border border-border">
                            <p className="text-xs font-medium text-green-400 mb-1">Resolution</p>
                            <p className="text-sm">{d.resolution}</p>
                            {d.resolved_by_name && (
                              <p className="text-xs text-muted-foreground mt-1">
                                By {d.resolved_by_name} on {d.resolved_at ? new Date(d.resolved_at).toLocaleDateString() : ''}
                              </p>
                            )}
                          </div>
                        )}

                        {isCommissioner && d.status === 'open' && (
                          <div className="mt-2 pt-2 border-t border-border space-y-2">
                            <textarea
                              className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm min-h-[60px]"
                              placeholder="Enter resolution..."
                              value={resolutionText}
                              onChange={(e) => setResolutionText(e.target.value)}
                            />
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                onClick={() => resolveDispute(d.id, 'resolved')}
                                disabled={actionLoading || !resolutionText.trim()}
                              >
                                Resolve
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => resolveDispute(d.id, 'dismissed')}
                                disabled={actionLoading || !resolutionText.trim()}
                              >
                                Dismiss
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Power Rankings Tab */}
        {tab === 'rankings' && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Power Rankings</CardTitle>
              <Button variant="outline" size="sm" onClick={fetchRankings} disabled={actionLoading}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${actionLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </CardHeader>
            <CardContent>
              {actionLoading && rankings.length === 0 ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin" />
                </div>
              ) : rankings.length === 0 ? (
                <p className="text-muted-foreground text-center py-8">No roster data available</p>
              ) : (
                <div className="space-y-3">
                  {rankings.map((r) => (
                    <div key={r.owner_id} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl font-bold text-muted-foreground w-8">#{r.rank}</span>
                        <div>
                          <p className="font-medium">{r.display_name || r.owner_id}</p>
                          <p className="text-xs text-muted-foreground">{r.roster_size} players</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold">{r.strength_score}</p>
                        <p className="text-xs text-muted-foreground">strength</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Trade Checker Tab */}
        {tab === 'trade' && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Trade Fairness Checker</CardTitle>
              <CardDescription>Enter player names separated by commas</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Team A gives up:</label>
                <input
                  type="text"
                  className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm"
                  placeholder="e.g. Patrick Mahomes, Travis Kelce"
                  value={teamAPlayers}
                  onChange={(e) => setTeamAPlayers(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Team B gives up:</label>
                <input
                  type="text"
                  className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm"
                  placeholder="e.g. Josh Allen, Davante Adams"
                  value={teamBPlayers}
                  onChange={(e) => setTeamBPlayers(e.target.value)}
                />
              </div>
              <Button onClick={analyzeTrade} disabled={actionLoading || !teamAPlayers.trim() || !teamBPlayers.trim()}>
                {actionLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ArrowRightLeft className="w-4 h-4 mr-2" />}
                Analyze Trade
              </Button>

              {tradeResult && (
                <div className="mt-4 p-4 bg-muted/50 rounded-lg space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-lg">{tradeResult.verdict}</span>
                    <span className="text-2xl font-bold">{tradeResult.fairness_score}/100</span>
                  </div>
                  <p className="text-sm text-muted-foreground">{tradeResult.reasoning}</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Activity Tab */}
        {tab === 'activity' && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Member Activity</CardTitle>
              <Button variant="outline" size="sm" onClick={fetchActivity} disabled={actionLoading}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${actionLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </CardHeader>
            <CardContent>
              {actionLoading && activity.length === 0 ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin" />
                </div>
              ) : activity.length === 0 ? (
                <p className="text-muted-foreground text-center py-8">No member data yet</p>
              ) : (
                <div className="space-y-3">
                  {activity.map((m) => (
                    <div key={m.user_id} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full ${m.is_active ? 'bg-green-500' : 'bg-gray-400'}`} />
                        <div>
                          <p className="font-medium">{m.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {m.last_active ? `Last active: ${new Date(m.last_active).toLocaleDateString()}` : 'Never active'}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold">{m.queries_this_week}</p>
                        <p className="text-xs text-muted-foreground">queries/wk</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
