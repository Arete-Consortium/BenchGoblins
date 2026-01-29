import { create } from 'zustand';
import { DecisionHistoryItem, Sport } from '@/types';
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
      const offset = reset ? 0 : items.length;
      const history = await api.getHistory(PAGE_SIZE, offset, filter || undefined);

      set({
        items: reset ? history : [...items, ...history],
        hasMore: history.length === PAGE_SIZE,
        isLoading: false,
      });
    } catch (error) {
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
