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
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import type { Sport, SleeperLeague, RosterPlayer } from '@/types';

const SPORT_NAMES: Record<Sport, string> = {
  nba: 'NBA',
  nfl: 'NFL',
  mlb: 'MLB',
  nhl: 'NHL',
  soccer: 'Soccer',
};

type Platform = 'sleeper' | 'espn' | 'yahoo';
type Step = 'platform' | 'leagues' | 'roster' | 'espn-creds' | 'espn-done' | 'yahoo-info';

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
  const [platform, setPlatform] = useState<Platform>('sleeper');
  const [username, setUsername] = useState('');

  // ESPN credential state
  const [espnSwid, setEspnSwid] = useState('');
  const [espnS2, setEspnS2] = useState('');
  const [espnLeagueId, setEspnLeagueId] = useState('');
  const [espnTeamId, setEspnTeamId] = useState('');
  const [espnLoading, setEspnLoading] = useState(false);
  const [espnError, setEspnError] = useState<string | null>(null);
  const [espnResult, setEspnResult] = useState<{ roster_player_count: number } | null>(null);

  // Wrap onOpenChange to reset step when dialog opens
  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      const state = useLeagueStore.getState();
      if (state.connection && state.selectedLeagueIds[sport]) {
        setStep('roster');
        setPlatform('sleeper');
      } else if (state.connection && state.leaguesBySport[sport]?.length) {
        setStep('leagues');
        setPlatform('sleeper');
      } else {
        setStep('platform');
      }
      setEspnError(null);
      setEspnResult(null);
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
      } else {
        // Connected but no leagues for this sport — still advance to show empty state
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

  const handleESPNConnect = async () => {
    if (!espnSwid.trim() || !espnS2.trim() || !espnLeagueId.trim() || !espnTeamId.trim()) return;
    setEspnLoading(true);
    setEspnError(null);
    try {
      const result = await api.syncESPN(
        espnSwid.trim(),
        espnS2.trim(),
        espnLeagueId.trim(),
        espnTeamId.trim(),
        sport === 'soccer' ? 'nfl' : sport,
      );
      setEspnResult(result);
      setStep('espn-done');
    } catch (err) {
      const msg = err instanceof Error && err.message.includes('401')
        ? 'Invalid ESPN credentials. Check your SWID and espn_s2 cookies.'
        : 'Failed to connect ESPN. Please try again.';
      setEspnError(msg);
    } finally {
      setEspnLoading(false);
    }
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
              <Button
                className={cn('flex-1', platform === 'sleeper' ? 'bg-primary-600 hover:bg-primary-700' : '')}
                variant={platform === 'sleeper' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setPlatform('sleeper')}
              >
                Sleeper
              </Button>
              <Button
                className={cn('flex-1', platform === 'espn' ? 'bg-primary-600 hover:bg-primary-700' : '')}
                variant={platform === 'espn' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setPlatform('espn')}
              >
                ESPN
              </Button>
              <Button
                className={cn('flex-1', platform === 'yahoo' ? 'bg-primary-600 hover:bg-primary-700' : '')}
                variant={platform === 'yahoo' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setPlatform('yahoo')}
              >
                Yahoo
              </Button>
            </div>

            {platform === 'sleeper' && (
              <div className="space-y-3">
                <label className="text-xs text-dark-400">
                  Your Sleeper @username (found in Sleeper app &gt; Profile)
                </label>
                <Input
                  placeholder="e.g. @fantasygoblin"
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
            )}

            {platform === 'espn' && (
              <div className="space-y-3">
                <p className="text-xs text-dark-400">
                  Paste your ESPN cookies from DevTools &gt; Application &gt; Cookies.
                </p>
                <Input
                  placeholder="SWID (e.g., {ABCD-1234-...})"
                  value={espnSwid}
                  onChange={(e) => setEspnSwid(e.target.value)}
                  disabled={espnLoading}
                />
                <Input
                  placeholder="espn_s2 cookie"
                  value={espnS2}
                  onChange={(e) => setEspnS2(e.target.value)}
                  disabled={espnLoading}
                />
                <Input
                  placeholder="League ID"
                  value={espnLeagueId}
                  onChange={(e) => setEspnLeagueId(e.target.value)}
                  disabled={espnLoading}
                />
                <Input
                  placeholder="Team ID (your team number)"
                  value={espnTeamId}
                  onChange={(e) => setEspnTeamId(e.target.value)}
                  disabled={espnLoading}
                />

                {espnError && (
                  <div className="flex items-center gap-2 text-sm text-red-400">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    {espnError}
                  </div>
                )}

                <Button
                  onClick={handleESPNConnect}
                  disabled={espnLoading || !espnSwid.trim() || !espnS2.trim() || !espnLeagueId.trim() || !espnTeamId.trim()}
                  className="w-full"
                >
                  {espnLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      Connecting...
                    </>
                  ) : (
                    'Connect ESPN'
                  )}
                </Button>

                <p className="text-xs text-dark-500 flex items-center gap-1.5">
                  <Shield className="h-3 w-3" />
                  Your ESPN cookies are stored securely and only used to fetch your roster.
                </p>
              </div>
            )}

            {platform === 'yahoo' && (
              <div className="space-y-3">
                <p className="text-sm text-dark-400">
                  Connect your Yahoo Fantasy account via OAuth to sync your league and roster.
                </p>
                <p className="text-xs text-dark-500">
                  Yahoo requires OAuth authentication. Click below to authorize BenchGoblin
                  to read your fantasy leagues and rosters.
                </p>

                <Button
                  onClick={async () => {
                    try {
                      const redirectUri = `${window.location.origin}/auth/yahoo/callback`;
                      const { auth_url } = await api.getYahooAuthUrl(redirectUri);
                      window.open(auth_url, '_blank', 'width=600,height=700');
                    } catch {
                      setEspnError('Failed to start Yahoo OAuth flow.');
                    }
                  }}
                  className="w-full"
                >
                  Connect with Yahoo
                </Button>

                <p className="text-xs text-dark-500 flex items-center gap-1.5">
                  <Shield className="h-3 w-3" />
                  We only request read access to your fantasy leagues and rosters.
                </p>
              </div>
            )}
          </>
        )}

        {step === 'espn-done' && espnResult && (
          <>
            <DialogHeader>
              <DialogTitle>ESPN Connected</DialogTitle>
              <DialogDescription>
                {espnResult.roster_player_count} players synced from your ESPN roster.
              </DialogDescription>
            </DialogHeader>

            <div className="text-center py-4">
              <div className="text-4xl mb-2">🏈</div>
              <p className="text-sm text-dark-400">
                Your ESPN roster will be used for personalized recommendations.
              </p>
            </div>

            <Button onClick={() => onOpenChange(false)} className="w-full">
              Done
            </Button>
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

            {/* Connected user confirmation */}
            {connection && (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                {connection.avatar && (
                  <img
                    src={`https://sleepercdn.com/avatars/thumbs/${connection.avatar}`}
                    alt=""
                    className="w-8 h-8 rounded-full"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-green-400 truncate">
                    Connected as {connection.displayName}
                  </p>
                  <p className="text-xs text-dark-400">
                    ID: {connection.sleeperUserId}
                  </p>
                </div>
              </div>
            )}

            {leagues.length === 0 ? (
              <div className="text-center py-6">
                <p className="text-dark-400 text-sm">
                  No {SPORT_NAMES[sport]} leagues found for {connection?.sleeperUsername}.
                </p>
                <p className="text-dark-500 text-xs mt-1">Try selecting a different sport or check the season.</p>
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
