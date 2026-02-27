'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Header } from '@/components/layout/Header';
import { useAppStore } from '@/stores/appStore';
import api from '@/lib/api';
import { getSportDisplayName } from '@/lib/utils';
import type { Sport, Player } from '@/types';
import {
  Search,
  FileText,
  User,
  Loader2,
} from 'lucide-react';

export default function DossierSearchPage() {
  const router = useRouter();
  const { sport } = useAppStore();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Player[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [selectedSport, setSelectedSport] = useState<Sport>(sport);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;

    setSearching(true);
    setSearched(true);
    try {
      const players = await api.searchPlayers(query.trim(), selectedSport);
      setResults(players);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [query, selectedSport]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <FileText className="w-8 h-8 text-primary-400" />
              Player Dossier
            </h1>
            <p className="text-dark-400 mt-2">
              Comprehensive player profiles with stats, five-index scores, game logs, and decision history.
            </p>
          </div>

          <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-dark-400 text-sm">Sport:</span>
              {(['nba', 'nfl', 'mlb', 'nhl', 'soccer'] as Sport[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setSelectedSport(s)}
                  className={`px-3 py-1 rounded-full text-sm font-medium transition-all ${
                    selectedSport === s
                      ? 'bg-primary-600 text-white'
                      : 'bg-dark-700 text-dark-300 hover:bg-dark-600'
                  }`}
                >
                  {getSportDisplayName(s)}
                </button>
              ))}
            </div>

            <div className="flex gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-500" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search for a player by name..."
                  className="w-full pl-10 pr-4 py-3 bg-dark-700 border border-dark-600 rounded-lg text-dark-100 placeholder:text-dark-500 focus:outline-none focus:border-primary-500 transition-colors"
                />
              </div>
              <button
                onClick={handleSearch}
                disabled={searching || !query.trim()}
                className="px-6 py-3 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
              >
                {searching ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Search className="w-5 h-5" />
                )}
                Search
              </button>
            </div>
          </div>

          {searching ? (
            <div className="text-center py-16">
              <Loader2 className="w-12 h-12 text-primary-400 mx-auto mb-4 animate-spin" />
              <p className="text-dark-400">Searching players...</p>
            </div>
          ) : results.length > 0 ? (
            <div className="space-y-2">
              <p className="text-dark-500 text-sm mb-4">
                {results.length} player{results.length !== 1 ? 's' : ''} found
              </p>
              {results.map((player) => (
                <button
                  key={player.id}
                  onClick={() => router.push(`/dossier/${selectedSport}/${player.id}`)}
                  className="w-full flex items-center gap-4 p-4 bg-dark-800/50 border border-dark-700 rounded-xl hover:border-primary-600/50 hover:bg-dark-800 transition-all text-left"
                >
                  <div className="w-12 h-12 rounded-lg bg-dark-700 flex items-center justify-center">
                    <User className="w-6 h-6 text-dark-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-dark-100">{player.name}</div>
                    <div className="text-sm text-dark-400">
                      {player.position} — {player.team}
                    </div>
                  </div>
                  <div className="text-dark-500">
                    <FileText className="w-5 h-5" />
                  </div>
                </button>
              ))}
            </div>
          ) : searched && !searching ? (
            <div className="text-center py-16">
              <Search className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">No players found</h2>
              <p className="text-dark-500 mt-2">
                Try a different name or switch sports.
              </p>
            </div>
          ) : (
            <div className="text-center py-16">
              <FileText className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">Search for a Player</h2>
              <p className="text-dark-500 mt-2">
                Enter a player name above to view their comprehensive dossier.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
