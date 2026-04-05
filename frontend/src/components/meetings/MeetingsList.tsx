'use client';
import { useState } from 'react';
import { Users, ChevronDown, ChevronUp, CheckCircle, Clock, XCircle, Loader2 } from 'lucide-react';
import type { Meeting, DecisionLog } from '@/types';
import { getStatusColor, formatRelative, formatDateTime } from '@/lib/utils';
import { api } from '@/lib/api';
import { getAgentColor } from '@/lib/utils';

const AGENT_ICONS: Record<string, string> = {
  transcript: '📝', cognitive: '🧠', scheduler: '📅', execution: '⚡', orchestrator: '🎯',
};

function StatusIcon({ status }: { status: string }) {
  if (status === 'processed') return <CheckCircle className="w-4 h-4 text-green-500" />;
  if (status === 'processing') return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
  if (status === 'failed') return <XCircle className="w-4 h-4 text-red-500" />;
  return <Clock className="w-4 h-4 text-gray-400" />;
}

function MeetingCard({ meeting }: { meeting: Meeting }) {
  const [expanded, setExpanded] = useState(false);
  const [decisions, setDecisions] = useState<DecisionLog[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadDecisions() {
    if (decisions) return;
    setLoading(true);
    try {
      const d = await api.getMeetingDecisions(meeting.id);
      setDecisions(d);
    } catch { setDecisions([]); }
    finally { setLoading(false); }
  }

  function toggle() {
    if (!expanded) loadDecisions();
    setExpanded(p => !p);
  }

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button onClick={toggle}
        className="w-full px-5 py-4 hover:bg-gray-50 flex items-center gap-3 text-left">
        <StatusIcon status={meeting.status} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900">{meeting.title || 'Untitled meeting'}</p>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
            <span>{formatRelative(meeting.created_at)}</span>
            <span className={`px-1.5 py-0.5 rounded-full ${getStatusColor(meeting.status)}`}>{meeting.status}</span>
            <span>{meeting.action_items_count} actions</span>
            <span>{meeting.decisions_count} decisions</span>
          </div>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-5 py-4">
          {meeting.summary && (
            <div className="mb-4 bg-blue-50 rounded-lg p-3">
              <p className="text-xs font-medium text-blue-700 mb-1">Meeting Summary</p>
              <p className="text-sm text-blue-800">{meeting.summary}</p>
            </div>
          )}
          {loading && <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> Loading decisions...</div>}
          {decisions && decisions.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">Agent Decisions ({decisions.length})</p>
              <div className="space-y-2">
                {decisions.map(d => (
                  <div key={d.id} className="bg-gray-50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span>{AGENT_ICONS[d.agent] || '🤖'}</span>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${getAgentColor(d.agent)}`}>{d.agent}</span>
                      <span className="text-xs font-medium text-gray-800">{d.decision}</span>
                      <span className="ml-auto text-xs text-gray-400">{formatDateTime(d.timestamp)}</span>
                    </div>
                    <p className="text-xs text-gray-600 leading-relaxed">{d.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {decisions && decisions.length === 0 && (
            <p className="text-sm text-gray-400">No decisions logged for this meeting.</p>
          )}
        </div>
      )}
    </div>
  );
}

interface Props { meetings: Meeting[]; }
export function MeetingsList({ meetings }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
        <Users className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">Meeting History</h3>
        <span className="ml-auto text-xs text-gray-400">{meetings.length} meetings</span>
      </div>
      {meetings.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">No meetings yet. Process your first transcript above.</p>
      ) : (
        <div className="p-4 space-y-3">
          {meetings.map(m => <MeetingCard key={m.id} meeting={m} />)}
        </div>
      )}
    </div>
  );
}
