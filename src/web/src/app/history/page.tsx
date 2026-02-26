'use client';

import { useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { useHistoryStore } from '@/stores/historyStore';
import { cn, formatDate, getConfidenceColor, getSportDisplayName } from '@/lib/utils';
import type { Sport } from '@/types';
import {
  Clock,
  CheckCircle,
  XCircle,
  HelpCircle,
  Bot,
  Cpu,
  Filter,
  RefreshCw,
} from 'lucide-react';

export default function HistoryPage() {
  const { items, isLoading, hasMore, filter, fetchHistory, setFilter } = useHistoryStore();

  useEffect(() => {
    if (items.length === 0) {
      fetchHistory(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilterChange = (newSport: Sport) => {
    if (filter === newSport) {
      setFilter(null);
    } else {
      setFilter(newSport);
    }
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="text-3xl font-bold">Decision History</h1>
              <p className="text-dark-400 mt-1">
                Review your past fantasy decisions and outcomes
              </p>
            </div>
            <button
              onClick={() => fetchHistory(true)}
              disabled={isLoading}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-lg',
                'bg-dark-800 text-dark-300 hover:bg-dark-700 transition-all',
                isLoading && 'opacity-50 cursor-not-allowed'
              )}
            >
              <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
              Refresh
            </button>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-4 mb-6 p-4 bg-dark-800/50 border border-dark-700 rounded-xl">
            <Filter className="w-5 h-5 text-dark-400" />
            <span className="text-dark-400 text-sm">Filter by sport:</span>
            <div className="flex gap-2">
              {(['nba', 'nfl', 'mlb', 'nhl', 'soccer'] as Sport[]).map((s) => (
                <button
                  key={s}
                  onClick={() => handleFilterChange(s)}
                  className={cn(
                    'px-3 py-1 rounded-full text-sm font-medium transition-all',
                    filter === s
                      ? 'bg-primary-600 text-white'
                      : 'bg-dark-700 text-dark-300 hover:bg-dark-600'
                  )}
                >
                  {getSportDisplayName(s)}
                </button>
              ))}
            </div>
            {filter && (
              <button
                onClick={() => setFilter(null)}
                className="text-sm text-dark-400 hover:text-dark-200"
              >
                Clear
              </button>
            )}
          </div>

          {/* History List */}
          {isLoading && items.length === 0 ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 animate-pulse">
                  <div className="h-4 bg-dark-700 rounded w-3/4 mb-3" />
                  <div className="h-3 bg-dark-700 rounded w-1/2 mb-4" />
                  <div className="flex gap-3">
                    <div className="h-3 bg-dark-700 rounded w-16" />
                    <div className="h-3 bg-dark-700 rounded w-12" />
                    <div className="h-3 bg-dark-700 rounded w-20" />
                  </div>
                </div>
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-16">
              <Clock className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-dark-300">No decisions yet</h2>
              <p className="text-dark-500 mt-2">
                Your decision history will appear here once you start asking questions.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 hover:border-dark-600 transition-all"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-dark-100 font-medium truncate">{item.query}</p>
                      <p className="text-primary-400 mt-1">{item.decision}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Outcome indicator */}
                      {item.outcome === 'correct' && (
                        <CheckCircle className="w-5 h-5 text-green-400" />
                      )}
                      {item.outcome === 'incorrect' && (
                        <XCircle className="w-5 h-5 text-red-400" />
                      )}
                      {item.outcome === 'pending' && (
                        <HelpCircle className="w-5 h-5 text-yellow-400" />
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-4 mt-3 text-sm">
                    <span className="text-dark-500">{formatDate(item.created_at)}</span>
                    <span className="px-2 py-0.5 rounded bg-dark-700 text-dark-300">
                      {getSportDisplayName(item.sport)}
                    </span>
                    <span className="capitalize text-dark-400">{item.risk_mode}</span>
                    <span className={cn('font-medium', getConfidenceColor(item.confidence))}>
                      {item.confidence} confidence
                    </span>
                    <span className="flex items-center gap-1 text-dark-500">
                      {item.source === 'local' ? (
                        <Cpu className="w-3 h-3" />
                      ) : (
                        <Bot className="w-3 h-3" />
                      )}
                      {item.source}
                    </span>
                  </div>
                </div>
              ))}

              {/* Load more */}
              {hasMore && (
                <button
                  onClick={() => fetchHistory()}
                  disabled={isLoading}
                  className={cn(
                    'w-full py-3 rounded-xl bg-dark-800 text-dark-300',
                    'hover:bg-dark-700 transition-all',
                    isLoading && 'opacity-50 cursor-not-allowed'
                  )}
                >
                  {isLoading ? 'Loading...' : 'Load More'}
                </button>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
