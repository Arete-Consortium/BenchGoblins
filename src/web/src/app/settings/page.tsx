'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Header } from '@/components/layout/Header';
import { SportSelector } from '@/components/SportSelector';
import { RiskModeSelector } from '@/components/RiskModeSelector';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';
import {
  Bell,
  Shield,
  CreditCard,
  ExternalLink,
  Trash2,
  Moon,
  Sun,
} from 'lucide-react';

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
      <h2 className="text-lg font-semibold mb-1">{title}</h2>
      {description && <p className="text-dark-400 text-sm mb-4">{description}</p>}
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { sport, riskMode, setSport, setRiskMode, clearMessages } = useAppStore();
  const darkMode = theme === 'dark';
  const [notifications, setNotifications] = useState(true);

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-2xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold">Settings</h1>
            <p className="text-dark-400 mt-1">Customize your BenchGoblin experience</p>
          </div>

          <div className="space-y-6">
            {/* Default Preferences */}
            <SettingsSection
              title="Default Preferences"
              description="Set your default sport and risk mode for new sessions"
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-dark-400 mb-2">Default Sport</label>
                  <SportSelector value={sport} onChange={setSport} />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-2">Default Risk Mode</label>
                  <RiskModeSelector value={riskMode} onChange={setRiskMode} />
                </div>
              </div>
            </SettingsSection>

            {/* Appearance */}
            <SettingsSection title="Appearance">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {darkMode ? (
                    <Moon className="w-5 h-5 text-dark-400" />
                  ) : (
                    <Sun className="w-5 h-5 text-yellow-400" />
                  )}
                  <div>
                    <div className="font-medium">Dark Mode</div>
                    <div className="text-sm text-dark-400">Use dark theme</div>
                  </div>
                </div>
                <button
                  onClick={() => setTheme(darkMode ? 'light' : 'dark')}
                  className={cn(
                    'w-12 h-7 rounded-full transition-all relative',
                    darkMode ? 'bg-primary-600' : 'bg-dark-600'
                  )}
                >
                  <div
                    className={cn(
                      'absolute w-5 h-5 rounded-full bg-white top-1 transition-all',
                      darkMode ? 'left-6' : 'left-1'
                    )}
                  />
                </button>
              </div>
            </SettingsSection>

            {/* Notifications */}
            <SettingsSection title="Notifications">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Bell className="w-5 h-5 text-dark-400" />
                  <div>
                    <div className="font-medium">Push Notifications</div>
                    <div className="text-sm text-dark-400">
                      Get notified about injury updates and lineup locks
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => setNotifications(!notifications)}
                  className={cn(
                    'w-12 h-7 rounded-full transition-all relative',
                    notifications ? 'bg-primary-600' : 'bg-dark-600'
                  )}
                >
                  <div
                    className={cn(
                      'absolute w-5 h-5 rounded-full bg-white top-1 transition-all',
                      notifications ? 'left-6' : 'left-1'
                    )}
                  />
                </button>
              </div>
            </SettingsSection>

            {/* Subscription */}
            <SettingsSection title="Subscription">
              <div className="flex items-center justify-between p-4 bg-dark-700/50 rounded-lg mb-4">
                <div>
                  <div className="font-medium">Free Tier</div>
                  <div className="text-sm text-dark-400">5 queries per day, all sports</div>
                </div>
                <span className="px-3 py-1 rounded-full bg-dark-600 text-dark-300 text-sm">
                  Current Plan
                </span>
              </div>
              <button
                onClick={() => router.push('/billing')}
                className="w-full py-3 rounded-lg bg-primary-600 text-white font-medium hover:bg-primary-500 transition-all flex items-center justify-center gap-2"
              >
                <CreditCard className="w-5 h-5" />
                Upgrade to Pro
              </button>
            </SettingsSection>

            {/* Data & Privacy */}
            <SettingsSection title="Data & Privacy">
              <div className="space-y-4">
                <button
                  onClick={() => {
                    if (confirm('Are you sure you want to clear all messages?')) {
                      clearMessages();
                    }
                  }}
                  className="flex items-center gap-3 text-dark-300 hover:text-red-400 transition-all"
                >
                  <Trash2 className="w-5 h-5" />
                  Clear Conversation History
                </button>
                <a
                  href="/privacy"
                  className="flex items-center gap-3 text-dark-300 hover:text-dark-100 transition-all"
                >
                  <Shield className="w-5 h-5" />
                  Privacy Policy
                  <ExternalLink className="w-4 h-4" />
                </a>
                <a
                  href="/terms"
                  className="flex items-center gap-3 text-dark-300 hover:text-dark-100 transition-all"
                >
                  <Shield className="w-5 h-5" />
                  Terms of Service
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
            </SettingsSection>

            {/* About */}
            <SettingsSection title="About">
              <div className="text-sm text-dark-400 space-y-1">
                <p>BenchGoblin v1.0.0</p>
                <p>Fantasy Sports Decision Engine</p>
                <p className="pt-2">
                  Built with the five-index scoring system for smarter fantasy decisions.
                </p>
              </div>
            </SettingsSection>
          </div>
        </div>
      </main>
    </div>
  );
}
