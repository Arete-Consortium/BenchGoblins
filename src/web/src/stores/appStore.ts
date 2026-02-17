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
  streamingMessageId: string | null;

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
      streamingMessageId: null,

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

        // Create placeholder for streaming response
        const assistantMessageId = generateId();

        set({
          messages: [...messages, userMessage],
          isLoading: true,
          streamingContent: '',
          streamingMessageId: assistantMessageId,
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

          // Use streaming API for real-time response
          let fullContent = '';
          const responseHolder: { value: DecisionResponse | null } = { value: null };

          await api.decideStream(
            {
              sport,
              risk_mode: riskMode,
              decision_type: decisionType,
              query: content,
            },
            // Accumulate chunks silently (Claude returns JSON, not display text)
            (chunk) => {
              fullContent += chunk;
            },
            // On complete, get the parsed response
            (response) => {
              responseHolder.value = response;
            }
          );

          // Add completed assistant message
          const finalResponse = responseHolder.value;
          const assistantMessage: Message = {
            id: assistantMessageId,
            role: 'assistant',
            content: finalResponse?.rationale || fullContent,
            timestamp: new Date(),
            decision: finalResponse || undefined,
          };

          set((state) => ({
            messages: [...state.messages, assistantMessage],
            isLoading: false,
            streamingContent: '',
            streamingMessageId: null,
          }));
        } catch (error) {
          console.error('Decision error:', error);
          // Add error message
          const errorMessage: Message = {
            id: assistantMessageId,
            role: 'assistant',
            content: error instanceof Error && error.message.includes('sports')
              ? error.message
              : 'Sorry, I encountered an error processing your request. Please try again.',
            timestamp: new Date(),
          };

          set((state) => ({
            messages: [...state.messages, errorMessage],
            isLoading: false,
            streamingContent: '',
            streamingMessageId: null,
          }));
        }
      },

      clearMessages: () => set({ messages: [], streamingContent: '', streamingMessageId: null }),
    }),
    {
      name: 'benchgoblin-app',
      partialize: (state) => ({
        sport: state.sport,
        riskMode: state.riskMode,
        // Don't persist messages
      }),
    }
  )
);

export default useAppStore;
