

'use client';
import { TopNav } from '@/components/layout/TopNav';
import { AddTaskForm } from '@/components/tasks/AddTaskForm';
import { TaskTable } from '@/components/tasks/TaskTable';
import { CognitiveLoadPanel } from '@/components/dashboard/CognitiveLoadPanel';
import { WorkBrainSidebar } from '@/components/copilot/WorkBrainSidebar';
import { useDashboard } from '@/hooks/useDashboard';
import { Loader2, RefreshCw } from 'lucide-react';
import { useState } from 'react';

const API = 'https://workbrain-backend-114869691007.us-central1.run.app';

export default function TasksPage() {
  const { data, loading, refetch } = useDashboard(5000);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);

  const syncFromGoogleTasks = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await fetch(`${API}/api/tasks/sync-google`, { method: 'POST' });
      const data = await res.json();
      setSyncResult(`✅ Synced ${data.synced} tasks from Google Tasks`);
      refetch();
    } catch (e) {
      setSyncResult('❌ Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <TopNav />
      <div className="flex h-[calc(100vh-56px)]">
        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-4xl mx-auto space-y-5">
            <div className="flex items-center justify-between">
              <h1 className="text-xl font-bold text-gray-900">Tasks</h1>
              <button
                onClick={syncFromGoogleTasks}
                disabled={syncing}
                className="flex items-center gap-2 text-sm bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Syncing...' : 'Sync from Google Tasks'}
              </button>
            </div>
            {syncResult && (
              <div className="text-sm bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-green-700">
                {syncResult}
              </div>
            )}
            <div className="grid grid-cols-3 gap-5">
              <div className="col-span-2 space-y-4">
                <AddTaskForm onComplete={refetch} />
                {loading && !data
                  ? <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
                  : <TaskTable items={data?.action_items || []} onStatusChange={refetch} />
                }
              </div>
              <div>
                {data && <CognitiveLoadPanel states={data.cognitive_states} onRefresh={refetch} />}
              </div>
            </div>
          </div>
        </div>
        <div className="w-80 border-l border-gray-200 bg-white flex-shrink-0">
          <WorkBrainSidebar dashboardData={data} onRefresh={refetch} />
        </div>
      </div>
    </div>
  );
}
