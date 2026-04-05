'use client';
import { TopNav } from '@/components/layout/TopNav';
import { DecisionsTable } from '@/components/decisions/DecisionsTable';
import { WorkBrainSidebar } from '@/components/copilot/WorkBrainSidebar';
import { useDashboard } from '@/hooks/useDashboard';
import { Loader2 } from 'lucide-react';

export default function DecisionsPage() {
  const { data, loading, refetch } = useDashboard(5000);
  return (
    <div className="min-h-screen bg-gray-50">
      <TopNav />
      <div className="flex h-[calc(100vh-56px)]">
        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-4xl mx-auto space-y-5">
            <div>
              <h1 className="text-xl font-bold text-gray-900">AI Decisions Log</h1>
              <p className="text-sm text-gray-500 mt-0.5">Every decision made by your AI agents — with full reasoning</p>
            </div>
            {loading && !data
              ? <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
              : <DecisionsTable decisions={data?.decisions || []} />
            }
          </div>
        </div>
        <div className="w-80 border-l border-gray-200 bg-white flex-shrink-0">
          <WorkBrainSidebar dashboardData={data} onRefresh={refetch} />
        </div>
      </div>
    </div>
  );
}
