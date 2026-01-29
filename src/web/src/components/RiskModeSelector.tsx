'use client';

import { cn } from '@/lib/utils';
import { RiskMode } from '@/types';
import { Shield, Target, TrendingUp } from 'lucide-react';

interface RiskModeOption {
  value: RiskMode;
  label: string;
  description: string;
  icon: typeof Shield;
  color: string;
}

const RISK_MODES: RiskModeOption[] = [
  {
    value: 'floor',
    label: 'Floor',
    description: 'Prioritize consistency and safety',
    icon: Shield,
    color: 'text-green-400 bg-green-500/10 border-green-500',
  },
  {
    value: 'median',
    label: 'Median',
    description: 'Balanced approach',
    icon: Target,
    color: 'text-blue-400 bg-blue-500/10 border-blue-500',
  },
  {
    value: 'ceiling',
    label: 'Ceiling',
    description: 'Chase upside potential',
    icon: TrendingUp,
    color: 'text-orange-400 bg-orange-500/10 border-orange-500',
  },
];

interface RiskModeSelectorProps {
  value: RiskMode;
  onChange: (mode: RiskMode) => void;
  disabled?: boolean;
  compact?: boolean;
}

export function RiskModeSelector({
  value,
  onChange,
  disabled,
  compact = false,
}: RiskModeSelectorProps) {
  if (compact) {
    return (
      <div className="flex gap-1 p-1 bg-dark-800 rounded-lg">
        {RISK_MODES.map((mode) => {
          const Icon = mode.icon;
          const isSelected = value === mode.value;
          return (
            <button
              key={mode.value}
              onClick={() => onChange(mode.value)}
              disabled={disabled}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all',
                isSelected
                  ? mode.color
                  : 'text-dark-400 hover:text-dark-200 hover:bg-dark-700',
                disabled && 'opacity-50 cursor-not-allowed'
              )}
              title={mode.description}
            >
              <Icon className="w-4 h-4" />
              <span>{mode.label}</span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-3">
      {RISK_MODES.map((mode) => {
        const Icon = mode.icon;
        const isSelected = value === mode.value;
        return (
          <button
            key={mode.value}
            onClick={() => onChange(mode.value)}
            disabled={disabled}
            className={cn(
              'flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all',
              isSelected
                ? mode.color
                : 'border-dark-700 bg-dark-800/50 text-dark-300 hover:border-dark-600',
              disabled && 'opacity-50 cursor-not-allowed'
            )}
          >
            <Icon className="w-6 h-6" />
            <div className="text-center">
              <div className="font-semibold">{mode.label}</div>
              <div className="text-xs text-dark-400 mt-1">{mode.description}</div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

export default RiskModeSelector;
