'use client';

import { useEffect } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function AskError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Ask page error:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-950 px-4">
      <div className="max-w-md text-center">
        <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mx-auto mb-6">
          <AlertCircle className="w-8 h-8 text-red-400" />
        </div>

        <h2 className="text-xl font-semibold mb-2">Something went wrong</h2>
        <p className="text-dark-400 mb-6">
          An error occurred while loading the chat. This is usually temporary.
        </p>

        <Button onClick={reset} className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Try again
        </Button>
      </div>
    </div>
  );
}
