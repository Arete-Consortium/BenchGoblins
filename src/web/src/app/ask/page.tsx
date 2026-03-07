'use client';

import { useState, useEffect, useRef } from 'react';
import { useAppStore } from '@/stores/appStore';
import { useLeagueStore } from '@/stores/leagueStore';
import { Header } from '@/components/layout/Header';
import { SportSelector } from '@/components/SportSelector';
import { RiskModeSelector } from '@/components/RiskModeSelector';
import { LeagueChip } from '@/components/LeagueChip';
import { LeagueConnectDialog } from '@/components/LeagueConnectDialog';
import { MessageBubble } from '@/components/MessageBubble';
import { ChatInput } from '@/components/ChatInput';
import { Sparkles, TrendingUp, Shield, Target, Link2 } from 'lucide-react';
import type { Sport } from '@/types';

const SPORT_EXAMPLES: Record<Sport, string[]> = {
  nba: [
    'Should I start Jayson Tatum or Anthony Edwards this week?',
    'Trade Trae Young for Tyrese Haliburton — who wins?',
    "Is De'Aaron Fox a good waiver pickup?",
    "Explain Luka Doncic's scoring volatility this season",
  ],
  nfl: [
    'Start Josh Allen or Lamar Jackson this week?',
    'Trade Tyreek Hill for Justin Jefferson — fair deal?',
    'Is Bijan Robinson a must-start in ceiling mode?',
    "Who's the best waiver QB for Week 12?",
  ],
  mlb: [
    'Start Shohei Ohtani or Aaron Judge tonight?',
    'Trade Corbin Burnes for Trea Turner — who wins?',
    'Best waiver wire pitchers for this week?',
    "Should I bench Mookie Betts against a lefty starter?",
  ],
  nhl: [
    'Start Connor McDavid or Nathan MacKinnon this week?',
    'Trade Auston Matthews for Cale Makar — fair?',
    'Best waiver wire goalies for the week?',
    "Should I start Ovechkin on a back-to-back?",
  ],
  soccer: [
    'Should I start Haaland or Salah in my FPL squad this gameweek?',
    'Captain Mbappé or Bellingham this week?',
    'Best budget midfielders to pick up on FPL waivers?',
    'Is Palmer a good differential captain option?',
  ],
};

const SPORT_ICONS: Record<Sport, string> = {
  nba: '🏀',
  nfl: '🏈',
  mlb: '⚾',
  nhl: '🏒',
  soccer: '⚽',
};

const SPORT_NAMES: Record<Sport, string> = {
  nba: 'NBA',
  nfl: 'NFL',
  mlb: 'MLB',
  nhl: 'NHL',
  soccer: 'Soccer',
};

// Quick follow-up suggestions shown after each assistant response
const FOLLOW_UP_SUGGESTIONS: Record<Sport, string[]> = {
  nba: [
    'Compare their floor vs ceiling scores',
    'Who else should I start this week?',
    'Any good waiver pickups at that position?',
    'What about for a trade instead?',
  ],
  nfl: [
    'What about in PPR scoring?',
    'Who else should I start this week?',
    'Best waiver wire pickups right now?',
    'Compare their matchup profiles',
  ],
  mlb: [
    'How do they do against lefties?',
    'Who else should I start tonight?',
    'Any waiver wire pitchers to grab?',
    'Break down their recent stats',
  ],
  nhl: [
    'How about on a back-to-back?',
    'Who else should I start this week?',
    'Best waiver goalies available?',
    'Compare their playoff schedules',
  ],
  soccer: [
    'Who should I captain instead?',
    'Any good budget picks this gameweek?',
    'Compare their fixture difficulty',
    'Should I use my wildcard?',
  ],
};

function FollowUpChips({ sport, onSend, disabled }: { sport: Sport; onSend: (msg: string) => void; disabled: boolean }) {
  const suggestions = FOLLOW_UP_SUGGESTIONS[sport];
  return (
    <div className="flex flex-wrap gap-2 px-4 pb-2">
      {suggestions.map((suggestion) => (
        <button
          key={suggestion}
          onClick={() => onSend(suggestion)}
          disabled={disabled}
          className="px-3 py-1.5 rounded-full bg-dark-800 text-dark-400 text-sm
                     hover:bg-dark-700 hover:text-dark-200 transition-all
                     disabled:opacity-50 disabled:cursor-not-allowed
                     border border-dark-700/50 hover:border-dark-600"
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}

function WelcomeScreen({ sport, onConnectLeague }: { sport: Sport; onConnectLeague: () => void }) {
  const sendMessage = useAppStore((state) => state.sendMessage);
  const connection = useLeagueStore((s) => s.connection);
  const examples = SPORT_EXAMPLES[sport];

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <div className="w-20 h-20 rounded-2xl bg-primary-600/20 flex items-center justify-center mx-auto mb-6">
          <span className="text-4xl">{SPORT_ICONS[sport]}</span>
        </div>

        <h1 className="text-4xl font-bold mb-4">
          <span className="gradient-text">{SPORT_NAMES[sport]} Decisions,</span>
          <br />
          <span className="text-dark-100">Made Simple</span>
        </h1>

        <p className="text-dark-400 text-lg mb-8">
          Ask any start/sit, trade, or waiver question. Get instant recommendations powered by our
          five-index scoring system.
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
          <p className="text-sm text-dark-500">Try asking about {SPORT_NAMES[sport]}:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {examples.map((query) => (
              <button
                key={query}
                onClick={() => sendMessage(query)}
                className="px-4 py-2 rounded-full bg-dark-800 text-dark-300 text-sm
                         hover:bg-dark-700 hover:text-dark-100 transition-all"
              >
                {query}
              </button>
            ))}
          </div>
        </div>

        {/* League connect nudge */}
        {!connection && sport !== 'soccer' && (
          <button
            onClick={onConnectLeague}
            className="mt-6 inline-flex items-center gap-2 text-sm text-primary-400 hover:text-primary-300 transition-colors"
          >
            <Link2 className="h-4 w-4" />
            Connect your Sleeper league for personalized answers
          </button>
        )}
      </div>
    </div>
  );
}

export default function AskPage() {
  const { messages, isLoading, streamingContent, sport, riskMode, setSport, setRiskMode, sendMessage, clearMessages } =
    useAppStore();
  const leagueConnection = useLeagueStore((s) => s.connection);
  const onSportChange = useLeagueStore((s) => s.onSportChange);

  const [leagueDialogOpen, setLeagueDialogOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Coordinate sport changes with league store — reset conversation for new sport
  const handleSportChange = (newSport: Sport) => {
    if (newSport !== sport) {
      clearMessages();
    }
    setSport(newSport);
    if (leagueConnection) {
      onSportChange(newSport);
    }
  };

  // Auto-scroll to bottom on new messages or streaming content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950">
      <Header />

      <main className="flex-1 flex flex-col pt-16">
        {/* Controls bar */}
        <div className="border-b border-dark-800/50 bg-dark-900/80 backdrop-blur-sm sticky top-16 z-10">
          <div className="max-w-4xl mx-auto px-4 py-3">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <SportSelector value={sport} onChange={handleSportChange} disabled={isLoading} />
              <div className="flex items-center gap-3">
                <LeagueChip onOpen={() => setLeagueDialogOpen(true)} />
                <RiskModeSelector value={riskMode} onChange={setRiskMode} disabled={isLoading} compact />
                {messages.length > 0 && (
                  <button
                    onClick={clearMessages}
                    disabled={isLoading}
                    className="px-3 py-1.5 text-sm text-dark-400 hover:text-dark-200 hover:bg-dark-700 rounded-lg transition-all"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Chat area */}
        <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full">
          {messages.length === 0 ? (
            <WelcomeScreen sport={sport} onConnectLeague={() => setLeagueDialogOpen(true)} />
          ) : (
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}

              {/* Streaming response */}
              {isLoading && streamingContent && (
                <div className="flex gap-3 justify-start">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-500/20 flex items-center justify-center">
                    <Sparkles className="w-5 h-5 text-primary-400" />
                  </div>
                  <div className="max-w-[80%] rounded-2xl rounded-bl-md px-4 py-3 bg-dark-800 text-dark-100">
                    <p className="whitespace-pre-wrap">{streamingContent}</p>
                    <span className="inline-block w-2 h-4 bg-primary-400 animate-pulse ml-1" />
                  </div>
                </div>
              )}

              {/* Loading indicator (before streaming starts) */}
              {isLoading && !streamingContent && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary-500/20 flex items-center justify-center">
                    <Sparkles className="w-5 h-5 text-primary-400 animate-pulse" />
                  </div>
                  <div className="bg-dark-800 rounded-2xl rounded-bl-md px-4 py-3">
                    <div className="flex gap-1.5 items-center">
                      <div className="w-2 h-2 rounded-full bg-primary-400 animate-bounce" />
                      <div
                        className="w-2 h-2 rounded-full bg-primary-400 animate-bounce"
                        style={{ animationDelay: '0.15s' }}
                      />
                      <div
                        className="w-2 h-2 rounded-full bg-primary-400 animate-bounce"
                        style={{ animationDelay: '0.3s' }}
                      />
                      <span className="ml-2 text-sm text-dark-400">Analyzing...</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Follow-up suggestions after conversation */}
          {messages.length > 0 && !isLoading && (
            <FollowUpChips sport={sport} onSend={sendMessage} disabled={isLoading} />
          )}

          {/* Input area */}
          <div className="border-t border-dark-800/50 p-4 bg-dark-900/80 backdrop-blur-sm">
            <ChatInput onSend={sendMessage} disabled={isLoading} />
          </div>
        </div>
      </main>

      <LeagueConnectDialog open={leagueDialogOpen} onOpenChange={setLeagueDialogOpen} />
    </div>
  );
}
