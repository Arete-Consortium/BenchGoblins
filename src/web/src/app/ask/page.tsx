'use client';

import { Suspense, useState, useEffect, useRef, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAppStore } from '@/stores/appStore';
import { useLeagueStore } from '@/stores/leagueStore';
import { Header, UsageIndicator } from '@/components/layout/Header';
import { useAuthStore } from '@/stores/authStore';
import { SportSelector } from '@/components/SportSelector';
import { RiskModeSelector } from '@/components/RiskModeSelector';
import { LeagueChip } from '@/components/LeagueChip';
import { LeagueConnectDialog } from '@/components/LeagueConnectDialog';
import { MessageBubble } from '@/components/MessageBubble';
import { ChatInput } from '@/components/ChatInput';
import { Sparkles, TrendingUp, Shield, Target, Link2 } from 'lucide-react';
import type { Sport } from '@/types';

// 100 questions (20 per sport) — WelcomeScreen picks 4 at random each render
const SPORT_EXAMPLES: Record<Sport, string[]> = {
  nba: [
    'Should I start Jayson Tatum or Anthony Edwards this week?',
    'Trade Trae Young for Tyrese Haliburton — who wins?',
    "Is De'Aaron Fox a good waiver pickup?",
    "Explain Luka Doncic's scoring volatility this season",
    'Who are the top 5 point guards for fantasy right now?',
    'Start LaMelo Ball or Jalen Brunson in a points league?',
    'Is Chet Holmgren worth a roster spot in 10-team leagues?',
    'Trade Nikola Jokic for Shai Gilgeous-Alexander — fair?',
    'Best streaming centers for this week?',
    'Should I sit Kawhi Leonard with his load management?',
    'Who has more upside ROS — Scottie Barnes or Paolo Banchero?',
    'Top 5 fantasy shooting guards this season?',
    'Is Victor Wembanyama living up to the hype in fantasy?',
    'Start Donovan Mitchell or Devin Booker tonight?',
    'Best waiver wire pickups in 12-team leagues?',
    'Trade Bam Adebayo for Domantas Sabonis — which side?',
    'Who should I start at UTIL — Zion or KAT?',
    'Rank these three: Haliburton, Brunson, Edwards',
    'Is it time to sell high on Tyrese Maxey?',
    'Best punt-assists build strategy this week?',
  ],
  nfl: [
    'Start Josh Allen or Lamar Jackson this week?',
    'Trade Tyreek Hill for Justin Jefferson — fair deal?',
    'Is Bijan Robinson a must-start in ceiling mode?',
    "Who's the best waiver QB for Week 12?",
    'Top 5 tight ends for fantasy this season?',
    'Start Ja\'Marr Chase or CeeDee Lamb in PPR?',
    'Is Breece Hall a buy-low candidate right now?',
    'Best defense to stream this week?',
    'Trade Travis Kelce for a WR1 — worth it?',
    'Should I flex Jaylen Waddle or DeVonta Smith?',
    'Who are the top 5 running backs ROS?',
    'Start Jalen Hurts or Patrick Mahomes this week?',
    'Best rookie wide receivers to stash?',
    'Is it safe to start two players from the same team?',
    'Trade Davante Adams for Amon-Ra St. Brown — who wins?',
    'Best waiver wire running backs available?',
    'Should I drop my backup QB to grab a handcuff RB?',
    'Rank these flex plays: Diontae Johnson, Keenan Allen, Raheem Mostert',
    'Start or sit Derrick Henry against the top rush defense?',
    'Who are the best DFS value plays this week?',
  ],
  mlb: [
    'Start Shohei Ohtani or Aaron Judge tonight?',
    'Trade Corbin Burnes for Trea Turner — who wins?',
    'Best waiver wire pitchers for this week?',
    'Should I bench Mookie Betts against a lefty starter?',
    'Top 5 starting pitchers for fantasy this season?',
    'Is Elly De La Cruz a must-start every day?',
    'Best closers to pick up for saves?',
    'Start Freddie Freeman or Vladimir Guerrero Jr. tonight?',
    'Trade Ronald Acuna Jr. for two mid-tier hitters — worth it?',
    'Who are the best two-start pitchers this week?',
    'Should I stream pitchers or hold my aces?',
    'Is Gunnar Henderson the top fantasy shortstop?',
    'Best outfield waiver pickups right now?',
    'Start Yordan Alvarez or Kyle Tucker this week?',
    'Rank these closers: Clase, Diaz, Hader',
    'Who has more stolen base upside — Bobby Witt Jr. or Elly?',
    'Trade Spencer Strider for a top-20 bat — fair?',
    'Best catcher options on the waiver wire?',
    'Should I start a pitcher at Coors Field?',
    'Top 5 fantasy second basemen this season?',
  ],
  nhl: [
    'Start Connor McDavid or Nathan MacKinnon this week?',
    'Trade Auston Matthews for Cale Makar — fair?',
    'Best waiver wire goalies for the week?',
    'Should I start Ovechkin on a back-to-back?',
    'Top 5 fantasy defensemen this season?',
    'Is Connor Bedard worth a top-5 pick in redraft?',
    'Start Igor Shesterkin or Andrei Vasilevskiy tonight?',
    'Best power play specialists to stream?',
    'Trade Nikita Kucherov for David Pastrnak — who wins?',
    'Should I roster two goalies or three?',
    'Who are the top waiver pickups this week?',
    'Start Leon Draisaitl or Mikko Rantanen tonight?',
    'Is it worth streaming defensemen for hits and blocks?',
    'Trade Matthew Tkachuk for Sebastian Aho — fair?',
    'Best goalies for the playoff schedule?',
    'Rank these wingers: Kaprizov, Marchand, Huberdeau',
    'Should I start a goalie against a top-5 offense?',
    'Who has the best remaining schedule for fantasy?',
    'Top 5 fantasy centers right now?',
    'Best players to target in a dynasty trade?',
  ],
  soccer: [
    'Should I start Haaland or Salah in my FPL squad this gameweek?',
    'Captain Mbappé or Bellingham this week?',
    'Best budget midfielders to pick up on FPL waivers?',
    'Is Palmer a good differential captain option?',
    'Top 5 FPL defenders for clean sheet potential?',
    'Should I take a hit to bring in Son for this gameweek?',
    'Best time to use my wildcard chip?',
    'Is Saka nailed for 90 minutes every week?',
    'Start Watkins or Isak as my lone striker?',
    'Who are the best set piece takers in FPL?',
    'Trade out Rashford — who should I bring in?',
    'Is it worth doubling up on Arsenal defense?',
    'Best cheap enablers under 5.0m?',
    'Should I bench boost or triple captain this gameweek?',
    'Top 5 midfield picks for the next 5 gameweeks?',
    'Is Alisson the best goalkeeper to own long-term?',
    'Rate my wildcard draft — 3-5-2 or 3-4-3?',
    'Best FPL differentials owned by under 5%?',
    'Should I start Foden despite the rotation risk?',
    'Who are the top transfer targets this gameweek?',
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
  const examples = useMemo(() => {
    const all = SPORT_EXAMPLES[sport];
    const shuffled = [...all].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, 4);
  }, [sport]);

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

function AskPageInner() {
  const { messages, isLoading, streamingContent, sport, riskMode, setSport, setRiskMode, sendMessage, clearMessages } =
    useAppStore();
  const leagueConnection = useLeagueStore((s) => s.connection);
  const onSportChange = useLeagueStore((s) => s.onSportChange);
  const { user, isAuthenticated } = useAuthStore();

  const [leagueDialogOpen, setLeagueDialogOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const searchParams = useSearchParams();
  const initialQuerySent = useRef(false);

  // Auto-send question from ?q= query param (e.g. from leaderboard suggestions)
  useEffect(() => {
    if (initialQuerySent.current) return;
    const q = searchParams.get('q');
    if (q && !isLoading && messages.length === 0) {
      initialQuerySent.current = true;
      sendMessage(q);
    }
  }, [searchParams, isLoading, messages.length, sendMessage]);

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
        {/* Top toolbar: Sport selector */}
        <div className="border-b border-dark-800/50 bg-dark-900/80 backdrop-blur-sm sticky top-16 z-10">
          <div className="max-w-4xl mx-auto px-4 py-2 flex items-center justify-between gap-3">
            <SportSelector value={sport} onChange={handleSportChange} disabled={isLoading} />
            <div className="flex items-center gap-3">
              <LeagueChip onOpen={() => setLeagueDialogOpen(true)} />
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

          {/* Bottom toolbar + input */}
          <div className="border-t border-dark-800/50 bg-dark-900/80 backdrop-blur-sm">
            <div className="max-w-4xl mx-auto px-4 py-2 flex items-center justify-between gap-3">
              <RiskModeSelector value={riskMode} onChange={setRiskMode} disabled={isLoading} compact />
              <Link
                href="/verdict"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary-600/20 border border-primary-500/30 text-primary-400 hover:bg-primary-600/30 hover:text-primary-300 transition-all text-sm font-medium"
              >
                <Sparkles className="w-4 h-4" />
                Verdict
              </Link>
              {isAuthenticated && user && (
                <UsageIndicator queriesUsed={user.queries_today} queriesLimit={user.queries_limit} />
              )}
            </div>
            <div className="px-4 pb-4">
              <ChatInput onSend={sendMessage} disabled={isLoading} />
            </div>
          </div>
        </div>
      </main>

      <LeagueConnectDialog open={leagueDialogOpen} onOpenChange={setLeagueDialogOpen} />
    </div>
  );
}

export default function AskPage() {
  return (
    <Suspense>
      <AskPageInner />
    </Suspense>
  );
}
