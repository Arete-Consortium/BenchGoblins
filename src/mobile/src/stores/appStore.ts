import { create } from 'zustand';
import { Sport, RiskMode, Message, DecisionResponse } from '../types';
import { makeDecision, ApiError } from '../services/api';
import { hapticSuccess, hapticError, hapticSelection } from '../utils/haptics';

interface AppState {
  // Settings
  sport: Sport;
  riskMode: RiskMode;
  setSport: (sport: Sport) => void;
  setRiskMode: (mode: RiskMode) => void;

  // Chat
  messages: Message[];
  isLoading: boolean;
  lastError: ApiError | null;
  sendMessage: (content: string) => Promise<void>;
  retryLastMessage: () => Promise<void>;
  clearMessages: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Default settings
  sport: 'nba',
  riskMode: 'median',

  setSport: (sport) => {
    hapticSelection();
    set({ sport });
  },
  setRiskMode: (riskMode) => {
    hapticSelection();
    set({ riskMode });
  },

  // Chat state
  messages: [],
  isLoading: false,
  lastError: null,

  sendMessage: async (content: string) => {
    const { sport, riskMode, messages } = get();

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    };

    set({ messages: [...messages, userMessage], isLoading: true, lastError: null });

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

      hapticSuccess();
      set((state) => ({
        messages: [...state.messages, assistantMessage],
        isLoading: false,
        lastError: null,
      }));
    } catch (error) {
      hapticError();

      const apiError = error instanceof ApiError ? error : null;
      const errorText = apiError
        ? apiError.message
        : 'Sorry, something went wrong. Please try again.';

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: errorText,
        timestamp: new Date(),
        isError: true,
      };

      set((state) => ({
        messages: [...state.messages, errorMessage],
        isLoading: false,
        lastError: apiError,
      }));
    }
  },

  retryLastMessage: async () => {
    const { messages, sendMessage } = get();
    // Find the last user message
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
    if (!lastUserMsg) return;

    // Remove the error message (last assistant message)
    const lastAssistantIdx = messages.length - 1;
    if (messages[lastAssistantIdx]?.isError) {
      set({ messages: messages.slice(0, -1) });
    }

    // Remove the user message too — sendMessage will re-add it
    set((state) => ({
      messages: state.messages.filter((m) => m.id !== lastUserMsg.id),
    }));

    await sendMessage(lastUserMsg.content);
  },

  clearMessages: () => set({ messages: [], lastError: null }),
}));
