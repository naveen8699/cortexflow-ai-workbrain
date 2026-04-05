'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Brain, LayoutDashboard, Users, CheckSquare, FileText, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';

const NAV = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/meetings', label: 'Meetings', icon: Users },
  { href: '/tasks', label: 'Tasks', icon: CheckSquare },
  { href: '/decisions', label: 'Decisions', icon: FileText },
];

export function TopNav() {
  const path = usePathname();
  return (
    <nav className="bg-white border-b border-gray-200 px-6 h-14 flex items-center justify-between sticky top-0 z-40">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
          <Brain className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold text-gray-900 text-sm">WorkBrain</span>
        <span className="ml-2 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
          ADK · Vertex AI
        </span>
      </div>
      <div className="flex items-center gap-1">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
              path.startsWith(href)
                ? 'bg-blue-50 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
            )}>
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Zap className="w-3.5 h-3.5 text-green-500" />
          demo_user
        </div>
      </div>
    </nav>
  );
}
