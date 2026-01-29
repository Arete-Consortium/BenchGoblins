'use client';

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/stores/appStore';
import { Navigation } from '@/components/Navigation';
import { SportSelector } from '@/components/SportSelector';
import { RiskModeSelector } from '@/components/RiskModeSelector';
import { MessageBubble } from '@/components/MessageBubble';
import { ChatInput } from '@/components/ChatInput';
import { Sparkles, TrendingUp, Shield, Target } from 'lucide-react';

const EXAMPLE_QUERIES = [
  'Should I start Jayson Tatum or Anthony Edwards this week?',
  'Trade Tyreek Hill for Justin Jefferson?',
  'Is De\'Aaron Fox a good waiver pickup?',
  'Explain Luka Doncic\'s scoring volatility',
];

function WelcomeScreen() {
  const sendMessage = useAppStore((state) => state.sendMessage);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <div className="w-20 h-20 rounded-2xl bg-primary-600/20 flex items-center justify-center mx-auto mb-6">
          <Sparkles className="w-10 h-10 text-primary-400" />
        </div>

        <h1 className="text-4xl font-bold mb-4">
          <span className="gradient-text">Fantasy Decisions,</span>
          <br />
          <span className="text-dark-100">Made Simple</span>
        </h1>

        <p className="text-dark-400 text-lg mb-8">
          Ask any start/sit, trade, or waiver question. Get instant recommendations
          powered by our five-index scoring system.
        </p>

        {/* Index explainer */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="p-4 rounded-xl bg-dark-800/50 border border-dark-700">
            <Shield className="w-6 h-6 text-green-400 mx-auto mb-2" />
            <div className="font-semibold text-sm">Floor Mode</div>
            <div className="text-xs text-dark-400">Prioritize safety</div>
          </div>
          <div className="p-4 rounded-xl bg-dark-800/50 border border-dark-700">
            <Target className="w-6 h-6 text-blue-400 mx-auto mb-2" />
            <div className="font-semibold text-sm">Median Mode</div>
            <div className="text-xs text-dark-400">Balanced approach</div>
          </div>
          <div className="p-4 rounded-xl bg-dark-800/50 border border-dark-700">
            <TrendingUp className="w-6 h-6 text-orange-400 mx-auto mb-2" />
            <div className="font-semibold text-sm">Ceiling Mode</div>
            <div className="text-xs text-dark-400">Chase upside</div>
          </div>
        </div>

        {/* Example queries */}
        <div className="space-y-2">
          <p className="text-sm text-dark-500">Try asking:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {EXAMPLE_QUERIES.map((query, index) => (
              <button
                key={index}
                onClick={() => sendMessage(query)}
                className="px-4 py-2 rounded-full bg-dark-800 text-dark-300 text-sm
                         hover:bg-dark-700 hover:text-dark-100 transition-all"
              >
                {query}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { messages, isLoading, sport, riskMode, setSport, setRiskMode, sendMessage } =
    useAppStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="min-h-screen flex flex-col">
      <Navigation />

      <main className="flex-1 flex flex-col pt-16">
        {/* Controls bar */}
        <div className="border-b border-dark-800 bg-dark-900/50">
          <div className="max-w-4xl mx-auto px-4 py-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <SportSelector value={sport} onChange={setSport} disabled={isLoading} />
              <RiskModeSelector
                value={riskMode}
                onChange={setRiskMode}
                disabled={isLoading}
                compact
              />
            </div>
          </div>
        </div>

        {/* Chat area */}
        <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full">
          {messages.length === 0 ? (
            <WelcomeScreen />
          ) : (
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}

              {isLoading && (
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
          )}

          {/* Input area */}
          <div className="border-t border-dark-800 p-4 bg-dark-900/50">
            <ChatInput onSend={sendMessage} disabled={isLoading} />
          </div>
        </div>
      </main>
    </div>
  );
}
