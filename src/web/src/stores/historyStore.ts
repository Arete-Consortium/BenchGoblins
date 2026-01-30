import { create } from 'zustand';
import type { DecisionHistoryItem, Sport } from '@/types';
import api from '@/lib/api';

interface HistoryState {
  // History data
  items: DecisionHistoryItem[];
  isLoading: boolean;
  hasMore: boolean;
  filter: Sport | null;

  // Actions
  fetchHistory: (reset?: boolean) => Promise<void>;
  setFilter: (sport: Sport | null) => void;
  clearHistory: () => void;
}

const PAGE_SIZE = 20;

export const useHistoryStore = create<HistoryState>((set, get) => ({
  items: [],
  isLoading: false,
  hasMore: true,
  filter: null,

  fetchHistory: async (reset = false) => {
    const { items, isLoading, filter } = get();
    if (isLoading) return;

    set({ isLoading: true });

    try {
      // Note: Current API doesn't support offset pagination
      // For now, just fetch all at once
      const limit = reset ? PAGE_SIZE : items.length + PAGE_SIZE;
      const history = await api.getHistory(limit, filter || undefined);

      set({
        items: history,
        hasMore: history.length === limit,
        isLoading: false,
      });
    } catch (error) {
      console.error('Failed to fetch history:', error);
      set({ isLoading: false });
    }
  },

  setFilter: (filter) => {
    set({ filter, items: [], hasMore: true });
    get().fetchHistory(true);
  },

  clearHistory: () => set({ items: [], hasMore: true }),
}));

export default useHistoryStore;
