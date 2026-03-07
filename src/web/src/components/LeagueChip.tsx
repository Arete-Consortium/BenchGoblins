'use client';

import { Link2, X } from 'lucide-react';
import { useLeagueStore, getActiveLeague } from '@/stores/leagueStore';
import { useAppStore } from '@/stores/appStore';

interface LeagueChipProps {
  onOpen: () => void;
}

export function LeagueChip({ onOpen }: LeagueChipProps) {
  const sport = useAppStore((s) => s.sport);
  const connection = useLeagueStore((s) => s.connection);
  const activeLeague = useLeagueStore((s) => getActiveLeague(s, sport));
  const selectedLeagueIds = useLeagueStore((s) => s.selectedLeagueIds);
  const disconnect = useLeagueStore((s) => s.disconnect);

  // Hide for soccer (Sleeper doesn't support it)
  if (sport === 'soccer') return null;

  // Connected with an active league for this sport
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

  // Connected but no league selected for this sport — show username + nudge
  if (connection) {
    const linkedCount = Object.keys(selectedLeagueIds).length;
    return (
      <button
        onClick={onOpen}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dark-800 border border-dark-700 text-dark-300 hover:text-dark-100 hover:border-dark-600 transition-all"
      >
        <span className="w-2 h-2 rounded-full bg-yellow-400 shrink-0" />
        <span className="text-sm truncate max-w-[120px]">{connection.displayName}</span>
        {linkedCount > 0 && (
          <span className="text-xs text-dark-500">{linkedCount} linked</span>
        )}
      </button>
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
