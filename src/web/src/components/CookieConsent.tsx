'use client';

import { useState } from 'react';
import { X } from 'lucide-react';

const CONSENT_KEY = 'benchgoblin_cookie_consent';

function getInitialVisibility(): boolean {
  if (typeof window === 'undefined') return false;
  return !localStorage.getItem(CONSENT_KEY);
}

export default function CookieConsent() {
  const [visible, setVisible] = useState(getInitialVisibility);

  const handleAccept = () => {
    localStorage.setItem(CONSENT_KEY, 'accepted');
    setVisible(false);

    // Update GA4 consent mode
    if (typeof window.gtag === 'function') {
      window.gtag('consent', 'update', {
        analytics_storage: 'granted',
      });
    }
  };

  const handleDecline = () => {
    localStorage.setItem(CONSENT_KEY, 'declined');
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 p-4">
      <div className="max-w-2xl mx-auto bg-dark-800 border border-dark-600 rounded-lg shadow-xl p-4 flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <p className="text-sm text-dark-300 flex-1">
          We use cookies for analytics to improve your experience.
          See our{' '}
          <a href="/privacy" className="text-primary-400 hover:underline">
            Privacy Policy
          </a>.
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleDecline}
            className="px-3 py-1.5 text-sm text-dark-400 hover:text-dark-200 transition-colors"
          >
            Decline
          </button>
          <button
            onClick={handleAccept}
            className="px-4 py-1.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-md transition-colors"
          >
            Accept
          </button>
          <button
            onClick={handleDecline}
            className="p-1 text-dark-500 hover:text-dark-300 transition-colors"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
