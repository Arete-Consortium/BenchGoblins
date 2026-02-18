'use client';

import { useState } from 'react';
import { X, Plus, Users, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Sport } from '@/types';

interface RosterPlayer {
  name: string;
  position: string;
  team: string;
}

interface ManualRosterFormProps {
  sport: Sport;
  onClose: () => void;
  onSaved?: (rosterId: string) => void;
}

const POSITIONS: Record<Sport, string[]> = {
  nba: ['PG', 'SG', 'SF', 'PF', 'C'],
  nfl: ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'],
  mlb: ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH', 'SP', 'RP'],
  nhl: ['C', 'LW', 'RW', 'D', 'G'],
  soccer: ['GK', 'DEF', 'MID', 'FWD'],
};

export function ManualRosterForm({ sport, onClose, onSaved }: ManualRosterFormProps) {
  const [players, setPlayers] = useState<RosterPlayer[]>([
    { name: '', position: POSITIONS[sport][0], team: '' },
  ]);
  const [teamName, setTeamName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const addPlayer = () => {
    if (players.length >= 30) return;
    setPlayers([...players, { name: '', position: POSITIONS[sport][0], team: '' }]);
  };

  const removePlayer = (index: number) => {
    if (players.length <= 1) return;
    setPlayers(players.filter((_, i) => i !== index));
  };

  const updatePlayer = (index: number, field: keyof RosterPlayer, value: string) => {
    const updated = [...players];
    updated[index] = { ...updated[index], [field]: value };
    setPlayers(updated);
  };

  const handleSave = async () => {
    const validPlayers = players.filter((p) => p.name.trim());
    if (validPlayers.length === 0) {
      setError('Add at least one player');
      return;
    }

    setSaving(true);
    setError('');

    try {
      const baseUrl = '/bapi';
      const res = await fetch(`${baseUrl}/roster/manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sport,
          players: validPlayers,
          team_name: teamName || undefined,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save roster');
      }

      const data = await res.json();
      onSaved?.(data.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-dark-800/90 border border-dark-700 rounded-xl p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary-400" />
          <h3 className="font-semibold">Manual Roster Entry</h3>
        </div>
        <button onClick={onClose} className="text-dark-400 hover:text-dark-200">
          <X className="h-5 w-5" />
        </button>
      </div>

      <input
        type="text"
        value={teamName}
        onChange={(e) => setTeamName(e.target.value)}
        placeholder="Team name (optional)"
        className="w-full px-3 py-2 rounded-lg bg-dark-900 border border-dark-700 text-dark-100 placeholder:text-dark-500 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500/50"
      />

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {players.map((player, i) => (
          <div key={i} className="flex gap-2 items-center">
            <input
              type="text"
              value={player.name}
              onChange={(e) => updatePlayer(i, 'name', e.target.value)}
              placeholder="Player name"
              className="flex-1 px-3 py-1.5 rounded-lg bg-dark-900 border border-dark-700 text-dark-100 placeholder:text-dark-500 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500/50"
            />
            <select
              value={player.position}
              onChange={(e) => updatePlayer(i, 'position', e.target.value)}
              className="px-2 py-1.5 rounded-lg bg-dark-900 border border-dark-700 text-dark-100 text-sm focus:outline-none"
            >
              {POSITIONS[sport].map((pos) => (
                <option key={pos} value={pos}>{pos}</option>
              ))}
            </select>
            <input
              type="text"
              value={player.team}
              onChange={(e) => updatePlayer(i, 'team', e.target.value)}
              placeholder="Team"
              className="w-20 px-2 py-1.5 rounded-lg bg-dark-900 border border-dark-700 text-dark-100 placeholder:text-dark-500 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500/50"
            />
            <button
              onClick={() => removePlayer(i)}
              disabled={players.length <= 1}
              className="text-dark-500 hover:text-red-400 disabled:opacity-30"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={addPlayer}
          disabled={players.length >= 30}
          className="gap-1 text-dark-400"
        >
          <Plus className="h-4 w-4" />
          Add Player
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={saving}
          className="gap-1.5"
        >
          <Save className="h-4 w-4" />
          {saving ? 'Saving...' : 'Save Roster'}
        </Button>
      </div>
    </div>
  );
}
