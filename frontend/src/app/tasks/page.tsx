'use client';
import { TopNav } from '@/components/layout/TopNav';
import { AddTaskForm } from '@/components/tasks/AddTaskForm';
import { TaskTable } from '@/components/tasks/TaskTable';
import { CognitiveLoadPanel } from '@/components/dashboard/CognitiveLoadPanel';
import { WorkBrainSidebar } from '@/components/copilot/WorkBrainSidebar';
import { useDashboard } from '@/hooks/useDashboard';
import { Loader2 } from 'lucide-react';

export default function TasksPage() {
  const { data, loading, refetch } = useDashboard(5000);
  return (
    <div className="min-h-screen bg-gray-50">
      <TopNav />
      <div className="flex h-[calc(100vh-56px)]">
        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-4xl mx-auto space-y-5">
            <h1 className="text-xl font-bold text-gray-900">Tasks</h1>
            <div className="grid grid-cols-3 gap-5">
              <div className="col-span-2 space-y-4">
                <AddTaskForm onComplete={refetch} />
                {loading && !data
                  ? <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
                  : <TaskTable items={data?.action_items || []} />
                }
              </div>
              <div>
                <CognitiveLoadPanel states={data?.cognitive_states || []} />
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
