import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Message, Sport, RiskMode, DecisionResponse } from '@/types';
import { generateId } from '@/lib/utils';
import api from '@/lib/api';
import { useLeagueStore } from '@/stores/leagueStore';

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
          const lowerContent = content.toLowerCase();
          const isDraft = lowerContent.includes('draft') ||
            lowerContent.includes('pick from') ||
            lowerContent.includes('choose from') ||
            lowerContent.includes('rank these');

          const isWaiver = lowerContent.includes('waiver') ||
            lowerContent.includes('pickup') ||
            lowerContent.includes('pick up') ||
            lowerContent.includes('who should i add') ||
            lowerContent.includes('free agent');

          // Check if league is connected for waiver routing
          const leagueState = useLeagueStore.getState();
          const activeLeagueId = leagueState.selectedLeagueIds[sport];
          const sleeperUserId = leagueState.connection?.sleeperUserId;

          let assistantMessage: Message;

          if (isDraft) {
            // Draft uses dedicated /draft endpoint (non-streaming)
            const draftResponse = await api.draft({
              sport,
              risk_mode: riskMode,
              query: content,
            });

            assistantMessage = {
              id: assistantMessageId,
              role: 'assistant',
              content: draftResponse.rationale,
              timestamp: new Date(),
              decision: {
                decision: draftResponse.recommended_pick,
                confidence: draftResponse.confidence,
                rationale: draftResponse.rationale,
                source: draftResponse.source,
                details: draftResponse.details || undefined,
              },
            };
          } else if (isWaiver && activeLeagueId && sleeperUserId) {
            // Waiver uses dedicated /waiver/recommend endpoint when league connected
            const waiverResponse = await api.waiverRecommend({
              sport,
              risk_mode: riskMode,
              query: content,
              league_id: activeLeagueId,
              sleeper_user_id: sleeperUserId,
            });

            assistantMessage = {
              id: assistantMessageId,
              role: 'assistant',
              content: waiverResponse.rationale,
              timestamp: new Date(),
              decision: {
                decision: waiverResponse.recommendations[0]?.name
                  ? `Add ${waiverResponse.recommendations[0].name}`
                  : 'No urgent pickups needed',
                confidence: waiverResponse.confidence,
                rationale: waiverResponse.rationale,
                source: waiverResponse.source,
                details: {
                  recommendations: waiverResponse.recommendations,
                  drop_candidates: waiverResponse.drop_candidates,
                  position_needs: waiverResponse.position_needs,
                },
              },
            };
          } else {
            let decisionType: 'start_sit' | 'trade' | 'waiver' | 'explain' = 'start_sit';
            if (lowerContent.includes('trade')) {
              decisionType = 'trade';
            } else if (isWaiver) {
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
                ...(activeLeagueId ? { league_id: activeLeagueId, sleeper_user_id: sleeperUserId } : {}),
              },
              (chunk) => {
                fullContent += chunk;
              },
              (response) => {
                responseHolder.value = response;
              }
            );

            const finalResponse = responseHolder.value;
            assistantMessage = {
              id: assistantMessageId,
              role: 'assistant',
              content: finalResponse?.rationale || fullContent,
              timestamp: new Date(),
              decision: finalResponse || undefined,
            };
          }

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
