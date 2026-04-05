import type { Metadata } from 'next';
import './globals.css';
import { WorkBrainProvider } from '@/components/copilot/CopilotProvider';

export const metadata: Metadata = {
  title: 'WorkBrain by CortexFlow',
  description: 'CortexFlow presents WorkBrain — AI-powered meeting execution engine',
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
