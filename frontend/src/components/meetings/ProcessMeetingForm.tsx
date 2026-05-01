'use client';
import { useState, useEffect, useRef } from 'react';
import { Upload, Loader2, CheckCircle, AlertTriangle, FileText, X } from 'lucide-react';
import { api } from '@/lib/api';
import type { ProcessMeetingResponse } from '@/types';
import { getAgentColor } from '@/lib/utils';

const API = 'https://workbrain-backend-114869691007.us-central1.run.app';

const DEMO_TRANSCRIPT = `Q2 Planning Meeting - April 30th 2026
Attendees: Naveen, Ravi, Sushma

Naveen will lead the API platform redesign by May 15th. Critical backend architecture task requiring 6 hours of deep focus work.

Ravi owns the payment gateway integration by May 14th. High priority, estimated 5 hours of focused development.

Sushma will deliver the new design system component library by May 12th. High complexity, needs 4 hours uninterrupted focus time.

Naveen mentioned he already has several ongoing commitments and is feeling stretched thin this sprint.

Next team sync scheduled for May 5th at 3pm IST. All three should attend.`;

interface ProgressEvent {
  type: 'progress' | 'done' | 'error' | 'started';
  step?: number;
  total?: number;
  message?: string;
  status?: string;
  result?: ProcessMeetingResponse;
}

interface Props { onComplete: () => void; }

// Clean VTT/SRT subtitle files
function cleanSubtitleFile(text: string): string {
  return text
    .replace(/WEBVTT\n?/g, '')
    .replace(/\d{2}:\d{2}:\d{2}[\.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[\.,]\d{3}\n?/g, '')
    .replace(/^\d+\s*\n/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

// Read file as text
function readAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = e => resolve(e.target?.result as string || '');
    reader.onerror = reject;
    reader.readAsText(file);
  });
}

// Extract text from PDF using pdfjs
async function extractPdfText(file: File): Promise<string> {
  const arrayBuffer = await file.arrayBuffer();
  
  // Dynamically load pdfjs from CDN
  if (!(window as any).pdfjsLib) {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
      script.onload = () => resolve();
      script.onerror = reject;
      document.head.appendChild(script);
    });
    (window as any).pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  }

  const pdfjsLib = (window as any).pdfjsLib;
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  const pages: string[] = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    const pageText = content.items
      .map((item: any) => item.str)
      .join(' ');
    pages.push(pageText);
  }

  return pages.join('\n\n');
}

export function ProcessMeetingForm({ onComplete }: Props) {
  const [transcript, setTranscript] = useState('');
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<ProcessMeetingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [currentMessage, setCurrentMessage] = useState('');
  const [uploadedFile, setUploadedFile] = useState<{name: string, words: number} | null>(null);
  const [extracting, setExtracting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setExtracting(true);
    setError(null);
    setUploadedFile(null);

    try {
      const ext = file.name.split('.').pop()?.toLowerCase();
      let text = '';

      if (ext === 'txt') {
        text = await readAsText(file);
      } else if (ext === 'pdf') {
        text = await extractPdfText(file);
      } else if (ext === 'vtt' || ext === 'srt') {
        text = cleanSubtitleFile(await readAsText(file));
      } else {
        setError('Unsupported file type. Use PDF, TXT, VTT, or SRT.');
        setExtracting(false);
        return;
      }

      if (!text.trim()) {
        setError('Could not extract text from file. Try copying the text manually.');
        setExtracting(false);
        return;
      }

      const wordCount = text.trim().split(/\s+/).length;
      setTranscript(text);
      setUploadedFile({ name: file.name, words: wordCount });
    } catch (e) {
      setError(`File extraction failed: ${e instanceof Error ? e.message : 'Unknown error'}`);
    } finally {
      setExtracting(false);
      // Reset file input so same file can be re-uploaded
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function handleProcess() {
    if (!transcript.trim()) return;
    setProcessing(true);
    setResult(null);
    setError(null);
    setCurrentStep(0);
    setCurrentMessage('Connecting to WorkBrain pipeline...');

    try {
      const title = uploadedFile
        ? uploadedFile.name.replace(/\.[^/.]+$/, '')
        : 'Meeting';

      const response = await fetch(`${API}/api/meetings/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript, title }),
      });

      if (!response.ok) throw new Error(`Failed: ${response.statusText}`);
      if (!response.body) throw new Error('No response body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data: ProgressEvent = JSON.parse(line.slice(6));
            if (data.type === 'started') {
              setCurrentMessage('Pipeline started...');
            } else if (data.type === 'progress') {
              setCurrentStep(data.step || 0);
              setCurrentMessage(data.message || '');
            } else if (data.type === 'done') {
              setCurrentStep(4);
              setCurrentMessage('Pipeline complete!');
              if (data.result) setResult(data.result);
              setProcessing(false);
              setUploadedFile(null);
              onComplete();
            } else if (data.type === 'error') {
              setError(data.message || 'Pipeline failed');
              setProcessing(false);
            }
          } catch { /* skip malformed lines */ }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Processing failed');
      setProcessing(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Upload className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">Process Meeting</h3>
        <div className="ml-auto flex items-center gap-2">
          {/* File upload button */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.pdf,.vtt,.srt"
            onChange={handleFileChange}
            className="hidden"
            disabled={processing}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={processing || extracting}
            className="text-xs text-gray-500 hover:text-gray-700 font-medium flex items-center gap-1 border border-gray-200 rounded px-2 py-1"
          >
            {extracting
              ? <><Loader2 className="w-3 h-3 animate-spin" /> Extracting...</>
              : <><FileText className="w-3 h-3" /> Upload file</>
            }
          </button>
          <button
            onClick={() => { setTranscript(DEMO_TRANSCRIPT); setUploadedFile(null); }}
            className="text-xs text-blue-600 hover:text-blue-700 font-medium"
            disabled={processing}
          >
            Load demo
          </button>
        </div>
      </div>

      {/* Uploaded file indicator */}
      {uploadedFile && (
        <div className="mb-2 flex items-center gap-2 text-xs bg-blue-50 text-blue-700 rounded-lg px-3 py-2">
          <FileText className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="font-medium">{uploadedFile.name}</span>
          <span className="text-blue-500">({uploadedFile.words.toLocaleString()} words extracted)</span>
          <button
            onClick={() => { setUploadedFile(null); setTranscript(''); }}
            className="ml-auto text-blue-400 hover:text-blue-600"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      <textarea
        value={transcript}
        onChange={e => setTranscript(e.target.value)}
        placeholder="Paste your meeting transcript here, or upload a PDF/TXT/VTT file..."
        rows={6}
        className="w-full text-sm border border-gray-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-gray-700 placeholder-gray-400"
        disabled={processing}
      />

      {processing && (
        <div className="mt-3 bg-blue-50 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
            <span className="text-xs font-medium text-blue-700">{currentMessage}</span>
          </div>
          <div className="w-full bg-blue-100 rounded-full h-1.5 mb-2">
            <div
              className="bg-blue-600 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${(currentStep / 4) * 100}%` }}
            />
          </div>
          <div className="flex justify-between">
            {[1,2,3,4].map(s => (
              <div key={s} className={`text-xs px-1 ${s <= currentStep ? 'text-blue-600 font-medium' : 'text-gray-400'}`}>
                {s <= currentStep ? '✓' : `${s}`}
              </div>
            ))}
          </div>
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
          {result.overloaded_owners?.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-orange-600 bg-orange-50 rounded px-2 py-1 mb-2">
              <AlertTriangle className="w-3.5 h-3.5" />
              Overloaded: {result.overloaded_owners.join(', ')}
            </div>
          )}
          {result.decisions?.slice(0, 3).map(d => (
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
        {processing
          ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing...</>
          : 'Process Meeting →'
        }
      </button>
    </div>
  );
}