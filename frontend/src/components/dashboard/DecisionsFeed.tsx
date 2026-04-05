import { Zap, Clock } from 'lucide-react';
import type { DecisionLog } from '@/types';
import { getAgentColor, formatRelative } from '@/lib/utils';

interface Props { decisions: DecisionLog[]; }

const AGENT_ICONS: Record<string, string> = {
  transcript: '📝', cognitive: '🧠', scheduler: '📅',
  execution: '⚡', orchestrator: '🎯',
};

export function DecisionsFeed({ decisions }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">AI Decisions</h3>
        <span className="ml-auto text-xs text-gray-400">{decisions.length} total</span>
      </div>
      {decisions.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-4">No decisions yet. Process a meeting to see AI reasoning.</p>
      ) : (
        <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
          {decisions.map((d) => (
            <div key={d.id} className="border border-gray-100 rounded-lg p-3 hover:border-gray-200 transition-colors">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">{AGENT_ICONS[d.agent] || '🤖'}</span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${getAgentColor(d.agent)}`}>
                  {d.agent}
                </span>
                <span className="text-xs font-medium text-gray-800 flex-1 truncate">{d.decision}</span>
              </div>
              <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">{d.reason}</p>
              <div className="flex items-center gap-1 mt-2">
                <Clock className="w-3 h-3 text-gray-300" />
                <span className="text-xs text-gray-400">{formatRelative(d.timestamp)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
