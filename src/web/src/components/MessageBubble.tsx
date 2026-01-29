'use client';

import { cn, formatRelativeTime, getConfidenceColor } from '@/lib/utils';
import { Message, DecisionResponse } from '@/types';
import { Bot, User, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface MessageBubbleProps {
  message: Message;
}

function IndexBar({ label, value, max = 100 }: { label: string; value: number; max?: number }) {
  const percentage = Math.min((value / max) * 100, 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-8 text-dark-400 uppercase">{label}</span>
      <div className="flex-1 h-1.5 bg-dark-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-primary-500 rounded-full transition-all"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="w-10 text-right text-dark-300">{value.toFixed(1)}</span>
    </div>
  );
}

function DecisionDetails({ decision }: { decision: DecisionResponse }) {
  if (!decision.details) return null;

  const { player_a, player_b, margin } = decision.details;
  const aWins = player_a.score > player_b.score;

  return (
    <div className="mt-4 p-4 bg-dark-800/50 rounded-lg border border-dark-700">
      <div className="flex items-center justify-between mb-4">
        <span className={cn('font-semibold', getConfidenceColor(decision.confidence))}>
          {decision.confidence.toUpperCase()} CONFIDENCE
        </span>
        <span className="text-xs text-dark-400">
          via {decision.source === 'local' ? 'Local Engine' : 'Claude AI'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Player A */}
        <div className={cn('p-3 rounded-lg', aWins ? 'bg-green-500/10 border border-green-500/30' : 'bg-dark-700/50')}>
          <div className="flex items-center gap-2 mb-2">
            {aWins ? (
              <TrendingUp className="w-4 h-4 text-green-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-dark-400" />
            )}
            <span className="font-semibold text-sm">{player_a.name}</span>
          </div>
          <div className="text-2xl font-bold text-primary-400 mb-3">
            {player_a.score.toFixed(1)}
          </div>
          <div className="space-y-1.5">
            <IndexBar label="SCI" value={player_a.indices.sci} />
            <IndexBar label="RMI" value={player_a.indices.rmi} />
            <IndexBar label="GIS" value={player_a.indices.gis} />
            <IndexBar label="OD" value={player_a.indices.od} max={50} />
            <IndexBar label="MSF" value={player_a.indices.msf} />
          </div>
        </div>

        {/* Player B */}
        <div className={cn('p-3 rounded-lg', !aWins ? 'bg-green-500/10 border border-green-500/30' : 'bg-dark-700/50')}>
          <div className="flex items-center gap-2 mb-2">
            {!aWins ? (
              <TrendingUp className="w-4 h-4 text-green-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-dark-400" />
            )}
            <span className="font-semibold text-sm">{player_b.name}</span>
          </div>
          <div className="text-2xl font-bold text-primary-400 mb-3">
            {player_b.score.toFixed(1)}
          </div>
          <div className="space-y-1.5">
            <IndexBar label="SCI" value={player_b.indices.sci} />
            <IndexBar label="RMI" value={player_b.indices.rmi} />
            <IndexBar label="GIS" value={player_b.indices.gis} />
            <IndexBar label="OD" value={player_b.indices.od} max={50} />
            <IndexBar label="MSF" value={player_b.indices.msf} />
          </div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-dark-700 flex items-center justify-center gap-2 text-sm">
        <Minus className="w-4 h-4 text-dark-400" />
        <span className="text-dark-300">
          Margin: <span className="font-semibold text-primary-400">{margin.toFixed(1)} pts</span>
        </span>
      </div>
    </div>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-500/20 flex items-center justify-center">
          <Bot className="w-5 h-5 text-primary-400" />
        </div>
      )}

      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-3',
          isUser
            ? 'bg-primary-600 text-white rounded-br-md'
            : 'bg-dark-800 text-dark-100 rounded-bl-md'
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>

        {message.decision && <DecisionDetails decision={message.decision} />}

        <div
          className={cn(
            'text-xs mt-2',
            isUser ? 'text-primary-200' : 'text-dark-400'
          )}
        >
          {formatRelativeTime(message.timestamp)}
        </div>
      </div>

      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-dark-700 flex items-center justify-center">
          <User className="w-5 h-5 text-dark-300" />
        </div>
      )}
    </div>
  );
}

export default MessageBubble;
