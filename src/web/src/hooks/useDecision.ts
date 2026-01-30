'use client';

import { useState, useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import type { DecisionRequest, DecisionResponse, DecisionHistoryItem, Sport } from '@/types';

/**
 * Hook for making decisions with streaming support
 */
export function useDecision() {
  const queryClient = useQueryClient();
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  const mutation = useMutation({
    mutationFn: async (request: DecisionRequest) => {
      return api.decide(request);
    },
    onSuccess: () => {
      // Invalidate history on new decision
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });

  const decideWithStream = useCallback(
    async (
      request: DecisionRequest,
      onComplete?: (response: DecisionResponse) => void
    ) => {
      setStreamingContent('');
      setIsStreaming(true);

      try {
        await api.decideStream(
          request,
          (chunk) => setStreamingContent((prev) => prev + chunk),
          (response) => {
            setIsStreaming(false);
            queryClient.invalidateQueries({ queryKey: ['history'] });
            onComplete?.(response);
          }
        );
      } catch (error) {
        setIsStreaming(false);
        throw error;
      }
    },
    [queryClient]
  );

  return {
    decide: mutation.mutate,
    decideAsync: mutation.mutateAsync,
    decideWithStream,
    streamingContent,
    isStreaming,
    isLoading: mutation.isPending || isStreaming,
    error: mutation.error,
    data: mutation.data,
  };
}

/**
 * Hook for fetching decision history
 */
export function useHistory(sport?: Sport, limit = 20) {
  return useQuery({
    queryKey: ['history', sport, limit],
    queryFn: () => api.getHistory(limit, sport),
  });
}

/**
 * Hook for health check
 */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.getHealth(),
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}

/**
 * Hook for usage stats
 */
export function useUsage() {
  return useQuery({
    queryKey: ['usage'],
    queryFn: () => api.getUsage(),
    refetchInterval: 60000, // Refetch every minute
  });
}
