'use client';

import { cn, getSportDisplayName } from '@/lib/utils';
import { Sport } from '@/types';

const SPORTS: Sport[] = ['nba', 'nfl', 'mlb', 'nhl'];

const SPORT_ICONS: Record<Sport, string> = {
  nba: '🏀',
  nfl: '🏈',
  mlb: '⚾',
  nhl: '🏒',
};

interface SportSelectorProps {
  value: Sport;
  onChange: (sport: Sport) => void;
  disabled?: boolean;
}

export function SportSelector({ value, onChange, disabled }: SportSelectorProps) {
  return (
    <div className="flex gap-2">
      {SPORTS.map((sport) => (
        <button
          key={sport}
          onClick={() => onChange(sport)}
          disabled={disabled}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all',
            'border-2',
            value === sport
              ? 'border-primary-500 bg-primary-500/10 text-primary-400'
              : 'border-dark-700 bg-dark-800 text-dark-300 hover:border-dark-600 hover:text-dark-200',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          <span className="text-lg">{SPORT_ICONS[sport]}</span>
          <span className="hidden sm:inline">{getSportDisplayName(sport)}</span>
        </button>
      ))}
    </div>
  );
}

export default SportSelector;
