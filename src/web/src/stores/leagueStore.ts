import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Sport, SleeperUser, SleeperLeague, RosterPlayer } from '@/types';
import api from '@/lib/api';

interface LeagueConnection {
  sleeperUserId: string;
  sleeperUsername: string;
  displayName: string;
  avatar: string | null;
}

interface LeagueState {
  // Persisted
  connection: LeagueConnection | null;
  leaguesBySport: Partial<Record<Sport, SleeperLeague[]>>;
  selectedLeagueIds: Partial<Record<Sport, string>>;

  // Ephemeral
  roster: RosterPlayer[];
  isConnecting: boolean;
  isLoadingLeagues: boolean;
  isLoadingRoster: boolean;
  error: string | null;

  // Actions
  connectSleeper: (username: string, sport: Sport) => Promise<void>;
  selectLeague: (leagueId: string, sport: Sport) => Promise<void>;
  fetchRoster: (leagueId: string, sport: Sport) => Promise<void>;
  syncToBackend: (leagueId: string, sport: Sport) => Promise<void>;
  restoreFromBackend: () => Promise<void>;
  onSportChange: (sport: Sport) => Promise<void>;
  disconnect: () => void;
  clearError: () => void;
}

export const useLeagueStore = create<LeagueState>()(
  persist(
    (set, get) => ({
      // Initial state
      connection: null,
      leaguesBySport: {},
      selectedLeagueIds: {},
      roster: [],
      isConnecting: false,
      isLoadingLeagues: false,
      isLoadingRoster: false,
      error: null,

      connectSleeper: async (username: string, sport: Sport) => {
        set({ isConnecting: true, error: null });

        try {
          const data = await api.connectSleeper(username, sport);
          const user: SleeperUser = data.sleeper_user;

          set((state) => ({
            isConnecting: false,
            connection: {
              sleeperUserId: user.user_id,
              sleeperUsername: user.username,
              displayName: user.display_name || user.username,
              avatar: user.avatar,
            },
            leaguesBySport: {
              ...state.leaguesBySport,
              [sport]: data.leagues,
            },
          }));
        } catch (error) {
          const message =
            error instanceof Error && error.message.includes('404')
              ? 'Sleeper user not found. Check the username and try again.'
              : 'Failed to connect. Please try again.';
          set({ isConnecting: false, error: message });
        }
      },

      selectLeague: async (leagueId: string, sport: Sport) => {
        set((state) => ({
          selectedLeagueIds: {
            ...state.selectedLeagueIds,
            [sport]: leagueId,
          },
        }));

        await get().fetchRoster(leagueId, sport);

        // Persist to backend (non-blocking)
        get().syncToBackend(leagueId, sport).catch(() => {});
      },

      fetchRoster: async (leagueId: string, sport: Sport) => {
        const { connection } = get();
        if (!connection) return;

        set({ isLoadingRoster: true, error: null });

        try {
          const data = await api.getLeagueRoster(
            leagueId,
            connection.sleeperUserId,
            sport
          );
          set({ isLoadingRoster: false, roster: data.players });
        } catch (error) {
          console.error('Failed to fetch roster:', error);
          set({
            isLoadingRoster: false,
            roster: [],
            error: 'Failed to load roster.',
          });
        }
      },

      syncToBackend: async (leagueId: string, sport: Sport) => {
        const { connection } = get();
        if (!connection || !api.isUserAuthenticated()) return;

        try {
          await api.syncLeague(connection.sleeperUsername, leagueId, sport);
        } catch (error) {
          console.error('Failed to sync league to backend:', error);
        }
      },

      restoreFromBackend: async () => {
        if (!api.isUserAuthenticated()) return;

        const { connection, selectedLeagueIds } = get();

        // If we have a local connection, push it to the backend so the DB
        // has the league data (verdicts, commissioner tools, etc. need it).
        if (connection) {
          const leagueId = selectedLeagueIds.nfl || selectedLeagueIds.nba || selectedLeagueIds.mlb || selectedLeagueIds.nhl;
          if (leagueId) {
            const sport = selectedLeagueIds.nfl ? 'nfl'
              : selectedLeagueIds.nba ? 'nba'
              : selectedLeagueIds.mlb ? 'mlb'
              : 'nhl';
            try {
              await api.syncLeague(connection.sleeperUsername, leagueId, sport as Sport);
            } catch {
              // Non-blocking — best effort sync
            }
          }
          return;
        }

        // No local connection — try restoring from backend
        try {
          const data = await api.getMyLeague();
          if (data.connected && data.sleeper_username && data.sleeper_user_id && data.sleeper_league_id) {
            set({
              connection: {
                sleeperUserId: data.sleeper_user_id,
                sleeperUsername: data.sleeper_username,
                displayName: data.sleeper_username,
                avatar: null,
              },
              selectedLeagueIds: { nfl: data.sleeper_league_id },
            });
          }
        } catch (error) {
          console.error('Failed to restore league from backend:', error);
        }
      },

      onSportChange: async (sport: Sport) => {
        const { connection, leaguesBySport, selectedLeagueIds } = get();
        if (!connection) return;

        // Sleeper doesn't support soccer
        if (sport === 'soccer') {
          set({ roster: [] });
          return;
        }

        // Fetch leagues for this sport if not cached
        if (!leaguesBySport[sport]) {
          set({ isLoadingLeagues: true, error: null });
          try {
            const data = await api.connectSleeper(
              connection.sleeperUsername,
              sport
            );
            set((state) => ({
              isLoadingLeagues: false,
              leaguesBySport: {
                ...state.leaguesBySport,
                [sport]: data.leagues,
              },
            }));
          } catch {
            set({ isLoadingLeagues: false, roster: [] });
            return;
          }
        }

        // Auto-select previously chosen league and fetch roster
        const leagueId = selectedLeagueIds[sport];
        if (leagueId) {
          await get().fetchRoster(leagueId, sport);
        } else {
          set({ roster: [] });
        }
      },

      disconnect: () => {
        // Clear backend connection (fire-and-forget)
        if (api.isUserAuthenticated()) {
          api.disconnectLeague().catch((err) =>
            console.error('Failed to disconnect league on backend:', err)
          );
        }

        set({
          connection: null,
          leaguesBySport: {},
          selectedLeagueIds: {},
          roster: [],
          error: null,
        });
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'benchgoblin-league',
      partialize: (state) => ({
        connection: state.connection,
        leaguesBySport: state.leaguesBySport,
        selectedLeagueIds: state.selectedLeagueIds,
      }),
    }
  )
);

// Selector for the active league based on current sport
export function getActiveLeague(
  state: LeagueState,
  sport: Sport
): SleeperLeague | null {
  const leagueId = state.selectedLeagueIds[sport];
  if (!leagueId) return null;
  const leagues = state.leaguesBySport[sport];
  return leagues?.find((l) => l.league_id === leagueId) ?? null;
}

export default useLeagueStore;
