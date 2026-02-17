import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Sport, RiskMode } from '@/types';
import type { Locale } from '@/i18n';

interface PreferencesState {
  // Display preferences
  theme: 'light' | 'dark' | 'system';
  language: Locale;

  // Default settings for decisions
  defaultSport: Sport;
  defaultRiskMode: RiskMode;

  // UI preferences
  showIndicesDetails: boolean;
  compactMode: boolean;

  // Actions
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  setLanguage: (language: Locale) => void;
  setDefaultSport: (sport: Sport) => void;
  setDefaultRiskMode: (riskMode: RiskMode) => void;
  setShowIndicesDetails: (show: boolean) => void;
  setCompactMode: (compact: boolean) => void;
  resetPreferences: () => void;
}

const defaultPreferences = {
  theme: 'dark' as const,
  language: 'en' as Locale,
  defaultSport: 'nba' as Sport,
  defaultRiskMode: 'median' as RiskMode,
  showIndicesDetails: true,
  compactMode: false,
};

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      ...defaultPreferences,

      setTheme: (theme) => set({ theme }),
      setLanguage: (language) => set({ language }),
      setDefaultSport: (defaultSport) => set({ defaultSport }),
      setDefaultRiskMode: (defaultRiskMode) => set({ defaultRiskMode }),
      setShowIndicesDetails: (showIndicesDetails) => set({ showIndicesDetails }),
      setCompactMode: (compactMode) => set({ compactMode }),

      resetPreferences: () => set(defaultPreferences),
    }),
    {
      name: 'benchgoblin-preferences',
    }
  )
);

export default usePreferencesStore;
