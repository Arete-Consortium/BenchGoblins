'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import { useAppStore } from '@/stores/appStore';
import api from '@/lib/api';
import { getSportDisplayName } from '@/lib/utils';
import type { Sport, RiskMode } from '@/types';
import {
  Trophy,
  Loader2,
  Shield,
  TrendingUp,
  Zap,
  Target,
  Users,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle,
  XCircle,
  Calendar,
} from 'lucide-react';

type Tab = 'top' | 'trending' | 'accuracy' | 'season';

const TABS: { key: Tab; label: string; icon: typeof Trophy }[] = [
  { key: 'top', label: 'Top Players', icon: Trophy },
  { key: 'trending', label: 'Trending', icon: TrendingUp },
  { key: 'accuracy', label: 'Accuracy', icon: Target },
  { key: 'season', label: 'Season', icon: Calendar },
];

// Position config per sport
const SPORT_POSITIONS: Record<string, string[]> = {
  nfl: ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'],
  nba: ['PG', 'SG', 'SF', 'PF', 'C'],
  mlb: ['SP', 'RP', 'C', '1B', '2B', '3B', 'SS', 'OF', 'DH'],
  nhl: ['C', 'LW', 'RW', 'D', 'G'],
  soccer: ['GK', 'DEF', 'MID', 'FWD'],
};

const MODE_CONFIG: { key: RiskMode; label: string; icon: typeof Shield; color: string }[] = [
  { key: 'floor', label: 'Floor', icon: Shield, color: 'text-green-400 bg-green-500/20 border-green-500/30' },
  { key: 'median', label: 'Median', icon: TrendingUp, color: 'text-blue-400 bg-blue-500/20 border-blue-500/30' },
  { key: 'ceiling', label: 'Ceiling', icon: Zap, color: 'text-orange-400 bg-orange-500/20 border-orange-500/30' },
];

interface LeaderboardPlayer {
  rank: number;
  player_id: string;
  name: string;
  team: string | null;
  position: string | null;
  score: number;
  floor_score: number;
  median_score: number;
  ceiling_score: number;
  sci: number;
  rmi: number;
  gis: number;
  od: number;
  msf: number;
  calculated_at: string;
}

interface TrendingPlayer {
  rank: number;
  player_id: string;
  name: string;
  team: string | null;
  position: string | null;
  current_score: number;
  previous_score: number;
  delta: number;
  direction: string;
}

interface AccuracyLeader {
  rank: number;
  user_id: string;
  total_decisions: number;
  correct: number;
  incorrect: number;
  accuracy_pct: number;
}

interface SeasonPlayer {
  player_id: string;
  name: string;
  team: string | null;
  position: string | null;
  avg_floor: number;
  avg_median: number;
  avg_ceiling: number;
  games: number;
  first_seen: string;
  last_seen: string;
}

function IndexBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden w-16">
      <div
        className="h-full bg-primary-500 rounded-full"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function PlayerRow({ player, mode, sport }: { player: LeaderboardPlayer; mode: RiskMode; sport: string }) {
  const score = mode === 'floor' ? player.floor_score : mode === 'ceiling' ? player.ceiling_score : player.median_score;
  const isTop3 = player.rank <= 3;

  return (
    <div className={`flex items-center gap-4 p-4 rounded-xl transition-all ${
      isTop3
        ? 'bg-dark-800/80 border border-dark-600'
        : 'bg-dark-800/40 border border-dark-700/50 hover:border-dark-600'
    }`}>
      <div className={`text-2xl font-bold w-8 text-center flex-shrink-0 ${
        player.rank === 1 ? 'text-yellow-400' :
        player.rank === 2 ? 'text-gray-300' :
        player.rank === 3 ? 'text-amber-600' :
        'text-dark-500'
      }`}>
        {player.rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Link href={`/dossier/${sport}/${player.player_id}`} className="font-semibold text-dark-100 truncate hover:text-primary-400 transition-colors">{player.name}</Link>
          {player.position && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-primary-600/20 text-primary-400 font-medium flex-shrink-0">
              {player.position}
            </span>
          )}
        </div>
        <div className="text-xs text-dark-500 mt-0.5">{player.team ?? 'FA'}</div>
      </div>
      <div className="hidden md:flex items-center gap-3">
        {(['SCI', 'RMI', 'GIS', 'MSF'] as const).map((label) => {
          const key = label.toLowerCase() as 'sci' | 'rmi' | 'gis' | 'msf';
          return (
            <div key={label} className="text-center">
              <div className="text-[10px] text-dark-500 uppercase">{label}</div>
              <IndexBar value={player[key]} />
              <div className="text-[10px] text-dark-400 mt-0.5">{player[key].toFixed(0)}</div>
            </div>
          );
        })}
      </div>
      <div className="text-right flex-shrink-0">
        <div className="text-xl font-bold text-primary-400">{score.toFixed(1)}</div>
        <div className="text-[10px] text-dark-500 uppercase">{mode}</div>
      </div>
    </div>
  );
}

function TrendingRow({ player, sport }: { player: TrendingPlayer; sport: string }) {
  const isUp = player.delta >= 0;
  const isTop3 = player.rank <= 3;

  return (
    <div className={`flex items-center gap-4 p-4 rounded-xl transition-all ${
      isTop3
        ? 'bg-dark-800/80 border border-dark-600'
        : 'bg-dark-800/40 border border-dark-700/50 hover:border-dark-600'
    }`}>
      <div className={`text-2xl font-bold w-8 text-center flex-shrink-0 ${
        player.rank === 1 ? 'text-yellow-400' :
        player.rank === 2 ? 'text-gray-300' :
        player.rank === 3 ? 'text-amber-600' :
        'text-dark-500'
      }`}>
        {player.rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Link href={`/dossier/${sport}/${player.player_id}`} className="font-semibold text-dark-100 truncate hover:text-primary-400 transition-colors">{player.name}</Link>
          {player.position && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-primary-600/20 text-primary-400 font-medium flex-shrink-0">
              {player.position}
            </span>
          )}
        </div>
        <div className="text-xs text-dark-500 mt-0.5">{player.team ?? 'FA'}</div>
      </div>
      <div className="hidden sm:flex items-center gap-4 text-sm">
        <div className="text-dark-500">
          {player.previous_score.toFixed(1)}
        </div>
        <div className="text-dark-600">&rarr;</div>
        <div className="text-dark-200 font-medium">
          {player.current_score.toFixed(1)}
        </div>
      </div>
      <div className={`flex items-center gap-1 text-right flex-shrink-0 ${
        isUp ? 'text-green-400' : 'text-red-400'
      }`}>
        {isUp ? (
          <ArrowUpRight className="w-5 h-5" />
        ) : (
          <ArrowDownRight className="w-5 h-5" />
        )}
        <span className="text-xl font-bold">
          {isUp ? '+' : ''}{player.delta.toFixed(1)}
        </span>
      </div>
    </div>
  );
}

function AccuracyRow({ leader }: { leader: AccuracyLeader }) {
  const isTop3 = leader.rank <= 3;

  return (
    <div className={`flex items-center gap-4 p-4 rounded-xl transition-all ${
      isTop3
        ? 'bg-dark-800/80 border border-dark-600'
        : 'bg-dark-800/40 border border-dark-700/50 hover:border-dark-600'
    }`}>
      <div className={`text-2xl font-bold w-8 text-center flex-shrink-0 ${
        leader.rank === 1 ? 'text-yellow-400' :
        leader.rank === 2 ? 'text-gray-300' :
        leader.rank === 3 ? 'text-amber-600' :
        'text-dark-500'
      }`}>
        {leader.rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-dark-100 truncate">
          User {leader.user_id.slice(0, 8)}...
        </div>
        <div className="text-xs text-dark-500 mt-0.5">
          {leader.total_decisions} decisions
        </div>
      </div>
      <div className="hidden sm:flex items-center gap-3 text-sm">
        <span className="flex items-center gap-1 text-green-400">
          <CheckCircle className="w-3.5 h-3.5" />
          {leader.correct}
        </span>
        <span className="flex items-center gap-1 text-red-400">
          <XCircle className="w-3.5 h-3.5" />
          {leader.incorrect}
        </span>
      </div>
      <div className="text-right flex-shrink-0">
        <div className={`text-xl font-bold ${
          leader.accuracy_pct >= 60 ? 'text-green-400' :
          leader.accuracy_pct >= 40 ? 'text-yellow-400' :
          'text-red-400'
        }`}>
          {leader.accuracy_pct}%
        </div>
        <div className="text-[10px] text-dark-500 uppercase">accuracy</div>
      </div>
    </div>
  );
}

function SeasonRow({ player, rank, mode, sport }: { player: SeasonPlayer; rank: number; mode: RiskMode; sport: string }) {
  const score = mode === 'floor' ? player.avg_floor : mode === 'ceiling' ? player.avg_ceiling : player.avg_median;
  const isTop3 = rank <= 3;

  return (
    <div className={`flex items-center gap-4 p-4 rounded-xl transition-all ${
      isTop3
        ? 'bg-dark-800/80 border border-dark-600'
        : 'bg-dark-800/40 border border-dark-700/50 hover:border-dark-600'
    }`}>
      <div className={`text-2xl font-bold w-8 text-center flex-shrink-0 ${
        rank === 1 ? 'text-yellow-400' :
        rank === 2 ? 'text-gray-300' :
        rank === 3 ? 'text-amber-600' :
        'text-dark-500'
      }`}>
        {rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Link href={`/dossier/${sport}/${player.player_id}`} className="font-semibold text-dark-100 truncate hover:text-primary-400 transition-colors">{player.name}</Link>
          {player.position && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-primary-600/20 text-primary-400 font-medium flex-shrink-0">
              {player.position}
            </span>
          )}
        </div>
        <div className="text-xs text-dark-500 mt-0.5">{player.team ?? 'FA'} &middot; {player.games} games</div>
      </div>
      <div className="hidden sm:flex items-center gap-4 text-xs text-dark-400">
        <div className="text-center">
          <div className="text-dark-500">FLR</div>
          <div>{player.avg_floor.toFixed(1)}</div>
        </div>
        <div className="text-center">
          <div className="text-dark-500">MED</div>
          <div>{player.avg_median.toFixed(1)}</div>
        </div>
        <div className="text-center">
          <div className="text-dark-500">CEL</div>
          <div>{player.avg_ceiling.toFixed(1)}</div>
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className="text-xl font-bold text-primary-400">{score.toFixed(1)}</div>
        <div className="text-[10px] text-dark-500 uppercase">avg {mode}</div>
      </div>
    </div>
  );
}

export default function LeaderboardPage() {
  const { sport: appSport } = useAppStore();
  const [tab, setTab] = useState<Tab>('top');
  const [sport, setSport] = useState<Sport>(appSport);
  const [position, setPosition] = useState<string | null>(null);
  const [mode, setMode] = useState<RiskMode>('median');
  const [trendingDirection, setTrendingDirection] = useState<'up' | 'down'>('up');

  // Season date range
  const [seasonRange, setSeasonRange] = useState<'7d' | '30d' | '90d'>('30d');

  // Data states
  const [players, setPlayers] = useState<LeaderboardPlayer[]>([]);
  const [trending, setTrending] = useState<TrendingPlayer[]>([]);
  const [accuracy, setAccuracy] = useState<AccuracyLeader[]>([]);
  const [seasonPlayers, setSeasonPlayers] = useState<SeasonPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const positions = SPORT_POSITIONS[sport] || [];

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === 'top') {
        const data = await api.getLeaderboard(sport, {
          position: position ?? undefined,
          mode,
          limit: 10,
        });
        setPlayers(data.players);
      } else if (tab === 'trending') {
        const data = await api.getTrending(sport, {
          mode,
          direction: trendingDirection,
          limit: 10,
        });
        setTrending(data.players);
      } else if (tab === 'accuracy') {
        const data = await api.getAccuracyLeaders({
          sport,
          min_decisions: 5,
          limit: 10,
        });
        setAccuracy(data.leaders);
      } else {
        const days = seasonRange === '7d' ? 7 : seasonRange === '90d' ? 90 : 30;
        const endDate = new Date();
        const startDate = new Date(endDate.getTime() - days * 24 * 60 * 60 * 1000);
        const data = await api.getSeasonSnapshot(sport, {
          start: startDate.toISOString().slice(0, 10),
          end: endDate.toISOString().slice(0, 10),
          position: position ?? undefined,
          mode,
          limit: 25,
        });
        setSeasonPlayers(data.players);
      }
    } catch {
      setError(`Failed to load ${tab} data`);
    } finally {
      setLoading(false);
    }
  }, [tab, sport, position, mode, trendingDirection, seasonRange]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Reset position when sport changes
  useEffect(() => {
    setPosition(null);
  }, [sport]);

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-6">
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Trophy className="w-8 h-8 text-yellow-400" />
              Leaderboard
            </h1>
            <p className="text-dark-400 mt-2">
              Top players ranked by BenchGoblins five-index scoring system.
            </p>
          </div>

          {/* Tab Selector */}
          <div className="flex gap-1 mb-6 bg-dark-800/50 rounded-lg p-1 border border-dark-700">
            {TABS.map((t) => {
              const Icon = t.icon;
              const isSelected = tab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-all ${
                    isSelected
                      ? 'bg-dark-700 text-white shadow-sm'
                      : 'text-dark-400 hover:text-dark-200'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Sport Selector */}
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <span className="text-dark-400 text-sm">Sport:</span>
            {(['nfl', 'nba', 'mlb', 'nhl', 'soccer'] as Sport[]).map((s) => (
              <button
                key={s}
                onClick={() => setSport(s)}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-all ${
                  sport === s
                    ? 'bg-primary-600 text-white'
                    : 'bg-dark-700 text-dark-300 hover:bg-dark-600'
                }`}
              >
                {getSportDisplayName(s)}
              </button>
            ))}
          </div>

          {/* Tab-specific controls */}
          {tab === 'top' && (
            <>
              {/* Position Filter */}
              <div className="flex items-center gap-2 mb-4 flex-wrap">
                <span className="text-dark-400 text-sm">Position:</span>
                <button
                  onClick={() => setPosition(null)}
                  className={`px-3 py-1 rounded-full text-sm font-medium transition-all ${
                    position === null
                      ? 'bg-primary-600 text-white'
                      : 'bg-dark-700 text-dark-300 hover:bg-dark-600'
                  }`}
                >
                  <Users className="w-3.5 h-3.5 inline mr-1" />
                  All
                </button>
                {positions.map((pos) => (
                  <button
                    key={pos}
                    onClick={() => setPosition(pos)}
                    className={`px-3 py-1 rounded-full text-sm font-medium transition-all ${
                      position === pos
                        ? 'bg-primary-600 text-white'
                        : 'bg-dark-700 text-dark-300 hover:bg-dark-600'
                    }`}
                  >
                    {pos}
                  </button>
                ))}
              </div>

              {/* Risk Mode Selector */}
              <div className="flex gap-2 mb-6">
                {MODE_CONFIG.map((m) => {
                  const Icon = m.icon;
                  const isSelected = mode === m.key;
                  return (
                    <button
                      key={m.key}
                      onClick={() => setMode(m.key)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-all ${
                        isSelected
                          ? m.color
                          : 'border-dark-700 text-dark-400 hover:border-dark-600 hover:text-dark-300'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      {m.label}
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {tab === 'season' && (
            <div className="flex flex-wrap items-center gap-3 mb-6">
              {/* Date Range */}
              <div className="flex gap-1 bg-dark-800/50 rounded-lg p-0.5 border border-dark-700">
                {(['7d', '30d', '90d'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setSeasonRange(r)}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                      seasonRange === r
                        ? 'bg-primary-600/20 text-primary-400'
                        : 'text-dark-400 hover:text-dark-200'
                    }`}
                  >
                    {r === '7d' ? 'Last 7 days' : r === '30d' ? 'Last 30 days' : 'Last 90 days'}
                  </button>
                ))}
              </div>
              {/* Risk Mode */}
              <div className="flex gap-2">
                {MODE_CONFIG.map((m) => {
                  const Icon = m.icon;
                  const isSelected = mode === m.key;
                  return (
                    <button
                      key={m.key}
                      onClick={() => setMode(m.key)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm font-medium transition-all ${
                        isSelected
                          ? m.color
                          : 'border-dark-700 text-dark-400 hover:border-dark-600 hover:text-dark-300'
                      }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {m.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {tab === 'trending' && (
            <div className="flex flex-wrap items-center gap-3 mb-6">
              {/* Risk Mode */}
              <div className="flex gap-2">
                {MODE_CONFIG.map((m) => {
                  const Icon = m.icon;
                  const isSelected = mode === m.key;
                  return (
                    <button
                      key={m.key}
                      onClick={() => setMode(m.key)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm font-medium transition-all ${
                        isSelected
                          ? m.color
                          : 'border-dark-700 text-dark-400 hover:border-dark-600 hover:text-dark-300'
                      }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {m.label}
                    </button>
                  );
                })}
              </div>
              {/* Direction toggle */}
              <div className="flex gap-1 bg-dark-800/50 rounded-lg p-0.5 border border-dark-700">
                <button
                  onClick={() => setTrendingDirection('up')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    trendingDirection === 'up'
                      ? 'bg-green-500/20 text-green-400'
                      : 'text-dark-400 hover:text-dark-200'
                  }`}
                >
                  <ArrowUpRight className="w-4 h-4" />
                  Risers
                </button>
                <button
                  onClick={() => setTrendingDirection('down')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    trendingDirection === 'down'
                      ? 'bg-red-500/20 text-red-400'
                      : 'text-dark-400 hover:text-dark-200'
                  }`}
                >
                  <ArrowDownRight className="w-4 h-4" />
                  Fallers
                </button>
              </div>
            </div>
          )}

          {/* Content */}
          {loading ? (
            <div className="text-center py-16">
              <Loader2 className="w-12 h-12 text-primary-400 mx-auto mb-4 animate-spin" />
              <p className="text-dark-400">Loading...</p>
            </div>
          ) : error ? (
            <div className="text-center py-16">
              <Target className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">{error}</h2>
              <button
                onClick={fetchData}
                className="mt-3 text-sm text-primary-400 hover:text-primary-300"
              >
                Try again
              </button>
            </div>
          ) : tab === 'top' ? (
            players.length === 0 ? (
              <div className="text-center py-16">
                <Trophy className="w-16 h-16 text-dark-600 mx-auto mb-4" />
                <h2 className="text-xl font-semibold text-dark-300">
                  No players found{position ? ` for ${position}` : ''}
                </h2>
                <p className="text-dark-500 mt-2">
                  Player index data is generated when verdicts are requested.
                  Try asking the Goblin about some players first!
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {players.map((player) => (
                  <PlayerRow key={player.player_id} player={player} mode={mode} sport={sport} />
                ))}
              </div>
            )
          ) : tab === 'trending' ? (
            trending.length === 0 ? (
              <div className="text-center py-16">
                <TrendingUp className="w-16 h-16 text-dark-600 mx-auto mb-4" />
                <h2 className="text-xl font-semibold text-dark-300">No trending data yet</h2>
                <p className="text-dark-500 mt-2">
                  Trending requires at least 7 days of player index history.
                  Check back soon!
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {trending.map((player) => (
                  <TrendingRow key={player.player_id} player={player} sport={sport} />
                ))}
              </div>
            )
          ) : tab === 'accuracy' ? (
            accuracy.length === 0 ? (
              <div className="text-center py-16">
                <Target className="w-16 h-16 text-dark-600 mx-auto mb-4" />
                <h2 className="text-xl font-semibold text-dark-300">No accuracy data yet</h2>
                <p className="text-dark-500 mt-2">
                  Users need at least 5 resolved decisions to appear on the accuracy leaderboard.
                  Keep making calls!
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {accuracy.map((leader) => (
                  <AccuracyRow key={leader.user_id} leader={leader} />
                ))}
              </div>
            )
          ) : (
            seasonPlayers.length === 0 ? (
              <div className="text-center py-16">
                <Calendar className="w-16 h-16 text-dark-600 mx-auto mb-4" />
                <h2 className="text-xl font-semibold text-dark-300">No season data yet</h2>
                <p className="text-dark-500 mt-2">
                  Season averages build up as more player indices are calculated.
                  Try a wider date range or check back later!
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {seasonPlayers.map((player, i) => (
                  <SeasonRow key={player.player_id} player={player} rank={i + 1} mode={mode} sport={sport} />
                ))}
              </div>
            )
          )}
        </div>
      </main>
    </div>
  );
}
