import type { Metadata } from 'next';
import { EmailCapture } from '@/components/EmailCapture';

export const metadata: Metadata = {
  title: 'Subscribe - Bench Goblins',
  description:
    'Get weekly fantasy sports insights, scoring updates, and NFL Draft prep from Bench Goblins — straight to your inbox.',
};

export default function SubscribePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950 flex items-center justify-center px-4">
      <EmailCapture variant="full" referrer="subscribe-page" />
    </div>
  );
}
