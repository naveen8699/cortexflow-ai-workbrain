import { Calendar, CheckSquare, Brain, Zap } from 'lucide-react';
import type { DashboardStats } from '@/types';
import { getLoadColor } from '@/lib/utils';

interface Props { stats: DashboardStats; }

export function StatCards({ stats }: Props) {
  const cards = [
    { label: 'Meetings today', value: stats.meetings_today, icon: Calendar, color: 'text-blue-600', bg: 'bg-blue-50' },
    { label: 'Action items', value: stats.total_action_items, icon: CheckSquare, color: 'text-green-600', bg: 'bg-green-50' },
    {
      label: 'Your load',
      value: `${stats.user_load_percentage.toFixed(0)}%`,
      icon: Brain,
      color: getLoadColor(stats.user_load_percentage),
      bg: stats.user_load_percentage >= 85 ? 'bg-red-50' : stats.user_load_percentage >= 70 ? 'bg-amber-50' : 'bg-green-50',
    },
    { label: 'AI decisions', value: stats.total_decisions, icon: Zap, color: 'text-purple-600', bg: 'bg-purple-50' },
  ];

  return (
    <div className="grid grid-cols-4 gap-4">
      {cards.map(({ label, value, icon: Icon, color, bg }) => (
        <div key={label} className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
            <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
              <Icon className={`w-4 h-4 ${color}`} />
            </div>
          </div>
          <div className={`text-2xl font-bold ${color}`}>{value}</div>
        </div>
      ))}
    </div>
  );
}
