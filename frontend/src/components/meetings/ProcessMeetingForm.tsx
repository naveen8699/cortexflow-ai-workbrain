'use client';
import { useState } from 'react';
import { Upload, Loader2, CheckCircle, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';
import type { ProcessMeetingResponse } from '@/types';
import { getAgentColor } from '@/lib/utils';

const DEMO_TRANSCRIPT = `Team sync - April 4th
Attendees: Arjun, Priya, Dev

We agreed the API redesign must be done by April 10th. Arjun owns this. This is a complex backend task.

Priya will prepare the demo deck by April 8th. She needs at least 2 hours of uninterrupted focus time.

Dev to review the security audit report before April 9th. This was flagged as high priority.

Next sync scheduled for April 11th at 3pm. All three should attend.

Arjun mentioned he already has 3 other deadlines this week and is feeling quite stretched thin.`;

interface Props { onComplete: () => void; }

export function ProcessMeetingForm({ onComplete }: Props) {
  const [transcript, setTranscript] = useState('');
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<ProcessMeetingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState('');

  const STEPS = [
    'Sending to Orchestrator Agent...',
    'Transcript Agent extracting action items...',
    'Cognitive Load Agent calculating load scores...',
    'Scheduler Agent creating calendar events...',
    'Execution Agent creating task cards...',
    'Writing decisions to database...',
  ];

  async function handleProcess() {
    if (!transcript.trim()) return;
    setProcessing(true);
    setResult(null);
    setError(null);

    // Animate through steps
    let i = 0;
    const interval = setInterval(() => {
      if (i < STEPS.length) { setStep(STEPS[i]); i++; }
    }, 1200);

    try {
      const res = await api.processMeeting(transcript);
      clearInterval(interval);
      setResult(res);
      setStep('');
      onComplete();
    } catch (e) {
      clearInterval(interval);
      setError(e instanceof Error ? e.message : 'Processing failed');
      setStep('');
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Upload className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">Process Meeting</h3>
        <button
          onClick={() => setTranscript(DEMO_TRANSCRIPT)}
          className="ml-auto text-xs text-blue-600 hover:text-blue-700 font-medium"
        >
          Load demo transcript
        </button>
      </div>

      <textarea
        value={transcript}
        onChange={e => setTranscript(e.target.value)}
        placeholder="Paste your meeting transcript here..."
        rows={6}
        className="w-full text-sm border border-gray-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-gray-700 placeholder-gray-400"
        disabled={processing}
      />

      {processing && (
        <div className="mt-3 flex items-center gap-2 text-sm text-blue-600 bg-blue-50 rounded-lg px-3 py-2">
          <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
          <span className="text-xs">{step}</span>
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="text-xs">{error}</span>
        </div>
      )}

      {result && (
        <div className="mt-3 bg-green-50 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-4 h-4 text-green-600" />
            <span className="text-sm font-medium text-green-700">Processing complete!</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs text-gray-600 mb-3">
            <span>📋 {result.action_items_created} action items</span>
            <span>📅 {result.events_created} calendar events</span>
            <span>✅ {result.tasks_created} task cards</span>
          </div>
          {result.overloaded_owners.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-orange-600 bg-orange-50 rounded px-2 py-1 mb-2">
              <AlertTriangle className="w-3.5 h-3.5" />
              Overloaded: {result.overloaded_owners.join(', ')}
            </div>
          )}
          {result.decisions.slice(0, 3).map(d => (
            <div key={d.id} className="text-xs bg-white rounded p-2 mb-1 border border-green-100">
              <span className={`inline-block text-xs px-1.5 py-0.5 rounded-full mr-1 ${getAgentColor(d.agent)}`}>
                {d.agent}
              </span>
              <span className="text-gray-700">{d.decision}</span>
            </div>
          ))}
        </div>
      )}

      <button
        onClick={handleProcess}
        disabled={processing || !transcript.trim()}
        className="mt-3 w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {processing ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing...</> : 'Process Meeting →'}
      </button>
    </div>
  );
}
