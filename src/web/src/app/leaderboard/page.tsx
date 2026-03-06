'use client';

import { useState, useEffect, useCallback } from 'react';
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
} from 'lucide-react';

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

function PlayerRow({ player, mode }: { player: LeaderboardPlayer; mode: RiskMode }) {
  const score = mode === 'floor' ? player.floor_score : mode === 'ceiling' ? player.ceiling_score : player.median_score;
  const isTop3 = player.rank <= 3;

  return (
    <div className={`flex items-center gap-4 p-4 rounded-xl transition-all ${
      isTop3
        ? 'bg-dark-800/80 border border-dark-600'
        : 'bg-dark-800/40 border border-dark-700/50 hover:border-dark-600'
    }`}>
      {/* Rank */}
      <div className={`text-2xl font-bold w-8 text-center flex-shrink-0 ${
        player.rank === 1 ? 'text-yellow-400' :
        player.rank === 2 ? 'text-gray-300' :
        player.rank === 3 ? 'text-amber-600' :
        'text-dark-500'
      }`}>
        {player.rank}
      </div>

      {/* Player info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-dark-100 truncate">{player.name}</span>
          {player.position && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-primary-600/20 text-primary-400 font-medium flex-shrink-0">
              {player.position}
            </span>
          )}
        </div>
        <div className="text-xs text-dark-500 mt-0.5">{player.team ?? 'FA'}</div>
      </div>

      {/* Five-index mini bars (hidden on mobile) */}
      <div className="hidden md:flex items-center gap-3">
        <div className="text-center">
          <div className="text-[10px] text-dark-500 uppercase">SCI</div>
          <IndexBar value={player.sci} />
          <div className="text-[10px] text-dark-400 mt-0.5">{player.sci.toFixed(0)}</div>
        </div>
        <div className="text-center">
          <div className="text-[10px] text-dark-500 uppercase">RMI</div>
          <IndexBar value={player.rmi} />
          <div className="text-[10px] text-dark-400 mt-0.5">{player.rmi.toFixed(0)}</div>
        </div>
        <div className="text-center">
          <div className="text-[10px] text-dark-500 uppercase">GIS</div>
          <IndexBar value={player.gis} />
          <div className="text-[10px] text-dark-400 mt-0.5">{player.gis.toFixed(0)}</div>
        </div>
        <div className="text-center">
          <div className="text-[10px] text-dark-500 uppercase">MSF</div>
          <IndexBar value={player.msf} />
          <div className="text-[10px] text-dark-400 mt-0.5">{player.msf.toFixed(0)}</div>
        </div>
      </div>

      {/* Score */}
      <div className="text-right flex-shrink-0">
        <div className="text-xl font-bold text-primary-400">{score.toFixed(1)}</div>
        <div className="text-[10px] text-dark-500 uppercase">{mode}</div>
      </div>
    </div>
  );
}

export default function LeaderboardPage() {
  const { sport: appSport } = useAppStore();
  const [sport, setSport] = useState<Sport>(appSport);
  const [position, setPosition] = useState<string | null>(null);
  const [mode, setMode] = useState<RiskMode>('median');
  const [players, setPlayers] = useState<LeaderboardPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const positions = SPORT_POSITIONS[sport] || [];

  const fetchLeaderboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getLeaderboard(sport, {
        position: position ?? undefined,
        mode,
        limit: 10,
      });
      setPlayers(data.players);
    } catch {
      setError('Failed to load leaderboard');
      setPlayers([]);
    } finally {
      setLoading(false);
    }
  }, [sport, position, mode]);

  useEffect(() => {
    fetchLeaderboard();
  }, [fetchLeaderboard]);

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

          {/* Sport Selector */}
          <div className="flex items-center gap-2 mb-4">
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

          {/* Content */}
          {loading ? (
            <div className="text-center py-16">
              <Loader2 className="w-12 h-12 text-primary-400 mx-auto mb-4 animate-spin" />
              <p className="text-dark-400">Loading leaderboard...</p>
            </div>
          ) : error ? (
            <div className="text-center py-16">
              <Target className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">{error}</h2>
              <button
                onClick={fetchLeaderboard}
                className="mt-3 text-sm text-primary-400 hover:text-primary-300"
              >
                Try again
              </button>
            </div>
          ) : players.length === 0 ? (
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
                <PlayerRow key={player.player_id} player={player} mode={mode} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
