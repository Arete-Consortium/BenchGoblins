import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Settings',
  description:
    'Customize your Bench Goblins experience. Set default sport, risk mode, appearance, and notification preferences.',
};

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
