'use client';
import { useState } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';

interface Props { onComplete: () => void; }

export function AddTaskForm({ onComplete }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: '', owner: 'demo_user', duration_minutes: 60,
    priority: 3, complexity: 3, deadline: '',
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await api.addTask({
        ...form,
        deadline: form.deadline || undefined,
      });
      setForm({ title: '', owner: 'demo_user', duration_minutes: 60, priority: 3, complexity: 3, deadline: '' });
      setOpen(false);
      onComplete();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to add task');
    } finally {
      setLoading(false);
    }
  }

  if (!open) return (
    <button onClick={() => setOpen(true)}
      className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
      <Plus className="w-4 h-4" /> Add Task
    </button>
  );

  return (
    <div className="bg-white rounded-xl border border-blue-200 p-5">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">Add Task Manually</h3>
      <form onSubmit={handleSubmit} className="space-y-3">
        <input required value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
          placeholder="Task title *" className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
        <div className="grid grid-cols-2 gap-3">
          <input value={form.owner} onChange={e => setForm(p => ({ ...p, owner: e.target.value }))}
            placeholder="Owner" className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <input type="number" value={form.duration_minutes} min={5} max={480}
            onChange={e => setForm(p => ({ ...p, duration_minutes: +e.target.value }))}
            placeholder="Duration (min)" className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Priority (1-5)</label>
            <select value={form.priority} onChange={e => setForm(p => ({ ...p, priority: +e.target.value }))}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
              {[1,2,3,4,5].map(n => <option key={n} value={n}>{n} — {['','Low','Low-Med','Medium','High','Critical'][n]}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Complexity (1-5)</label>
            <select value={form.complexity} onChange={e => setForm(p => ({ ...p, complexity: +e.target.value }))}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
              {[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Deadline</label>
            <input type="date" value={form.deadline} onChange={e => setForm(p => ({ ...p, deadline: e.target.value }))}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>
        <div className="flex gap-2 pt-1">
          <button type="submit" disabled={loading}
            className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-200 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Adding...</> : 'Add + Analyse →'}
          </button>
          <button type="button" onClick={() => setOpen(false)}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
