'use client';
import { CopilotKit } from '@copilotkit/react-core';

export function WorkBrainProvider({ children }: { children: React.ReactNode }) {
  return (
    <CopilotKit 
      publicApiKey="ck_pub_8561ee59de8ef0f9bb5aa3cb78e1d394"
      showDevConsole={false}
    >
      {children}
    </CopilotKit>
  );
}
