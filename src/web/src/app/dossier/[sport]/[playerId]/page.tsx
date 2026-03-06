'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import api from '@/lib/api';
import { getSportDisplayName, formatDate, getConfidenceColor } from '@/lib/utils';
import type { Sport, DossierResponse } from '@/types';
import {
  ArrowLeft,
  User,
  BarChart3,
  TrendingUp,
  History,
  Activity,
  Target,
  Shield,
  Zap,
  ChevronUp,
  ChevronDown,
  Minus,
  CheckCircle,
  XCircle,
  HelpCircle,
} from 'lucide-react';

function IndexBar({ label, abbrev, value, color }: { label: string; abbrev: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="text-dark-400">{label} <span className="font-mono text-dark-300">({abbrev})</span></span>
        <span className="font-mono font-bold">{value.toFixed(1)}</span>
      </div>
      <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-dark-700/50 last:border-0">
      <span className="text-dark-400 text-sm">{label}</span>
      <span className="font-mono text-sm">{value}</span>
    </div>
  );
}

export default function DossierDetailPage() {
  const params = useParams();
  const sport = params.sport as Sport;
  const playerId = params.playerId as string;

  const [dossier, setDossier] = useState<DossierResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'games' | 'decisions'>('overview');

  useEffect(() => {
    async function fetchDossier() {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getPlayerDossier(sport, playerId);
        setDossier(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load player dossier');
      } finally {
        setLoading(false);
      }
    }
    fetchDossier();
  }, [sport, playerId]);

  const formatStatLabel = (key: string): string => {
    return key
      .replace(/_/g, ' ')
      .replace(/per game/gi, '/G')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-6xl mx-auto">
          <Link
            href="/dossier"
            className="inline-flex items-center gap-2 text-dark-400 hover:text-dark-200 mb-6 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Player Search
          </Link>

          {loading ? (
            <div className="space-y-6">
              <div className="h-32 bg-dark-800/50 rounded-xl animate-pulse" />
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="h-64 bg-dark-800/50 rounded-xl animate-pulse" />
                <div className="lg:col-span-2 h-64 bg-dark-800/50 rounded-xl animate-pulse" />
              </div>
            </div>
          ) : error ? (
            <div className="text-center py-16">
              <XCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">Error Loading Dossier</h2>
              <p className="text-dark-500 mt-2">{error}</p>
            </div>
          ) : dossier ? (
            <>
              {/* Player Header */}
              <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6 mb-6">
                <div className="flex items-center gap-6">
                  <div className="w-20 h-20 rounded-xl bg-dark-700 flex items-center justify-center">
                    <User className="w-10 h-10 text-dark-500" />
                  </div>
                  <div className="flex-1">
                    <h1 className="text-3xl font-bold">{dossier.player.name}</h1>
                    <div className="flex items-center gap-3 mt-2 text-dark-400">
                      <span className="px-2 py-0.5 rounded bg-primary-600/20 text-primary-400 text-sm font-medium">
                        {dossier.player.position ?? 'N/A'}
                      </span>
                      <span>{dossier.player.team}</span>
                      <span className="text-dark-600">|</span>
                      <span>{getSportDisplayName(dossier.player.sport as Sport)}</span>
                    </div>
                  </div>
                  <div className="hidden sm:flex items-center gap-4">
                    {dossier.summary.latest_median !== null && (
                      <div className="text-center">
                        <div className="text-3xl font-bold text-primary-400">
                          {dossier.summary.latest_median.toFixed(1)}
                        </div>
                        <div className="text-xs text-dark-500 mt-1">Median Score</div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-dark-700">
                  <div className="text-center">
                    <div className="text-2xl font-bold">{dossier.summary.games_played}</div>
                    <div className="text-xs text-dark-500">Games Played</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold">{dossier.summary.total_indices}</div>
                    <div className="text-xs text-dark-500">Index Calculations</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold">{dossier.summary.total_game_logs}</div>
                    <div className="text-xs text-dark-500">Game Logs</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold">{dossier.summary.total_decisions}</div>
                    <div className="text-xs text-dark-500">Past Decisions</div>
                  </div>
                </div>
              </div>

              {/* Tab Navigation */}
              <div className="flex gap-2 mb-6">
                {(['overview', 'games', 'decisions'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      activeTab === tab
                        ? 'bg-primary-600 text-white'
                        : 'bg-dark-800 text-dark-400 hover:text-dark-200 hover:bg-dark-700'
                    }`}
                  >
                    {tab === 'overview' && <BarChart3 className="w-4 h-4 inline mr-2" />}
                    {tab === 'games' && <Activity className="w-4 h-4 inline mr-2" />}
                    {tab === 'decisions' && <History className="w-4 h-4 inline mr-2" />}
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>

              {/* Tab Content */}
              {activeTab === 'overview' && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                      <Target className="w-5 h-5 text-primary-400" />
                      Five-Index Scores
                    </h2>
                    {dossier.indices.length > 0 ? (
                      <div className="space-y-4">
                        <IndexBar label="Space Creation" abbrev="SCI" value={dossier.indices[0].sci} color="bg-primary-500" />
                        <IndexBar label="Role Motion" abbrev="RMI" value={dossier.indices[0].rmi} color="bg-blue-500" />
                        <IndexBar label="Gravity Impact" abbrev="GIS" value={dossier.indices[0].gis} color="bg-purple-500" />
                        <IndexBar label="Opportunity Delta" abbrev="OD" value={dossier.indices[0].od} color="bg-orange-500" />
                        <IndexBar label="Matchup Space Fit" abbrev="MSF" value={dossier.indices[0].msf} color="bg-green-500" />

                        <div className="pt-4 border-t border-dark-700 space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="flex items-center gap-1 text-dark-400">
                              <Shield className="w-3 h-3" /> Floor
                            </span>
                            <span className="font-mono">{dossier.indices[0].floor_score.toFixed(1)}</span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span className="flex items-center gap-1 text-dark-400">
                              <Minus className="w-3 h-3" /> Median
                            </span>
                            <span className="font-mono">{dossier.indices[0].median_score.toFixed(1)}</span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span className="flex items-center gap-1 text-dark-400">
                              <Zap className="w-3 h-3" /> Ceiling
                            </span>
                            <span className="font-mono">{dossier.indices[0].ceiling_score.toFixed(1)}</span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <p className="text-dark-500 text-sm">No index data available yet.</p>
                    )}
                  </div>

                  <div className="lg:col-span-2 bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-blue-400" />
                      Season Statistics
                    </h2>
                    {dossier.player.stats ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
                        {Object.entries(dossier.player.stats).map(([key, value]) => (
                          <StatRow
                            key={key}
                            label={formatStatLabel(key)}
                            value={typeof value === 'number' ? (Number.isInteger(value) ? value : value.toFixed(2)) : String(value)}
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="text-dark-500 text-sm">No season stats available.</p>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'games' && (
                <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                    <Activity className="w-5 h-5 text-green-400" />
                    Recent Game Logs
                  </h2>
                  {dossier.game_logs.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-dark-700 text-dark-400">
                            <th className="text-left py-2 pr-4">Date</th>
                            <th className="text-left py-2 pr-4">Opp</th>
                            <th className="text-center py-2 pr-4">H/A</th>
                            <th className="text-center py-2 pr-4">W/L</th>
                            <th className="text-right py-2 pr-4">FP</th>
                            {Object.keys(dossier.game_logs[0].stats).map((key) => (
                              <th key={key} className="text-right py-2 pr-4">
                                {formatStatLabel(key)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {dossier.game_logs.map((gl, i) => (
                            <tr key={i} className="border-b border-dark-700/50 hover:bg-dark-700/30">
                              <td className="py-2 pr-4 text-dark-300">{formatDate(gl.game_date)}</td>
                              <td className="py-2 pr-4 font-mono">{gl.opponent ?? '\u2014'}</td>
                              <td className="py-2 pr-4 text-center">
                                {gl.home_away === 'H' ? (
                                  <span className="text-green-400">H</span>
                                ) : gl.home_away === 'A' ? (
                                  <span className="text-blue-400">A</span>
                                ) : '\u2014'}
                              </td>
                              <td className="py-2 pr-4 text-center">
                                {gl.result === 'W' ? (
                                  <ChevronUp className="w-4 h-4 text-green-400 inline" />
                                ) : gl.result === 'L' ? (
                                  <ChevronDown className="w-4 h-4 text-red-400 inline" />
                                ) : '\u2014'}
                              </td>
                              <td className="py-2 pr-4 text-right font-mono font-bold">
                                {gl.fantasy_points?.toFixed(1) ?? '\u2014'}
                              </td>
                              {Object.keys(dossier.game_logs[0].stats).map((key) => (
                                <td key={key} className="py-2 pr-4 text-right font-mono">
                                  {gl.stats[key] ?? '\u2014'}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-dark-500 text-sm">No game logs recorded yet.</p>
                  )}
                </div>
              )}

              {activeTab === 'decisions' && (
                <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                    <History className="w-5 h-5 text-purple-400" />
                    Decision History
                  </h2>
                  {dossier.decisions.length > 0 ? (
                    <div className="space-y-3">
                      {dossier.decisions.map((d) => (
                        <div
                          key={d.id}
                          className="p-4 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-all"
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <p className="text-dark-100 font-medium truncate">{d.query}</p>
                              <p className="text-primary-400 mt-1">{d.decision}</p>
                            </div>
                            <div className="flex items-center gap-2">
                              {d.outcome === 'correct' && <CheckCircle className="w-5 h-5 text-green-400" />}
                              {d.outcome === 'incorrect' && <XCircle className="w-5 h-5 text-red-400" />}
                              {d.outcome === 'pending' && <HelpCircle className="w-5 h-5 text-yellow-400" />}
                              {!d.outcome && <HelpCircle className="w-5 h-5 text-dark-600" />}
                            </div>
                          </div>
                          <div className="flex items-center gap-4 mt-3 text-sm text-dark-500">
                            <span>{formatDate(d.created_at)}</span>
                            <span className="capitalize">{d.decision_type.replace('_', '/')}</span>
                            <span className="capitalize">{d.risk_mode}</span>
                            <span className={getConfidenceColor(d.confidence as 'low' | 'medium' | 'high')}>
                              {d.confidence}
                            </span>
                            <span>{d.source}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-dark-500 text-sm">No decisions involving this player yet.</p>
                  )}
                </div>
              )}
            </>
          ) : null}
        </div>
      </main>
    </div>
  );
}
