'use client';

import { useEffect, useRef, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { SportSelector } from '@/components/SportSelector';
import { RiskModeSelector } from '@/components/RiskModeSelector';
import { MessageBubble } from '@/components/MessageBubble';
import { ChatInput } from '@/components/ChatInput';
import { StreamingMessage } from './StreamingMessage';
import useAuthStore from '@/stores/authStore';
import api from '@/lib/api';
import { generateId } from '@/lib/utils';
import type { Message, DecisionResponse } from '@/types';

interface ChatInterfaceProps {
  useStreaming?: boolean;
}

export function ChatInterface({ useStreaming = true }: ChatInterfaceProps) {
  const { messages, isLoading, sport, riskMode, setSport, setRiskMode, sendMessage } =
    useAppStore();

  const [streamingContent, setStreamingContent] = useState('');
  const [isStreamingActive, setIsStreamingActive] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or streaming content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSendMessage = async (content: string) => {
    if (!useStreaming) {
      // Use non-streaming endpoint via store
      await sendMessage(content);
      return;
    }

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: new Date(),
    };

    // Update store with user message
    useAppStore.setState((state) => ({
      messages: [...state.messages, userMessage],
      isLoading: true,
    }));

    setStreamingContent('');
    setIsStreamingActive(true);

    try {
      // Determine decision type from query
      let decisionType: 'start_sit' | 'trade' | 'waiver' | 'explain' = 'start_sit';
      const lowerContent = content.toLowerCase();
      if (lowerContent.includes('trade')) {
        decisionType = 'trade';
      } else if (
        lowerContent.includes('waiver') ||
        lowerContent.includes('pickup') ||
        lowerContent.includes('pick up')
      ) {
        decisionType = 'waiver';
      } else if (
        lowerContent.includes('explain') ||
        lowerContent.includes('why') ||
        lowerContent.includes('how')
      ) {
        decisionType = 'explain';
      }

      let fullContent = '';
      let finalResponse: DecisionResponse | undefined;

      await api.decideStream(
        {
          sport,
          risk_mode: riskMode,
          decision_type: decisionType,
          query: content,
        },
        (chunk) => {
          fullContent += chunk;
          setStreamingContent(fullContent);
        },
        (response) => {
          finalResponse = response;
        }
      );

      // Add assistant message with final content
      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: fullContent || finalResponse?.rationale || '',
        timestamp: new Date(),
        decision: finalResponse,
      };

      useAppStore.setState((state) => ({
        messages: [...state.messages, assistantMessage],
        isLoading: false,
      }));
      // Refresh user data to update query counter in header
      useAuthStore.getState().refreshUser();
    } catch (error) {
      console.error('Streaming error:', error);

      const errMsg = error instanceof Error ? error.message : 'Unknown error';
      const isQuotaExceeded = errMsg.includes('query limit') || errMsg.includes('QUOTA_EXCEEDED');

      const errorMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: isQuotaExceeded
          ? 'You\'ve reached your weekly question limit (5 questions). Upgrade to Pro for unlimited questions!'
          : 'Sorry, I encountered an error processing your request. Please try again.',
        timestamp: new Date(),
      };

      useAppStore.setState((state) => ({
        messages: [...state.messages, errorMessage],
        isLoading: false,
      }));

      // Refresh user data on quota errors too
      useAuthStore.getState().refreshUser();
    } finally {
      setIsStreamingActive(false);
      setStreamingContent('');
    }
  };

  return (
    <div className="flex-1 flex flex-col">
      {/* Controls bar */}
      <div className="border-b border-dark-800 bg-dark-900/50">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <SportSelector
              value={sport}
              onChange={setSport}
              disabled={isLoading || isStreamingActive}
            />
            <RiskModeSelector
              value={riskMode}
              onChange={setRiskMode}
              disabled={isLoading || isStreamingActive}
              compact
            />
          </div>
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {/* Streaming message */}
          {isStreamingActive && streamingContent && (
            <StreamingMessage content={streamingContent} isStreaming={true} />
          )}

          {/* Loading indicator (non-streaming) */}
          {isLoading && !isStreamingActive && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-primary-500/20 flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-primary-400 animate-pulse" />
              </div>
              <div className="bg-dark-800 rounded-2xl rounded-bl-md px-4 py-3">
                <div className="flex gap-1">
                  <div className="w-2 h-2 rounded-full bg-dark-500 animate-bounce" />
                  <div
                    className="w-2 h-2 rounded-full bg-dark-500 animate-bounce"
                    style={{ animationDelay: '0.1s' }}
                  />
                  <div
                    className="w-2 h-2 rounded-full bg-dark-500 animate-bounce"
                    style={{ animationDelay: '0.2s' }}
                  />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-dark-800 p-4 bg-dark-900/50">
          <ChatInput onSend={handleSendMessage} disabled={isLoading || isStreamingActive} />
        </div>
      </div>
    </div>
  );
}
