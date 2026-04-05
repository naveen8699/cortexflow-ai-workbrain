import type { Metadata } from 'next';
import './globals.css';
import { WorkBrainProvider } from '@/components/copilot/CopilotProvider';

export const metadata: Metadata = {
  title: 'WorkBrain — AI Personal Operating System',
  description: 'Turn meetings into executed action plans with AI agents',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <WorkBrainProvider>
          {children}
        </WorkBrainProvider>
      </body>
    </html>
  );
}
