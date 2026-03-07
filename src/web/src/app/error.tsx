'use client';

import { useEffect } from 'react';

function ShibaFace() {
  return (
    <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Face */}
      <ellipse cx="40" cy="45" rx="28" ry="25" fill="#D4A054" />
      {/* Inner face (tan) */}
      <ellipse cx="40" cy="50" rx="20" ry="18" fill="#F5DEB3" />
      {/* Left ear */}
      <polygon points="14,30 8,5 28,22" fill="#2C1A0E" />
      <polygon points="16,28 12,10 26,23" fill="#D4A054" />
      {/* Right ear */}
      <polygon points="66,30 72,5 52,22" fill="#2C1A0E" />
      <polygon points="64,28 68,10 54,23" fill="#D4A054" />
      {/* Left eye */}
      <ellipse cx="30" cy="42" rx="4" ry="4.5" fill="#2C1A0E" />
      <ellipse cx="31" cy="41" rx="1.5" ry="1.5" fill="white" />
      {/* Right eye */}
      <ellipse cx="50" cy="42" rx="4" ry="4.5" fill="#2C1A0E" />
      <ellipse cx="51" cy="41" rx="1.5" ry="1.5" fill="white" />
      {/* Nose */}
      <ellipse cx="40" cy="52" rx="3.5" ry="2.5" fill="#2C1A0E" />
      {/* Mouth */}
      <path d="M36 56 Q40 60 44 56" stroke="#2C1A0E" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      {/* Cheek marks */}
      <ellipse cx="22" cy="50" rx="4" ry="2.5" fill="#E8A0A0" opacity="0.5" />
      <ellipse cx="58" cy="50" rx="4" ry="2.5" fill="#E8A0A0" opacity="0.5" />
    </svg>
  );
}

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
        <div className="flex justify-center mb-4">
          <ShibaFace />
        </div>
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
