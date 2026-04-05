'use client';
import { TopNav } from '@/components/layout/TopNav';
import { ProcessMeetingForm } from '@/components/meetings/ProcessMeetingForm';
import { MeetingsList } from '@/components/meetings/MeetingsList';
import { WorkBrainSidebar } from '@/components/copilot/WorkBrainSidebar';
import { useDashboard } from '@/hooks/useDashboard';
import { Loader2 } from 'lucide-react';

export default function MeetingsPage() {
  const { data, loading, refetch } = useDashboard(5000);
  return (
    <div className="min-h-screen bg-gray-50">
      <TopNav />
      <div className="flex h-[calc(100vh-56px)]">
        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-3xl mx-auto space-y-5">
            <h1 className="text-xl font-bold text-gray-900">Meetings</h1>
            <ProcessMeetingForm onComplete={refetch} />
            {loading && !data ? (
              <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
            ) : (
              <MeetingsList meetings={data?.meetings || []} />
            )}
          </div>
        </div>
        <div className="w-80 border-l border-gray-200 bg-white flex-shrink-0">
          <WorkBrainSidebar dashboardData={data} onRefresh={refetch} />
        </div>
      </div>
    </div>
  );
}
