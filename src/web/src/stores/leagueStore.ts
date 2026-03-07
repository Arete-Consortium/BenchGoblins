import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Sport, SleeperUser, SleeperLeague, RosterPlayer } from '@/types';
import api from '@/lib/api';

// Demo league + roster data per sport
const DEMO_LEAGUES: Record<string, SleeperLeague[]> = {
  nfl: [{ league_id: 'demo-nfl', name: 'The Show Fantasy League', sport: 'nfl', season: '2025', status: 'in_season', total_rosters: 12, roster_positions: ['QB','RB','RB','WR','WR','TE','FLEX','K','DEF'], scoring_settings: {} }],
  nba: [{ league_id: 'demo-nba', name: 'Goblin Court League', sport: 'nba', season: '2025', status: 'in_season', total_rosters: 10, roster_positions: ['PG','SG','SF','PF','C','UTIL','UTIL'], scoring_settings: {} }],
  mlb: [{ league_id: 'demo-mlb', name: 'Diamond Goblins', sport: 'mlb', season: '2025', status: 'in_season', total_rosters: 12, roster_positions: ['C','1B','2B','SS','3B','OF','OF','OF','SP','RP'], scoring_settings: {} }],
  nhl: [{ league_id: 'demo-nhl', name: 'Ice Goblin League', sport: 'nhl', season: '2025', status: 'in_season', total_rosters: 10, roster_positions: ['C','LW','RW','D','D','G'], scoring_settings: {} }],
};

const DEMO_ROSTERS: Record<string, RosterPlayer[]> = {
  nfl: [
    { player_id: 'd1', full_name: 'Josh Allen', team: 'BUF', position: 'QB', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'd2', full_name: 'Saquon Barkley', team: 'PHI', position: 'RB', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'd3', full_name: 'Bijan Robinson', team: 'ATL', position: 'RB', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'd4', full_name: "Ja'Marr Chase", team: 'CIN', position: 'WR', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'd5', full_name: 'CeeDee Lamb', team: 'DAL', position: 'WR', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'd6', full_name: 'Travis Kelce', team: 'KC', position: 'TE', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'd7', full_name: 'Puka Nacua', team: 'LAR', position: 'WR', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'd8', full_name: 'Lamar Jackson', team: 'BAL', position: 'QB', status: 'Active', is_starter: false, injury_status: null },
    { player_id: 'd9', full_name: 'Breece Hall', team: 'NYJ', position: 'RB', status: 'Active', is_starter: false, injury_status: 'Questionable' },
    { player_id: 'd10', full_name: 'Jaylen Waddle', team: 'MIA', position: 'WR', status: 'Active', is_starter: false, injury_status: null },
    { player_id: 'd11', full_name: 'Dallas Goedert', team: 'PHI', position: 'TE', status: 'Active', is_starter: false, injury_status: null },
  ],
  nba: [
    { player_id: 'dn1', full_name: 'Luka Doncic', team: 'DAL', position: 'PG', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dn2', full_name: 'Anthony Edwards', team: 'MIN', position: 'SG', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dn3', full_name: 'Jayson Tatum', team: 'BOS', position: 'SF', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dn4', full_name: 'Giannis Antetokounmpo', team: 'MIL', position: 'PF', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dn5', full_name: 'Nikola Jokic', team: 'DEN', position: 'C', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dn6', full_name: 'Tyrese Haliburton', team: 'IND', position: 'PG', status: 'Active', is_starter: false, injury_status: null },
    { player_id: 'dn7', full_name: 'Paolo Banchero', team: 'ORL', position: 'PF', status: 'Active', is_starter: false, injury_status: 'GTD' },
  ],
  mlb: [
    { player_id: 'dm1', full_name: 'Shohei Ohtani', team: 'LAD', position: 'DH', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dm2', full_name: 'Aaron Judge', team: 'NYY', position: 'OF', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dm3', full_name: 'Ronald Acuna Jr.', team: 'ATL', position: 'OF', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dm4', full_name: 'Freddie Freeman', team: 'LAD', position: '1B', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dm5', full_name: 'Corbin Burnes', team: 'BAL', position: 'SP', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dm6', full_name: 'Elly De La Cruz', team: 'CIN', position: 'SS', status: 'Active', is_starter: false, injury_status: null },
  ],
  nhl: [
    { player_id: 'dh1', full_name: 'Connor McDavid', team: 'EDM', position: 'C', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dh2', full_name: 'Nathan MacKinnon', team: 'COL', position: 'C', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dh3', full_name: 'Cale Makar', team: 'COL', position: 'D', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dh4', full_name: 'Auston Matthews', team: 'TOR', position: 'C', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dh5', full_name: 'Igor Shesterkin', team: 'NYR', position: 'G', status: 'Active', is_starter: true, injury_status: null },
    { player_id: 'dh6', full_name: 'David Pastrnak', team: 'BOS', position: 'RW', status: 'Active', is_starter: false, injury_status: null },
  ],
};

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
  connectDemo: (sport: Sport) => void;
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

      connectDemo: (sport: Sport) => {
        const demoLeagues = DEMO_LEAGUES[sport] || DEMO_LEAGUES.nfl;
        const demoRoster = DEMO_ROSTERS[sport] || DEMO_ROSTERS.nfl;
        const league = demoLeagues[0];

        set((state) => ({
          connection: {
            sleeperUserId: 'demo',
            sleeperUsername: 'demo',
            displayName: 'Demo User',
            avatar: null,
          },
          leaguesBySport: {
            ...state.leaguesBySport,
            nfl: DEMO_LEAGUES.nfl,
            nba: DEMO_LEAGUES.nba,
            mlb: DEMO_LEAGUES.mlb,
            nhl: DEMO_LEAGUES.nhl,
          },
          selectedLeagueIds: {
            ...state.selectedLeagueIds,
            [sport]: league.league_id,
          },
          roster: demoRoster,
          error: null,
        }));
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

        // Demo mode — use local data
        if (connection.sleeperUserId === 'demo') {
          set({ roster: DEMO_ROSTERS[sport] || [] });
          return;
        }

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
        if (connection?.sleeperUserId === 'demo') return;
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

        // Demo mode — load demo roster directly
        if (connection.sleeperUserId === 'demo') {
          const demoLeague = DEMO_LEAGUES[sport]?.[0];
          if (demoLeague) {
            set((state) => ({
              selectedLeagueIds: { ...state.selectedLeagueIds, [sport]: demoLeague.league_id },
              roster: DEMO_ROSTERS[sport] || [],
            }));
          }
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
