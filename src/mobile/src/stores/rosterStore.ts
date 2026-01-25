import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Player, Sport } from '../types';

interface RosterState {
  // Roster by sport
  roster: Record<Sport, Player[]>;

  // Actions
  addPlayer: (sport: Sport, player: Player) => void;
  removePlayer: (sport: Sport, playerId: string) => void;
  clearRoster: (sport: Sport) => void;
  clearAllRosters: () => void;
}

const initialRoster: Record<Sport, Player[]> = {
  nba: [],
  nfl: [],
  mlb: [],
  nhl: [],
};

export const useRosterStore = create<RosterState>()(
  persist(
    (set) => ({
      roster: initialRoster,

      addPlayer: (sport, player) =>
        set((state) => {
          const currentRoster = state.roster[sport] || [];
          // Prevent duplicates
          if (currentRoster.some((p) => p.id === player.id)) {
            return state;
          }
          return {
            roster: {
              ...state.roster,
              [sport]: [...currentRoster, player],
            },
          };
        }),

      removePlayer: (sport, playerId) =>
        set((state) => ({
          roster: {
            ...state.roster,
            [sport]: (state.roster[sport] || []).filter((p) => p.id !== playerId),
          },
        })),

      clearRoster: (sport) =>
        set((state) => ({
          roster: {
            ...state.roster,
            [sport]: [],
          },
        })),

      clearAllRosters: () =>
        set({
          roster: initialRoster,
        }),
    }),
    {
      name: 'gamespace-roster',
      storage: createJSONStorage(() => AsyncStorage),
    }
  )
);
