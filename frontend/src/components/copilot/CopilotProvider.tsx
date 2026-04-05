'use client';
import { CopilotKit } from '@copilotkit/react-core';

const COPILOTKIT_URL = process.env.NEXT_PUBLIC_COPILOTKIT_URL || 'http://localhost:8080/api/copilotkit';

export function WorkBrainProvider({ children }: { children: React.ReactNode }) {
  return (
    <CopilotKit runtimeUrl={COPILOTKIT_URL} agent="workbrain">
      {children}
    </CopilotKit>
  );
}
