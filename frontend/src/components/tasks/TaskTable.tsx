import { CheckSquare, Calendar, Clock } from 'lucide-react';
import type { ActionItem } from '@/types';
import { getPriorityColor, getPriorityLabel, getStatusColor, formatDate } from '@/lib/utils';

interface Props { items: ActionItem[]; }

export function TaskTable({ items }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
        <CheckSquare className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">Action Items</h3>
        <span className="ml-auto text-xs text-gray-400">{items.length} total</span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">No tasks yet. Process a meeting to create action items.</p>
      ) : (
        <div className="divide-y divide-gray-50">
          {items.map(item => (
            <div key={item.id} className="px-5 py-3.5 hover:bg-gray-50 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{item.title}</p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-gray-500">{item.owner}</span>
                  <span className="text-xs text-gray-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" />{item.duration_minutes}m
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${getPriorityColor(item.priority)}`}>
                  {getPriorityLabel(item.priority)}
                </span>
                {item.deadline && (
                  <span className="text-xs text-blue-600 flex items-center gap-1">
                    <Calendar className="w-3 h-3" />{formatDate(item.deadline)}
                  </span>
                )}
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${getStatusColor(item.status)}`}>
                  {item.status}
                </span>
                {item.calendar_event_id && <span className="text-xs" title="Calendar event created">📅</span>}
                {item.task_id && <span className="text-xs" title="Task card created">✅</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
