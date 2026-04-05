import { Brain, AlertTriangle } from 'lucide-react';
import type { CognitiveState } from '@/types';
import { getLoadBgColor, getLoadColor } from '@/lib/utils';

interface Props { states: CognitiveState[]; }

export function CognitiveLoadPanel({ states }: Props) {
  const overloaded = states.filter(s => s.overload_flag);
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-900">Cognitive Load</h3>
        </div>
        {overloaded.length > 0 && (
          <span className="flex items-center gap-1 text-xs bg-red-50 text-red-600 px-2 py-1 rounded-full font-medium">
            <AlertTriangle className="w-3 h-3" />
            {overloaded.length} overloaded
          </span>
        )}
      </div>
      {states.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-4">No load data yet. Process a meeting to see cognitive states.</p>
      ) : (
        <div className="space-y-3">
          {states.map((s) => (
            <div key={s.id}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-gray-700">{s.owner}</span>
                <div className="flex items-center gap-2">
                  {s.overload_flag && <AlertTriangle className="w-3.5 h-3.5 text-red-500" />}
                  <span className={`text-sm font-bold ${getLoadColor(s.load_percentage)}`}>
                    {s.load_percentage.toFixed(0)}%
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
                <p className="text-xs text-red-500 mt-1">Overloaded — no new calendar blocks added</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
