'use client';
import { CopilotSidebar } from '@copilotkit/react-ui';
import { useCopilotReadable, useCopilotAction } from '@copilotkit/react-core';
import '@copilotkit/react-ui/styles.css';
import type { DashboardData } from '@/types';

interface Props {
  dashboardData: DashboardData | null;
  onRefresh: () => void;
}

export function WorkBrainSidebar({ dashboardData, onRefresh }: Props) {
  useCopilotReadable({
    description: 'Current WorkBrain dashboard state — meetings, tasks, cognitive load',
    value: dashboardData ? {
      stats: dashboardData.stats,
      overloaded_owners: dashboardData.stats.overloaded_owners,
      total_tasks: dashboardData.stats.total_action_items,
      user_load: dashboardData.stats.user_load_percentage,
      recent_meetings: dashboardData.meetings.slice(0, 3).map(m => ({
        title: m.title, status: m.status, items: m.action_items_count,
      })),
    } : null,
  });

  useCopilotAction({
    name: 'refresh_dashboard',
    description: 'Refresh the dashboard to show latest data',
    parameters: [],
    handler: async () => { onRefresh(); return 'Dashboard refreshed.'; },
  });

  return (
    <CopilotSidebar
      defaultOpen={true}
      className="copilotKitSidebar"
      instructions={`You are WorkBrain AI, an autonomous productivity assistant.
You help users process meetings, manage cognitive load, and understand AI decisions.
Reference the dashboard state provided. Be concise and specific.
For meeting processing, guide users to use the Process Meeting panel.`}
      labels={{
        title: 'WorkBrain AI — by CortexFlow',
        initial: "I'm WorkBrain AI by CortexFlow. Paste a meeting transcript or ask about your workload.",
        placeholder: 'Ask about your workload or decisions...',
      }}
    />
  );
}
