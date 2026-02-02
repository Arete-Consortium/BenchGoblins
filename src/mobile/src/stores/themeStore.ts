/**
 * Theme Store
 *
 * Manages app theme (dark/light mode) with persistence.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { Appearance } from 'react-native';

export type ThemeMode = 'dark' | 'light' | 'system';

export interface Theme {
  // Background colors
  background: string;
  backgroundSecondary: string;
  backgroundTertiary: string;

  // Text colors
  text: string;
  textSecondary: string;
  textTertiary: string;

  // Accent colors
  primary: string;
  primaryLight: string;
  success: string;
  warning: string;
  error: string;

  // Border colors
  border: string;
  borderLight: string;

  // Status bar
  statusBar: 'light-content' | 'dark-content';
}

const darkTheme: Theme = {
  background: '#0f0f1a',
  backgroundSecondary: '#1a1a2e',
  backgroundTertiary: '#2d2d44',

  text: '#ffffff',
  textSecondary: '#9ca3af',
  textTertiary: '#6b7280',

  primary: '#6366f1',
  primaryLight: '#818cf8',
  success: '#22c55e',
  warning: '#fbbf24',
  error: '#ef4444',

  border: '#1a1a2e',
  borderLight: '#2d2d44',

  statusBar: 'light-content',
};

const lightTheme: Theme = {
  background: '#f8fafc',
  backgroundSecondary: '#ffffff',
  backgroundTertiary: '#f1f5f9',

  text: '#0f172a',
  textSecondary: '#475569',
  textTertiary: '#94a3b8',

  primary: '#6366f1',
  primaryLight: '#818cf8',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',

  border: '#e2e8f0',
  borderLight: '#f1f5f9',

  statusBar: 'dark-content',
};

interface ThemeState {
  mode: ThemeMode;
  theme: Theme;
  isDark: boolean;

  setMode: (mode: ThemeMode) => void;
  toggleTheme: () => void;
}

function getThemeForMode(mode: ThemeMode): { theme: Theme; isDark: boolean } {
  if (mode === 'system') {
    const systemColorScheme = Appearance.getColorScheme();
    const isDark = systemColorScheme !== 'light';
    return { theme: isDark ? darkTheme : lightTheme, isDark };
  }

  const isDark = mode === 'dark';
  return { theme: isDark ? darkTheme : lightTheme, isDark };
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: 'dark' as ThemeMode,
      theme: darkTheme,
      isDark: true,

      setMode: (mode) => {
        const { theme, isDark } = getThemeForMode(mode);
        set({ mode, theme, isDark });
      },

      toggleTheme: () => {
        const { mode } = get();
        const newMode: ThemeMode = mode === 'dark' ? 'light' : 'dark';
        const { theme, isDark } = getThemeForMode(newMode);
        set({ mode: newMode, theme, isDark });
      },
    }),
    {
      name: 'benchgoblins-theme',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({ mode: state.mode }),
      onRehydrateStorage: () => (state) => {
        // Recompute theme after rehydration
        if (state) {
          const { theme, isDark } = getThemeForMode(state.mode);
          state.theme = theme;
          state.isDark = isDark;
        }
      },
    },
  ),
);

// Listen for system theme changes
Appearance.addChangeListener(({ colorScheme }) => {
  const state = useThemeStore.getState();
  if (state.mode === 'system') {
    const isDark = colorScheme !== 'light';
    useThemeStore.setState({
      theme: isDark ? darkTheme : lightTheme,
      isDark,
    });
  }
});

// Export themes for direct access if needed
export { darkTheme, lightTheme };
