import { Calendar } from 'lucide-react';
import type { ActionItem } from '@/types';
import { formatDate, getPriorityColor } from '@/lib/utils';

interface Props { items: ActionItem[]; }

export function SchedulePanel({ items }: Props) {
  const scheduled = items.filter(i => i.status === 'scheduled' || i.calendar_event_id);
  const byDeadline = [...scheduled].sort((a, b) => {
    if (!a.deadline) return 1;
    if (!b.deadline) return -1;
    return new Date(a.deadline).getTime() - new Date(b.deadline).getTime();
  });

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Calendar className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">Scheduled Work</h3>
        <span className="ml-auto text-xs text-gray-400">{scheduled.length} items</span>
      </div>
      {byDeadline.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-4">No scheduled items yet.</p>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {byDeadline.map((item) => (
            <div key={item.id} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-gray-50">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{item.title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-gray-500">{item.owner}</span>
                  {item.deadline && (
                    <span className="text-xs text-blue-600 font-medium">{formatDate(item.deadline)}</span>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${getPriorityColor(item.priority)}`}>
                  P{item.priority}
                </span>
                {item.calendar_event_id && (
                  <span className="text-xs text-green-600">📅 Scheduled</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
