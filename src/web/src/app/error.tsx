'use client';

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('App error:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-950 p-4">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-4">👺</div>
        <h2 className="text-2xl font-bold text-dark-100 mb-2">Something went wrong</h2>
        <p className="text-dark-400 mb-6">
          The Goblin tripped over something. Try refreshing or heading back to the app.
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={reset}
            className="px-5 py-2.5 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-400 transition-colors"
          >
            Try Again
          </button>
          <a
            href="/ask"
            className="px-5 py-2.5 bg-dark-800 text-dark-200 rounded-lg font-medium hover:bg-dark-700 transition-colors"
          >
            Go to Ask
          </a>
        </div>
      </div>
    </div>
  );
}
