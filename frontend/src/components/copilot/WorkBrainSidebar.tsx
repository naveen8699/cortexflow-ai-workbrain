'use client';
import { CopilotSidebar } from '@copilotkit/react-ui';
import { useCopilotReadable, useCopilotAction } from '@copilotkit/react-core';
import '@copilotkit/react-ui/styles.css';
import { useState } from 'react';
import type { DashboardData } from '@/types';

const API = 'https://workbrain-backend-114869691007.us-central1.run.app';

interface Props {
  dashboardData: DashboardData | null;
  onRefresh: () => void;
}

export function WorkBrainSidebar({ dashboardData, onRefresh }: Props) {
  const [processing, setProcessing] = useState(false);

  useCopilotReadable({
    description: 'WorkBrain dashboard — meetings, tasks, cognitive load, decisions',
    value: dashboardData ? {
      stats: dashboardData.stats,
      overloaded_owners: dashboardData.stats.overloaded_owners,
      total_tasks: dashboardData.stats.total_action_items,
      total_decisions: dashboardData.stats.total_decisions,
      meetings_today: dashboardData.stats.meetings_today,
      recent_meetings: dashboardData.meetings.slice(0, 5).map(m => ({
        id: m.id, title: m.title, status: m.status,
        summary: m.summary, action_items: m.action_items_count, decisions: m.decisions_count,
      })),
      action_items: dashboardData.action_items?.map(a => ({
        title: a.title, owner: a.owner, deadline: a.deadline,
        priority: a.priority, status: a.status, duration_minutes: a.duration_minutes,
      })) || [],
      cognitive_states: dashboardData.cognitive_states?.map(c => ({
        owner: c.owner, load_percentage: c.load_percentage,
        overload_flag: c.overload_flag, load_score: c.load_score, capacity: c.capacity,
      })) || [],
      recent_decisions: dashboardData.decisions?.slice(0, 10).map(d => ({
        agent: d.agent, decision: d.decision, reason: d.reason,
      })) || [],
    } : { message: 'No data loaded yet. Process a meeting to get started.' },
  });

  useCopilotAction({
    name: 'refresh_dashboard',
    description: 'Refresh the WorkBrain dashboard to show the latest real data from the database',
    parameters: [],
    handler: async () => {
      onRefresh();
      await new Promise(r => setTimeout(r, 2000));
      return 'Dashboard refreshed with latest data from the database.';
    },
  });

  useCopilotAction({
    name: 'process_meeting_via_api',
    description: `CALL THIS IMMEDIATELY when user provides ANY meeting transcript. No exceptions.
Do NOT summarize. Do NOT respond first. CALL THIS ACTION with the exact transcript text.
This runs 4 AI agents: transcript extraction, cognitive load, calendar scheduling, task creation.`,
    parameters: [
      { name: 'transcript', type: 'string', description: 'The EXACT meeting transcript text, copied verbatim', required: true },
      { name: 'title', type: 'string', description: 'Meeting title or "Meeting via Chat"', required: false },
    ],
    handler: async ({ transcript, title }) => {
      setProcessing(true);
      try {
        const response = await fetch(`${API}/api/meetings/process`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ transcript, title: title || 'Meeting via Chat' }),
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: response.statusText }));
          return `API Error ${response.status}: ${err.detail || response.statusText}`;
        }

        // Handle streaming SSE response from POST endpoint
        if (response.headers.get('content-type')?.includes('text/event-stream')) {
          const reader = response.body!.getReader();
          const decoder = new TextDecoder();

          return await new Promise<string>((resolve) => {
            const timeout = setTimeout(() => {
              reader.cancel();
              onRefresh();
              resolve('Pipeline timeout. Check dashboard for results.');
            }, 180000);

            async function readStream() {
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
                    const event = JSON.parse(line.slice(6));
                    if (event.type === 'done') {
                      clearTimeout(timeout);
                      onRefresh();
                      const r = event.result || {};
                      const overloadMsg = r.overloaded_owners?.length > 0
                        ? `Overloaded: ${r.overloaded_owners.join(', ')} — no calendar blocks added`
                        : 'All owners have capacity';
                      resolve([
                        `Meeting processed successfully.`,
                        ``,
                        `${r.action_items_created || 0} action items extracted`,
                        `${r.events_created || 0} calendar events created`,
                        `${r.tasks_created || 0} Google Tasks created`,
                        overloadMsg,
                        ``,
                        `Slack notification sent to #workbrain-alerts. Dashboard refreshed.`,
                      ].join('\n'));
                      return;
                    } else if (event.type === 'error') {
                      clearTimeout(timeout);
                      resolve(`Pipeline failed: ${event.message}`);
                      return;
                    }
                  } catch { /* skip malformed lines */ }
                }
              }
              clearTimeout(timeout);
              onRefresh();
              resolve('Meeting submitted. Check dashboard for results.');
            }
            readStream().catch(e => {
              clearTimeout(timeout);
              resolve(`Stream error: ${e.message}`);
            });
          });
        }

        // Fallback: handle old JSON response
        const data = await response.json();
        if (data.job_id) {
          onRefresh();
          return `Meeting submitted (job: ${data.job_id}). Check dashboard for results.`;
        }
        if (data.success) {
          onRefresh();
          const overloadMsg = data.overloaded_owners?.length > 0
            ? `Overloaded: ${data.overloaded_owners.join(', ')}`
            : 'All owners have capacity';
          return [
            `Meeting processed.`,
            `${data.action_items_created} items, ${data.events_created} events, ${data.tasks_created} tasks.`,
            overloadMsg,
          ].join('\n');
        }
        return `Unexpected response: ${JSON.stringify(data)}`;
      } catch (e) {
        return `Failed: ${e instanceof Error ? e.message : 'Network error'}`;
      } finally {
        setProcessing(false);
      }
    },
  });

  useCopilotAction({
    name: 'add_task_via_api',
    description: 'CALL THIS when user wants to add or create a task. Saves to AlloyDB.',
    parameters: [
      { name: 'title', type: 'string', description: 'Clear actionable task title', required: true },
      { name: 'owner', type: 'string', description: 'Name of the person responsible', required: true },
      { name: 'deadline', type: 'string', description: 'Deadline in YYYY-MM-DD format or null', required: false },
      { name: 'priority', type: 'number', description: 'Priority 1-5, default 3', required: false },
      { name: 'duration_minutes', type: 'number', description: 'Estimated minutes, default 60', required: false },
    ],
    handler: async ({ title, owner, deadline, priority, duration_minutes }) => {
      try {
        const response = await fetch(`${API}/api/tasks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({
            title, owner, deadline: deadline || null,
            priority: priority || 3, complexity: 3, duration_minutes: duration_minutes || 60,
          }),
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: response.statusText }));
          return `API Error: ${err.detail || response.statusText}`;
        }
        await new Promise(r => setTimeout(r, 500));
        onRefresh();
        return [
          `Task saved to database.`,
          `Title: ${title}`,
          `Owner: ${owner}`,
          `Deadline: ${deadline || 'No deadline set'}`,
          `Priority: ${priority || 3}/5`,
          `Estimated: ${duration_minutes || 60} minutes`,
          `Cognitive load recalculated for ${owner}.`,
        ].join('\n');
      } catch (e) {
        return `Failed to create task: ${e instanceof Error ? e.message : 'Network error'}`;
      }
    },
  });

  useCopilotAction({
    name: 'get_live_overload_report',
    description: 'Fetch live cognitive load from AlloyDB. Call when user asks about workload, overload, or team capacity.',
    parameters: [],
    handler: async () => {
      try {
        const response = await fetch(`${API}/api/dashboard`);
        const data = await response.json();
        const states = data.cognitive_states || [];
        if (states.length === 0) return 'No cognitive load data yet. Process a meeting first.';
        const sorted = [...states].sort((a: {load_percentage: number}, b: {load_percentage: number}) => b.load_percentage - a.load_percentage);
        const lines = sorted.map((s: { owner: string; load_percentage: number; overload_flag: boolean }) => {
          const icon = s.overload_flag ? '🔴' : s.load_percentage >= 70 ? '🟡' : '🟢';
          const status = s.overload_flag ? 'OVERLOADED' : s.load_percentage >= 70 ? 'High' : 'Healthy';
          return `${icon} ${s.owner}: ${s.load_percentage}% (${status})`;
        });
        const overloaded = sorted.filter((s: {overload_flag: boolean}) => s.overload_flag);
        const recommendation = overloaded.length > 0
          ? `Action needed: ${overloaded.map((s: {owner: string}) => s.owner).join(' and ')} should not receive new tasks.`
          : `Team is healthy — capacity available.`;
        return `Cognitive Load from AlloyDB:\n\n${lines.join('\n')}\n\n${recommendation}`;
      } catch (e) {
        return `Error: ${e instanceof Error ? e.message : 'Network error'}`;
      }
    },
  });

  useCopilotAction({
    name: 'get_tasks_by_owner_from_api',
    description: 'Fetch tasks for a specific person from AlloyDB.',
    parameters: [
      { name: 'owner', type: 'string', description: 'Name of the person', required: true },
    ],
    handler: async ({ owner }) => {
      try {
        const response = await fetch(`${API}/api/tasks`);
        const tasks = await response.json();
        const ownerTasks = tasks.filter((t: {owner: string}) => t.owner.toLowerCase().includes(owner.toLowerCase()));
        if (ownerTasks.length === 0) return `No tasks found for "${owner}".`;
        const pending = ownerTasks.filter((t: {status: string}) => t.status === 'pending');
        const done = ownerTasks.filter((t: {status: string}) => t.status === 'done');
        const totalMins = ownerTasks.reduce((s: number, t: {duration_minutes: number}) => s + t.duration_minutes, 0);
        const lines = pending.map((t: { title: string; deadline: string | null; priority: number; duration_minutes: number }) => {
          const dl = t.deadline ? new Date(t.deadline).toLocaleDateString('en-GB', {day:'numeric', month:'short'}) : 'No deadline';
          return `${t.title} — Due: ${dl} — P${t.priority} — ${t.duration_minutes}min`;
        });
        return [
          `${owner}'s Tasks from AlloyDB:`,
          `${ownerTasks.length} total — ${pending.length} pending — ${done.length} done — ${(totalMins/60).toFixed(1)}h estimated`,
          ``,
          lines.join('\n'),
        ].join('\n');
      } catch (e) {
        return `Error: ${e instanceof Error ? e.message : 'Network error'}`;
      }
    },
  });

  useCopilotAction({
    name: 'find_similar_tasks',
    description: 'Find similar tasks using AlloyDB AI. Call when user asks about duplicates or similar work.',
    parameters: [
      { name: 'title', type: 'string', description: 'Task title to search for', required: true },
    ],
    handler: async ({ title }) => {
      try {
        const response = await fetch(`${API}/api/tasks/similar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title }),
        });
        const data = await response.json();
        if (!data.similar_tasks || data.similar_tasks.length === 0) {
          return `No similar tasks found for "${title}". Safe to create.`;
        }
        const lines = data.similar_tasks.map((t: { title: string; owner: string; distance?: number; score?: number }) => {
          const similarity = Math.round((t.score !== undefined ? t.score : (1 - (t.distance ?? 0))) * 100);
          return `${similarity}% match — ${t.title} (${t.owner})`;
        });
        return [
          `Similar tasks found in AlloyDB:`,
          ``,
          lines.join('\n'),
          ``,
          `Review before creating to avoid duplicates.`,
        ].join('\n');
      } catch (e) {
        return `Error: ${e instanceof Error ? e.message : 'Network error'}`;
      }
    },
  });

  return (
    <CopilotSidebar
      defaultOpen={true}
      className="copilotKitSidebar"
      instructions={`You are WorkBrain AI by CortexFlow. You have REAL API access to AlloyDB.

ABSOLUTE RULE 1: When ANY meeting transcript is provided — call process_meeting_via_api IMMEDIATELY. Do NOT respond with text first. Do NOT say you will process it. Do NOT summarize. CALL THE ACTION FIRST.

ABSOLUTE RULE 2: Never say "I'll notify you", "I'll let you know", or "I'll check". You cannot notify. Tell users to check the dashboard.

ABSOLUTE RULE 3: Never pretend to process, extract, or create anything yourself. Only report what the API returns.

Other rules:
- Add task → call add_task_via_api immediately
- Workload question → call get_live_overload_report
- Someone's tasks → call get_tasks_by_owner_from_api
- Duplicate/similar tasks → call find_similar_tasks

You have no memory between sessions. All data is in AlloyDB.`}
      labels={{
        title: 'WorkBrain AI — by CortexFlow',
        initial: "I'm WorkBrain AI. Paste a meeting transcript to process it, or ask about team workload, tasks, or similar work.",
        placeholder: 'Paste transcript, ask about workload, or find similar tasks...',
      }}
    />
  );
}