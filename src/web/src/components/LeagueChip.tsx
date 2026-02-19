'use client';

import { Link2, X } from 'lucide-react';
import { useLeagueStore, getActiveLeague } from '@/stores/leagueStore';
import { useAppStore } from '@/stores/appStore';
import { useAuthStore } from '@/stores/authStore';

interface LeagueChipProps {
  onOpen: () => void;
}

export function LeagueChip({ onOpen }: LeagueChipProps) {
  const sport = useAppStore((s) => s.sport);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const connection = useLeagueStore((s) => s.connection);
  const activeLeague = useLeagueStore((s) => getActiveLeague(s, sport));
  const disconnect = useLeagueStore((s) => s.disconnect);

  // Hide for soccer (Sleeper doesn't support it) or unauthenticated users
  if (sport === 'soccer' || !isAuthenticated) return null;

  if (connection && activeLeague) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dark-800 border border-dark-700">
        <span className="w-2 h-2 rounded-full bg-green-400 shrink-0" />
        <button
          onClick={onOpen}
          className="text-sm text-dark-200 truncate max-w-[140px] hover:text-dark-100 transition-colors"
        >
          {activeLeague.name}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            disconnect();
          }}
          className="text-dark-500 hover:text-dark-200 transition-colors ml-0.5"
          title="Disconnect"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={onOpen}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dark-800 border border-dark-700 text-dark-400 hover:text-dark-200 hover:border-dark-600 transition-all"
    >
      <Link2 className="w-4 h-4" />
      <span className="text-sm">Connect League</span>
    </button>
  );
}
