'use client';

import { useState, useCallback } from 'react';
import { Loader2, ArrowLeft, AlertCircle, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useLeagueStore } from '@/stores/leagueStore';
import { useAppStore } from '@/stores/appStore';
import type { Sport, SleeperLeague, RosterPlayer } from '@/types';

const SPORT_NAMES: Record<Sport, string> = {
  nba: 'NBA',
  nfl: 'NFL',
  mlb: 'MLB',
  nhl: 'NHL',
  soccer: 'Soccer',
};

type Step = 'platform' | 'leagues' | 'roster';

interface LeagueConnectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LeagueConnectDialog({ open, onOpenChange }: LeagueConnectDialogProps) {
  const sport = useAppStore((s) => s.sport);
  const {
    connection,
    leaguesBySport,
    selectedLeagueIds,
    roster,
    isConnecting,
    isLoadingRoster,
    error,
    connectSleeper,
    selectLeague,
  } = useLeagueStore();

  const [step, setStep] = useState<Step>('platform');
  const [username, setUsername] = useState('');

  // Wrap onOpenChange to reset step when dialog opens
  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      const state = useLeagueStore.getState();
      if (state.connection && state.selectedLeagueIds[sport]) {
        setStep('roster');
      } else if (state.connection && state.leaguesBySport[sport]?.length) {
        setStep('leagues');
      } else {
        setStep('platform');
        setUsername(state.connection?.sleeperUsername || '');
      }
      state.clearError();
    }
    onOpenChange(nextOpen);
  }, [sport, onOpenChange]);

  const leagues = leaguesBySport[sport] || [];

  const handleConnect = async () => {
    if (!username.trim()) return;
    await connectSleeper(username.trim(), sport);
    const state = useLeagueStore.getState();
    if (state.connection && !state.error) {
      const sportLeagues = state.leaguesBySport[sport] || [];
      if (sportLeagues.length > 0) {
        setStep('leagues');
      }
    }
  };

  const handleSelectLeague = async (league: SleeperLeague) => {
    await selectLeague(league.league_id, sport);
    setStep('roster');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleConnect();
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        {step === 'platform' && (
          <>
            <DialogHeader>
              <DialogTitle>Connect Your League</DialogTitle>
              <DialogDescription>
                Import your roster for personalized recommendations.
              </DialogDescription>
            </DialogHeader>

            {/* Platform selector */}
            <div className="flex gap-2">
              <Button className="flex-1 bg-primary-600 hover:bg-primary-700" size="sm">
                Sleeper
              </Button>
              <Button variant="outline" className="flex-1 opacity-50 cursor-not-allowed" size="sm" disabled>
                ESPN <span className="text-xs ml-1 text-dark-500">Soon</span>
              </Button>
              <Button variant="outline" className="flex-1 opacity-50 cursor-not-allowed" size="sm" disabled>
                Yahoo <span className="text-xs ml-1 text-dark-500">Soon</span>
              </Button>
            </div>

            {/* Username input */}
            <div className="space-y-3">
              <Input
                placeholder="Sleeper username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isConnecting}
                autoFocus
              />

              {error && (
                <div className="flex items-center gap-2 text-sm text-red-400">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {error}
                </div>
              )}

              <Button
                onClick={handleConnect}
                disabled={isConnecting || !username.trim()}
                className="w-full"
              >
                {isConnecting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Connecting...
                  </>
                ) : (
                  'Connect'
                )}
              </Button>

              <p className="text-xs text-dark-500 flex items-center gap-1.5">
                <Shield className="h-3 w-3" />
                Sleeper&apos;s API is public — we only read your leagues and roster.
              </p>
            </div>
          </>
        )}

        {step === 'leagues' && (
          <>
            <DialogHeader>
              <DialogTitle>Select a League</DialogTitle>
              <DialogDescription>
                {connection?.displayName}&apos;s {SPORT_NAMES[sport]} leagues
              </DialogDescription>
            </DialogHeader>

            {leagues.length === 0 ? (
              <div className="text-center py-6">
                <p className="text-dark-400 text-sm">
                  No {SPORT_NAMES[sport]} leagues found for {connection?.sleeperUsername}.
                </p>
                <p className="text-dark-500 text-xs mt-1">Try selecting a different sport.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {leagues.map((league) => (
                  <button
                    key={league.league_id}
                    onClick={() => handleSelectLeague(league)}
                    className="w-full text-left p-3 rounded-lg border border-dark-700 bg-dark-800/50 hover:bg-dark-800 hover:border-dark-600 transition-all"
                  >
                    <div className="font-medium text-sm">{league.name}</div>
                    <div className="text-xs text-dark-400 mt-0.5">
                      {league.season} &middot; {league.total_rosters} teams &middot; {league.status}
                    </div>
                  </button>
                ))}
              </div>
            )}

            <button
              onClick={() => setStep('platform')}
              className="text-sm text-dark-400 hover:text-dark-200 flex items-center gap-1"
            >
              <ArrowLeft className="h-3 w-3" />
              Change User
            </button>
          </>
        )}

        {step === 'roster' && (
          <>
            <DialogHeader>
              <DialogTitle>
                {leagues.find((l) => l.league_id === selectedLeagueIds[sport])?.name || 'Your Roster'}
              </DialogTitle>
              <DialogDescription>
                {roster.length} players on your roster
              </DialogDescription>
            </DialogHeader>

            {isLoadingRoster ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-primary-400" />
              </div>
            ) : (
              <RosterView players={roster} />
            )}

            <div className="flex items-center justify-between">
              <button
                onClick={() => setStep('leagues')}
                className="text-sm text-dark-400 hover:text-dark-200 flex items-center gap-1"
              >
                <ArrowLeft className="h-3 w-3" />
                Change League
              </button>
              <Button onClick={() => onOpenChange(false)} size="sm">
                Done
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// Position badge colors
const POSITION_COLORS: Record<string, string> = {
  QB: 'bg-red-500/20 text-red-400',
  RB: 'bg-blue-500/20 text-blue-400',
  WR: 'bg-green-500/20 text-green-400',
  TE: 'bg-orange-500/20 text-orange-400',
  K: 'bg-purple-500/20 text-purple-400',
  DEF: 'bg-dark-600 text-dark-300',
  C: 'bg-blue-500/20 text-blue-400',
  PF: 'bg-green-500/20 text-green-400',
  SF: 'bg-green-500/20 text-green-400',
  SG: 'bg-orange-500/20 text-orange-400',
  PG: 'bg-red-500/20 text-red-400',
};

function RosterView({ players }: { players: RosterPlayer[] }) {
  const starters = players.filter((p) => p.is_starter);
  const bench = players.filter((p) => !p.is_starter);

  return (
    <div className="space-y-4 max-h-[40vh] overflow-y-auto">
      {starters.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-dark-400 uppercase mb-2">Starters</h4>
          <div className="space-y-1">
            {starters.map((p) => (
              <PlayerRow key={p.player_id} player={p} />
            ))}
          </div>
        </div>
      )}
      {bench.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-dark-400 uppercase mb-2">Bench</h4>
          <div className="space-y-1">
            {bench.map((p) => (
              <PlayerRow key={p.player_id} player={p} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PlayerRow({ player }: { player: RosterPlayer }) {
  const posColor = POSITION_COLORS[player.position] || 'bg-dark-600 text-dark-300';

  return (
    <div className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-dark-800/50">
      <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${posColor}`}>
        {player.position}
      </span>
      <span className="text-sm flex-1 truncate">{player.full_name}</span>
      {player.team && (
        <span className="text-xs text-dark-500">{player.team}</span>
      )}
      {player.injury_status && (
        <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
          {player.injury_status}
        </span>
      )}
    </div>
  );
}
