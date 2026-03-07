'use client';

import { useEffect } from 'react';

function ShibaFace() {
  return (
    <svg width="96" height="96" viewBox="0 0 96 96" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Left ear - outer (black) */}
      <path d="M18 38 L10 8 L32 28 Z" fill="#1a1a1a" />
      {/* Left ear - inner (tan) */}
      <path d="M19 35 L14 14 L30 28 Z" fill="#C4884D" />
      {/* Right ear - outer (black) */}
      <path d="M78 38 L86 8 L64 28 Z" fill="#1a1a1a" />
      {/* Right ear - inner (tan) */}
      <path d="M77 35 L82 14 L66 28 Z" fill="#C4884D" />

      {/* Head shape (tan/sesame) */}
      <ellipse cx="48" cy="52" rx="32" ry="30" fill="#C4884D" />

      {/* Black forehead patch */}
      <path d="M22 42 Q48 20 74 42 Q48 35 22 42" fill="#1a1a1a" opacity="0.7" />

      {/* White face mask (urajiro) */}
      <path d="M48 38 Q28 44 24 58 Q28 76 48 80 Q68 76 72 58 Q68 44 48 38" fill="#F5E6D0" />

      {/* Left eyebrow mark */}
      <ellipse cx="34" cy="42" rx="4" ry="2" fill="#DBA55D" />
      {/* Right eyebrow mark */}
      <ellipse cx="62" cy="42" rx="4" ry="2" fill="#DBA55D" />

      {/* Left eye */}
      <ellipse cx="36" cy="50" rx="4" ry="5" fill="#1a1a1a" />
      <ellipse cx="37.5" cy="48.5" rx="1.5" ry="2" fill="white" opacity="0.8" />
      {/* Right eye */}
      <ellipse cx="60" cy="50" rx="4" ry="5" fill="#1a1a1a" />
      <ellipse cx="61.5" cy="48.5" rx="1.5" ry="2" fill="white" opacity="0.8" />

      {/* Nose */}
      <ellipse cx="48" cy="60" rx="4" ry="3" fill="#1a1a1a" />
      {/* Nose highlight */}
      <ellipse cx="47" cy="59" rx="1.5" ry="1" fill="#333" />

      {/* Mouth */}
      <line x1="48" y1="63" x2="48" y2="66" stroke="#1a1a1a" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M42 66 Q45 70 48 66 Q51 70 54 66" stroke="#1a1a1a" strokeWidth="1.5" fill="none" strokeLinecap="round" />

      {/* Cheek fluff */}
      <ellipse cx="24" cy="56" rx="5" ry="4" fill="#DBA55D" opacity="0.6" />
      <ellipse cx="72" cy="56" rx="5" ry="4" fill="#DBA55D" opacity="0.6" />
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
