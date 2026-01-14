import { create } from 'zustand';
import { Sport, RiskMode, Message, DecisionResponse } from '../types';
import { makeDecision } from '../services/api';

interface AppState {
  // Settings
  sport: Sport;
  riskMode: RiskMode;
  setSport: (sport: Sport) => void;
  setRiskMode: (mode: RiskMode) => void;

  // Chat
  messages: Message[];
  isLoading: boolean;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Default settings
  sport: 'nba',
  riskMode: 'median',

  setSport: (sport) => set({ sport }),
  setRiskMode: (riskMode) => set({ riskMode }),

  // Chat state
  messages: [],
  isLoading: false,

  sendMessage: async (content: string) => {
    const { sport, riskMode, messages } = get();

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    };

    set({ messages: [...messages, userMessage], isLoading: true });

    try {
      const response = await makeDecision({
        sport,
        risk_mode: riskMode,
        decision_type: 'start_sit',
        query: content,
      });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `**${response.decision}** — ${response.confidence} confidence\n\n${response.rationale}`,
        timestamp: new Date(),
        decision: response,
      };

      set((state) => ({
        messages: [...state.messages, assistantMessage],
        isLoading: false,
      }));
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
        timestamp: new Date(),
      };

      set((state) => ({
        messages: [...state.messages, errorMessage],
        isLoading: false,
      }));
    }
  },

  clearMessages: () => set({ messages: [] }),
}));
