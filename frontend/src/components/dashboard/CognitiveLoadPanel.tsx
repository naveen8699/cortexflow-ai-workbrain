'use client';
import { useState } from 'react';
import { Brain, AlertTriangle, RefreshCw } from 'lucide-react';
import type { CognitiveState } from '@/types';
import { getLoadBgColor, getLoadColor } from '@/lib/utils';

const API = 'https://workbrain-backend-114869691007.us-central1.run.app';

interface Props { states: CognitiveState[]; onRefresh?: () => void; }

export function CognitiveLoadPanel({ states, onRefresh }: Props) {
  const overloaded = states.filter(s => s.overload_flag);
  const [recalculating, setRecalculating] = useState(false);

  const recalculate = async () => {
    setRecalculating(true);
    try {
      await fetch(`${API}/api/cognitive/recalculate`, { method: 'POST' });
      onRefresh?.();
    } catch (e) {
      console.error('Recalculate failed', e);
    } finally {
      setRecalculating(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-900">Cognitive Load</h3>
        </div>
        <div className="flex items-center gap-2">
          {overloaded.length > 0 && (
            <span className="flex items-center gap-1 text-xs bg-red-50 text-red-600 px-2 py-1 rounded-full font-medium">
              <AlertTriangle className="w-3 h-3" />
              {overloaded.length} overloaded
            </span>
          )}
          <button
            onClick={recalculate}
            disabled={recalculating}
            title="Recalculate cognitive load"
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600 px-2 py-1 rounded-lg hover:bg-blue-50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${recalculating ? 'animate-spin' : ''}`} />
            {recalculating ? 'Recalculating...' : 'Recalculate'}
          </button>
        </div>
      </div>
      <div className="space-y-3">
        {states.map(s => (
          <div key={s.owner}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-gray-700">{s.owner}</span>
              <div className="flex items-center gap-1">
                {s.overload_flag && <AlertTriangle className="w-3 h-3 text-red-500" />}
                <span className={`text-sm font-semibold ${getLoadColor(s.load_percentage)}`}>
                  {s.load_percentage}%
                </span>
              </div>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-500 ${getLoadBgColor(s.load_percentage)}`}
                style={{ width: `${Math.min(s.load_percentage, 100)}%` }}
              />
            </div>
            {s.overload_flag && (
              <p className="text-xs text-red-500 mt-0.5">Overloaded — no new calendar blocks added</p>
            )}
          </div>
        ))}
        {states.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-4">No load data yet. Process a meeting first.</p>
        )}
      </div>
    </div>
  );
}
