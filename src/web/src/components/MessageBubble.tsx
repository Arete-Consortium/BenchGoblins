'use client';

import { cn, formatRelativeTime, getConfidenceColor } from '@/lib/utils';
import { Message, DecisionResponse, StartSitDetailsData, TradeDetailsData, DraftDetailsData, WaiverDetailsData } from '@/types';
import { Bot, User, TrendingUp, TrendingDown, Minus, ArrowRightLeft, Trophy, Zap, UserPlus, UserMinus, AlertCircle } from 'lucide-react';

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

function isTradeDetails(
  details: StartSitDetailsData | TradeDetailsData | DraftDetailsData | WaiverDetailsData
): details is TradeDetailsData {
  return 'side_giving' in details;
}

function isDraftDetails(
  details: StartSitDetailsData | TradeDetailsData | DraftDetailsData | WaiverDetailsData
): details is DraftDetailsData {
  return 'ranked_players' in details;
}

function isWaiverDetails(
  details: StartSitDetailsData | TradeDetailsData | DraftDetailsData | WaiverDetailsData
): details is WaiverDetailsData {
  return 'recommendations' in details && 'drop_candidates' in details;
}

function TradeDetails({ decision }: { decision: DecisionResponse }) {
  const details = decision.details as TradeDetailsData;
  const accept = details.net_value > 0;

  return (
    <div className="mt-4 p-4 bg-dark-800/50 rounded-lg border border-dark-700">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ArrowRightLeft className="w-4 h-4 text-primary-400" />
          <span className={cn('font-semibold', accept ? 'text-green-400' : 'text-red-400')}>
            {decision.decision}
          </span>
          <span className={cn('text-xs', getConfidenceColor(decision.confidence))}>
            {decision.confidence.toUpperCase()}
          </span>
        </div>
        <span className="text-xs text-dark-400">
          via {decision.source === 'local' ? 'Local Engine' : 'Claude AI'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Giving side */}
        <div>
          <div className="text-xs font-medium text-dark-400 uppercase mb-2">You Give</div>
          <div className="space-y-3">
            {details.side_giving.players.map((p) => (
              <div key={p.name} className="p-3 rounded-lg bg-dark-700/50">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="font-semibold text-sm">{p.name}</div>
                    {p.team && <div className="text-xs text-dark-400">{p.team}</div>}
                  </div>
                  <span className="text-lg font-bold text-primary-400">{p.score.toFixed(1)}</span>
                </div>
                <div className="space-y-1">
                  <IndexBar label="SCI" value={p.indices.sci} />
                  <IndexBar label="RMI" value={p.indices.rmi} />
                  <IndexBar label="GIS" value={p.indices.gis} />
                  <IndexBar label="OD" value={p.indices.od} max={50} />
                  <IndexBar label="MSF" value={p.indices.msf} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-center text-sm text-dark-300">
            Total: <span className="font-semibold">{details.side_giving.total_score.toFixed(1)}</span>
          </div>
        </div>

        {/* Receiving side */}
        <div>
          <div className="text-xs font-medium text-dark-400 uppercase mb-2">You Get</div>
          <div className="space-y-3">
            {details.side_receiving.players.map((p) => (
              <div key={p.name} className="p-3 rounded-lg bg-dark-700/50">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="font-semibold text-sm">{p.name}</div>
                    {p.team && <div className="text-xs text-dark-400">{p.team}</div>}
                  </div>
                  <span className="text-lg font-bold text-primary-400">{p.score.toFixed(1)}</span>
                </div>
                <div className="space-y-1">
                  <IndexBar label="SCI" value={p.indices.sci} />
                  <IndexBar label="RMI" value={p.indices.rmi} />
                  <IndexBar label="GIS" value={p.indices.gis} />
                  <IndexBar label="OD" value={p.indices.od} max={50} />
                  <IndexBar label="MSF" value={p.indices.msf} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-center text-sm text-dark-300">
            Total: <span className="font-semibold">{details.side_receiving.total_score.toFixed(1)}</span>
          </div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-dark-700 flex items-center justify-center gap-2 text-sm">
        <span className={cn('font-semibold', accept ? 'text-green-400' : 'text-red-400')}>
          Net: {details.net_value > 0 ? '+' : ''}{details.net_value.toFixed(1)} pts
        </span>
      </div>
    </div>
  );
}

function DraftDetails({ decision }: { decision: DecisionResponse }) {
  const details = decision.details as DraftDetailsData;

  return (
    <div className="mt-4 p-4 bg-dark-800/50 rounded-lg border border-dark-700">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Trophy className="w-4 h-4 text-primary-400" />
          <span className="font-semibold text-primary-300">
            Pick: {decision.decision}
          </span>
          <span className={cn('text-xs', getConfidenceColor(decision.confidence))}>
            {decision.confidence.toUpperCase()}
          </span>
        </div>
        <span className="text-xs text-dark-400">
          via {decision.source === 'local' ? 'Local Engine' : 'Claude AI'}
        </span>
      </div>

      <div className="space-y-2">
        {details.ranked_players.map((p, i) => (
          <div
            key={p.name}
            className={cn(
              'p-3 rounded-lg flex items-start gap-3',
              i === 0
                ? 'bg-green-500/10 border border-green-500/30'
                : 'bg-dark-700/50'
            )}
          >
            <span className={cn(
              'text-lg font-bold w-7 text-center flex-shrink-0',
              i === 0 ? 'text-green-400' : 'text-dark-400'
            )}>
              {p.rank}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm">{p.name}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-dark-600 text-dark-300">
                    {p.position}
                  </span>
                  {p.position_boosted && (
                    <span title="Position boosted">
                      <Zap className="w-3 h-3 text-yellow-400" />
                    </span>
                  )}
                </div>
                <span className="text-lg font-bold text-primary-400">{p.score.toFixed(1)}</span>
              </div>
              {p.team && (
                <div className="text-xs text-dark-400 mb-2">{p.team}</div>
              )}
              <div className="space-y-1">
                <IndexBar label="SCI" value={p.indices.sci} />
                <IndexBar label="RMI" value={p.indices.rmi} />
                <IndexBar label="GIS" value={p.indices.gis} />
                <IndexBar label="OD" value={p.indices.od} max={50} />
                <IndexBar label="MSF" value={p.indices.msf} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {details.position_needs && details.position_needs.length > 0 && (
        <div className="mt-3 pt-3 border-t border-dark-700 text-xs text-dark-400">
          Position needs: {details.position_needs.join(', ')}
        </div>
      )}
    </div>
  );
}

function WaiverDetails({ decision }: { decision: DecisionResponse }) {
  const details = decision.details as WaiverDetailsData;

  return (
    <div className="mt-4 p-4 bg-dark-800/50 rounded-lg border border-dark-700">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <UserPlus className="w-4 h-4 text-primary-400" />
          <span className="font-semibold text-primary-300">
            Waiver Recommendations
          </span>
          <span className={cn('text-xs', getConfidenceColor(decision.confidence))}>
            {decision.confidence.toUpperCase()}
          </span>
        </div>
        <span className="text-xs text-dark-400">
          via {decision.source === 'local' ? 'Local Engine' : 'Claude AI'}
        </span>
      </div>

      {/* Position needs badges */}
      {details.position_needs.length > 0 && (
        <div className="flex items-center gap-2 mb-4">
          <AlertCircle className="w-3.5 h-3.5 text-yellow-400" />
          <span className="text-xs text-dark-400">Needs:</span>
          <div className="flex gap-1.5">
            {details.position_needs.map((pos) => (
              <span
                key={pos}
                className="text-xs px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400 font-medium"
              >
                {pos}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Pickup recommendations */}
      {details.recommendations.length > 0 && (
        <div className="mb-4">
          <div className="text-xs font-medium text-dark-400 uppercase mb-2 flex items-center gap-1.5">
            <UserPlus className="w-3 h-3" /> Add
          </div>
          <div className="space-y-2">
            {details.recommendations.map((r, i) => (
              <div
                key={r.name}
                className={cn(
                  'p-3 rounded-lg',
                  i === 0
                    ? 'bg-green-500/10 border border-green-500/30'
                    : 'bg-dark-700/50'
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'text-sm font-bold w-5 text-center',
                      i === 0 ? 'text-green-400' : 'text-dark-400'
                    )}>
                      {r.priority}
                    </span>
                    <span className="font-semibold text-sm">{r.name}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-dark-600 text-dark-300">
                      {r.position}
                    </span>
                  </div>
                  <span className="text-xs text-dark-400">{r.team}</span>
                </div>
                <p className="text-xs text-dark-300 ml-7">{r.rationale}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Drop candidates */}
      {details.drop_candidates.length > 0 && (
        <div>
          <div className="text-xs font-medium text-dark-400 uppercase mb-2 flex items-center gap-1.5">
            <UserMinus className="w-3 h-3" /> Consider Dropping
          </div>
          <div className="space-y-2">
            {details.drop_candidates.map((d) => (
              <div key={d.name} className="p-3 rounded-lg bg-red-500/5 border border-red-500/20">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-sm text-red-300">{d.name}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-dark-600 text-dark-300">
                    {d.position}
                  </span>
                </div>
                <p className="text-xs text-dark-400">{d.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DecisionDetails({ decision }: { decision: DecisionResponse }) {
  if (!decision.details) return null;

  if (isWaiverDetails(decision.details)) {
    return <WaiverDetails decision={decision} />;
  }

  if (isDraftDetails(decision.details)) {
    return <DraftDetails decision={decision} />;
  }

  if (isTradeDetails(decision.details)) {
    return <TradeDetails decision={decision} />;
  }

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
    <div className={cn('flex gap-3 animate-fadeIn', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-500/20 flex items-center justify-center ring-2 ring-primary-500/10">
          <Bot className="w-5 h-5 text-primary-400" />
        </div>
      )}

      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-3 shadow-lg',
          isUser
            ? 'bg-gradient-to-br from-primary-600 to-primary-700 text-white rounded-br-md shadow-primary-500/20'
            : 'bg-dark-800/90 text-dark-100 rounded-bl-md border border-dark-700/50'
        )}
      >
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>

        {message.decision && <DecisionDetails decision={message.decision} />}

        <div
          className={cn(
            'text-xs mt-2 opacity-70',
            isUser ? 'text-primary-100' : 'text-dark-400'
          )}
        >
          {formatRelativeTime(message.timestamp)}
        </div>
      </div>

      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-dark-600 to-dark-700 flex items-center justify-center ring-2 ring-dark-600/50">
          <User className="w-5 h-5 text-dark-200" />
        </div>
      )}
    </div>
  );
}

export default MessageBubble;
