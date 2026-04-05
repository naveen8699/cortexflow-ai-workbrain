import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { formatDistanceToNow, format } from 'date-fns';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatRelative(dateStr: string): string {
  try { return formatDistanceToNow(new Date(dateStr), { addSuffix: true }); }
  catch { return dateStr; }
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try { return format(new Date(dateStr), 'MMM d, yyyy'); }
  catch { return dateStr; }
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try { return format(new Date(dateStr), 'MMM d, h:mm a'); }
  catch { return dateStr; }
}

export function getLoadColor(pct: number): string {
  if (pct >= 100) return 'text-red-600';
  if (pct >= 85) return 'text-orange-500';
  if (pct >= 70) return 'text-yellow-500';
  return 'text-green-600';
}

export function getLoadBgColor(pct: number): string {
  if (pct >= 100) return 'bg-red-500';
  if (pct >= 85) return 'bg-orange-500';
  if (pct >= 70) return 'bg-yellow-500';
  return 'bg-green-500';
}

export function getPriorityLabel(p: number): string {
  return ['', 'Low', 'Low-Med', 'Medium', 'High', 'Critical'][p] || 'Medium';
}

export function getPriorityColor(p: number): string {
  if (p >= 5) return 'bg-red-100 text-red-700';
  if (p >= 4) return 'bg-orange-100 text-orange-700';
  if (p >= 3) return 'bg-yellow-100 text-yellow-700';
  return 'bg-gray-100 text-gray-600';
}

export function getAgentColor(agent: string): string {
  const map: Record<string, string> = {
    transcript: 'bg-blue-100 text-blue-700',
    cognitive: 'bg-red-100 text-red-700',
    scheduler: 'bg-green-100 text-green-700',
    execution: 'bg-amber-100 text-amber-700',
    orchestrator: 'bg-purple-100 text-purple-700',
  };
  return map[agent] || 'bg-gray-100 text-gray-600';
}

export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    processed: 'bg-green-100 text-green-700',
    processing: 'bg-blue-100 text-blue-700',
    pending: 'bg-gray-100 text-gray-600',
    failed: 'bg-red-100 text-red-700',
    scheduled: 'bg-green-100 text-green-700',
    done: 'bg-gray-100 text-gray-500',
    dropped: 'bg-red-100 text-red-400',
  };
  return map[status] || 'bg-gray-100 text-gray-600';
}
