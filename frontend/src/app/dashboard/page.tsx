'use client';
import { TopNav } from '@/components/layout/TopNav';
import { StatCards } from '@/components/dashboard/StatCards';
import { CognitiveLoadPanel } from '@/components/dashboard/CognitiveLoadPanel';
import { DecisionsFeed } from '@/components/dashboard/DecisionsFeed';
import { SchedulePanel } from '@/components/dashboard/SchedulePanel';
import { ProcessMeetingForm } from '@/components/meetings/ProcessMeetingForm';
import { AddTaskForm } from '@/components/tasks/AddTaskForm';
import { WorkBrainSidebar } from '@/components/copilot/WorkBrainSidebar';
import { useDashboard } from '@/hooks/useDashboard';
import { Loader2, RefreshCw, AlertCircle } from 'lucide-react';

export default function DashboardPage() {
  const { data, loading, error, refetch } = useDashboard(3000);

  return (
    <div className="min-h-screen bg-gray-50">
      <TopNav />
      <div className="flex h-[calc(100vh-56px)]">
        {/* Main content */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-6 max-w-5xl mx-auto space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>
                <p className="text-sm text-gray-500 mt-0.5">
                  AI-powered meeting execution · Powered by Google ADK + Vertex AI
                </p>
              </div>
              <button onClick={refetch}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
                <RefreshCw className="w-4 h-4" /> Refresh
              </button>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-4 py-3">
                <AlertCircle className="w-4 h-4" /> {error}
              </div>
            )}

            {/* Loading skeleton */}
            {loading && !data && (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              </div>
            )}

            {data && (
              <>
                {/* Stats row */}
                <StatCards stats={data.stats} />

                {/* Overload alert */}
                {data.stats.overloaded_owners.length > 0 && (
                  <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
                    <span className="text-xl">⚠️</span>
                    <div>
                      <p className="text-sm font-semibold text-red-700">Cognitive Overload Detected</p>
                      <p className="text-sm text-red-600 mt-0.5">
                        {data.stats.overloaded_owners.join(', ')} {data.stats.overloaded_owners.length === 1 ? 'is' : 'are'} overloaded.
                        Calendar blocks were not added to avoid increasing schedule pressure.
                      </p>
                    </div>
                  </div>
                )}

                {/* Input row */}
                <div className="grid grid-cols-2 gap-4">
                  <ProcessMeetingForm onComplete={refetch} />
                  <div className="space-y-4">
                    <AddTaskForm onComplete={refetch} />
                    <CognitiveLoadPanel states={data.cognitive_states} />
                  </div>
                </div>

                {/* Info panels */}
                <div className="grid grid-cols-2 gap-4">
                  <DecisionsFeed decisions={data.decisions} />
                  <SchedulePanel items={data.action_items} />
                </div>
              </>
            )}
          </div>
        </div>

        {/* CopilotKit AG-UI Sidebar */}
        <div className="w-80 border-l border-gray-200 bg-white flex-shrink-0">
          <WorkBrainSidebar dashboardData={data} onRefresh={refetch} />
        </div>
      </div>
    </div>
  );
}
