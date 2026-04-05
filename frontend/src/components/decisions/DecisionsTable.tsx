import { FileText, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import type { DecisionLog } from '@/types';
import { getAgentColor, formatDateTime } from '@/lib/utils';

const AGENT_ICONS: Record<string, string> = {
  transcript: '📝', cognitive: '🧠', scheduler: '📅',
  execution: '⚡', orchestrator: '🎯',
};

interface Props { decisions: DecisionLog[]; }

function DecisionRow({ d }: { d: DecisionLog }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border-b border-gray-50 last:border-0">
      <button
        onClick={() => setExpanded(p => !p)}
        className="w-full px-5 py-3.5 hover:bg-gray-50 flex items-center gap-3 text-left"
      >
        <span className="text-lg">{AGENT_ICONS[d.agent] || '🤖'}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${getAgentColor(d.agent)}`}>
              {d.agent}
            </span>
            <span className="text-sm font-medium text-gray-800 truncate">{d.decision}</span>
          </div>
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <Clock className="w-3 h-3" />
            {formatDateTime(d.timestamp)}
          </div>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-gray-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />}
      </button>
      {expanded && (
        <div className="px-5 pb-4">
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs font-medium text-gray-500 mb-1.5">AI Reasoning</p>
            <p className="text-sm text-gray-700 leading-relaxed">{d.reason}</p>
            {d.metadata && Object.keys(d.metadata).length > 0 && (
              <details className="mt-2">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">Show metadata</summary>
                <pre className="mt-1 text-xs text-gray-500 overflow-auto">{JSON.stringify(d.metadata, null, 2)}</pre>
              </details>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function DecisionsTable({ decisions }: Props) {
  const [filter, setFilter] = useState<string>('all');
  const agents = ['all', 'orchestrator', 'transcript', 'cognitive', 'scheduler', 'execution'];
  const filtered = filter === 'all' ? decisions : decisions.filter(d => d.agent === filter);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2 flex-wrap">
        <FileText className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">All Decisions</h3>
        <div className="ml-auto flex gap-1 flex-wrap">
          {agents.map(a => (
            <button key={a} onClick={() => setFilter(a)}
              className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${
                filter === a ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}>
              {a}
            </button>
          ))}
        </div>
      </div>
      {filtered.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">No decisions found.</p>
      ) : (
        <div className="divide-y divide-gray-50">
          {filtered.map(d => <DecisionRow key={d.id} d={d} />)}
        </div>
      )}
    </div>
  );
}
