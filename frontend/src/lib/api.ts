import type { DashboardData, ProcessMeetingResponse, AddTaskRequest, Meeting, ActionItem, DecisionLog } from '@/types';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  getDashboard: () => request<DashboardData>('/api/dashboard'),
  getMeetings: () => request<Meeting[]>('/api/meetings'),
  getMeetingDecisions: (id: string) => request<DecisionLog[]>(`/api/meetings/${id}/decisions`),
  getTasks: () => request<ActionItem[]>('/api/tasks'),
  getDecisions: (limit = 30) => request<DecisionLog[]>(`/api/decisions?limit=${limit}`),

  processMeeting: (transcript: string, title?: string) =>
    request<ProcessMeetingResponse>('/api/meetings/process', {
      method: 'POST',
      body: JSON.stringify({ transcript, title }),
    }),

  addTask: (data: AddTaskRequest) =>
    request('/api/tasks', { method: 'POST', body: JSON.stringify(data) }),

  health: () => request<{ status: string; db: string }>('/health'),
};
