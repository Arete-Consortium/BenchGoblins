'use client';

import { useEffect } from 'react';
import api from '@/lib/api';
import { UpgradePrompt, useUpgradePrompt } from '@/components/UpgradePrompt';

export function ProGateProvider({ children }: { children: React.ReactNode }) {
  const { isOpen, setIsOpen, showUpgradePrompt } = useUpgradePrompt();

  useEffect(() => {
    api.setOnProGateError(showUpgradePrompt);
    return () => api.setOnProGateError(() => {});
  }, [showUpgradePrompt]);

  return (
    <>
      {children}
      <UpgradePrompt open={isOpen} onOpenChange={setIsOpen} />
    </>
  );
}
