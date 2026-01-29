import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Message, Sport, RiskMode, DecisionResponse } from '@/types';
import { generateId } from '@/lib/utils';
import api from '@/lib/api';

interface AppState {
  // Current settings
  sport: Sport;
  riskMode: RiskMode;

  // Chat state
  messages: Message[];
  isLoading: boolean;
  streamingContent: string;

  // Actions
  setSport: (sport: Sport) => void;
  setRiskMode: (mode: RiskMode) => void;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Initial state
      sport: 'nba',
      riskMode: 'median',
      messages: [],
      isLoading: false,
      streamingContent: '',

      // Actions
      setSport: (sport) => set({ sport }),
      setRiskMode: (riskMode) => set({ riskMode }),

      sendMessage: async (content) => {
        const { sport, riskMode, messages } = get();

        // Add user message
        const userMessage: Message = {
          id: generateId(),
          role: 'user',
          content,
          timestamp: new Date(),
        };

        set({
          messages: [...messages, userMessage],
          isLoading: true,
          streamingContent: '',
        });

        try {
          // Determine decision type from query
          let decisionType: 'start_sit' | 'trade' | 'waiver' | 'explain' = 'start_sit';
          const lowerContent = content.toLowerCase();
          if (lowerContent.includes('trade')) {
            decisionType = 'trade';
          } else if (lowerContent.includes('waiver') || lowerContent.includes('pickup') || lowerContent.includes('pick up')) {
            decisionType = 'waiver';
          } else if (lowerContent.includes('explain') || lowerContent.includes('why') || lowerContent.includes('how')) {
            decisionType = 'explain';
          }

          // Make API request
          const response = await api.decide({
            sport,
            risk_mode: riskMode,
            decision_type: decisionType,
            query: content,
          });

          // Add assistant message
          const assistantMessage: Message = {
            id: generateId(),
            role: 'assistant',
            content: response.rationale,
            timestamp: new Date(),
            decision: response,
          };

          set((state) => ({
            messages: [...state.messages, assistantMessage],
            isLoading: false,
          }));
        } catch (error) {
          // Add error message
          const errorMessage: Message = {
            id: generateId(),
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
    }),
    {
      name: 'gamespace-app',
      partialize: (state) => ({
        sport: state.sport,
        riskMode: state.riskMode,
        // Don't persist messages
      }),
    }
  )
);

export default useAppStore;
