'use client';

import { useState, useEffect, useCallback } from 'react';
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
  Link2,
  Unlink,
  Loader2,
} from 'lucide-react';
import api from '@/lib/api';
import { useLeagueStore } from '@/stores/leagueStore';
import { useAuthStore } from '@/stores/authStore';
import { LeagueConnectDialog } from '@/components/LeagueConnectDialog';

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
  const { connection, selectedLeagueIds, disconnect } = useLeagueStore();
  const { isAuthenticated, user, refreshUser } = useAuthStore();
  const darkMode = theme === 'dark';
  const [leagueDialogOpen, setLeagueDialogOpen] = useState(false);

  // Billing status — primary source is user object from auth store,
  // enriched with renewal details from /billing/status
  const billingTier = user?.subscription_tier ?? 'free';
  const [renewalDate, setRenewalDate] = useState<string | null>(null);
  const [cancelAtPeriodEnd, setCancelAtPeriodEnd] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  // Refresh user data on mount to pick up subscription changes
  useEffect(() => {
    if (isAuthenticated) {
      refreshUser();
    }
  }, [isAuthenticated, refreshUser]);

  useEffect(() => {
    if (!isAuthenticated || billingTier !== 'pro') return;
    // Only fetch extra details (renewal date, cancel status) for Pro users
    api.getBillingStatus()
      .then((data) => {
        if (data.current_period_end) {
          setRenewalDate(new Date(data.current_period_end).toLocaleDateString());
        }
        setCancelAtPeriodEnd(data.cancel_at_period_end ?? false);
      })
      .catch(() => { /* billing endpoint may not be configured */ });
  }, [isAuthenticated, billingTier]);

  const handleManageSubscription = async () => {
    setPortalLoading(true);
    try {
      const { portal_url } = await api.createPortalSession();
      window.location.href = portal_url;
    } catch {
      setPortalLoading(false);
    }
  };

  // Notification preferences
  const [notifPrefs, setNotifPrefs] = useState({
    injury_alerts: true,
    lineup_reminders: true,
    decision_updates: false,
    trending_players: false,
  });
  const [notifTokenCount, setNotifTokenCount] = useState(0);
  const [notifSaving, setNotifSaving] = useState(false);

  // ESPN connection status
  const [espnStatus, setEspnStatus] = useState<{
    connected: boolean;
    espn_league_id: string | null;
    sport: string | null;
    roster_player_count: number;
  } | null>(null);
  const [espnLoading, setEspnLoading] = useState(false);

  const fetchEspnStatus = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const data = await api.getMyESPN();
      setEspnStatus(data);
    } catch {
      // Silently ignore — user may not have ESPN
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchEspnStatus();
  }, [fetchEspnStatus]);

  const handleDisconnectESPN = async () => {
    if (!confirm('Disconnect your ESPN league? You can reconnect anytime.')) return;
    setEspnLoading(true);
    try {
      await api.disconnectESPN();
      setEspnStatus({ connected: false, espn_league_id: null, sport: null, roster_player_count: 0 });
    } catch {
      // ignore
    } finally {
      setEspnLoading(false);
    }
  };

  // Yahoo connection status
  const [yahooStatus, setYahooStatus] = useState<{
    connected: boolean;
    yahoo_league_key: string | null;
    sport: string | null;
    roster_player_count: number;
  } | null>(null);
  const [yahooLoading, setYahooLoading] = useState(false);

  const fetchYahooStatus = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const data = await api.getMyYahoo();
      setYahooStatus(data);
    } catch {
      // Silently ignore
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchYahooStatus();
  }, [fetchYahooStatus]);

  const handleDisconnectYahoo = async () => {
    if (!confirm('Disconnect your Yahoo league? You can reconnect anytime.')) return;
    setYahooLoading(true);
    try {
      await api.disconnectYahoo();
      setYahooStatus({ connected: false, yahoo_league_key: null, sport: null, roster_player_count: 0 });
    } catch {
      // ignore
    } finally {
      setYahooLoading(false);
    }
  };

  // Fetch notification preferences
  const fetchNotifPrefs = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const data = await api.getNotificationPreferences();
      setNotifPrefs(data.preferences);
      setNotifTokenCount(data.token_count);
    } catch {
      // Silently ignore
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchNotifPrefs();
  }, [fetchNotifPrefs]);

  const handleToggleNotifPref = async (key: keyof typeof notifPrefs) => {
    const updated = { ...notifPrefs, [key]: !notifPrefs[key] };
    setNotifPrefs(updated);
    setNotifSaving(true);
    try {
      await api.updateNotificationPreferences(updated);
    } catch {
      // Revert on failure
      setNotifPrefs(notifPrefs);
    } finally {
      setNotifSaving(false);
    }
  };

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

            {/* Connected Leagues */}
            {isAuthenticated && (
              <SettingsSection
                title="Connected Leagues"
                description="Fantasy platforms synced to your profile for personalized recommendations"
              >
                <div className="space-y-4">
                  {/* Sleeper Connection */}
                  <div>
                    <h3 className="text-sm font-medium text-dark-300 mb-2">Sleeper</h3>
                    {connection && selectedLeagueIds[sport] ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-3 p-3 bg-dark-700/50 rounded-lg">
                          <Link2 className="w-4 h-4 text-primary-400 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">{connection.sleeperUsername}</div>
                            <div className="text-xs text-dark-400 truncate">
                              League: {selectedLeagueIds[sport]}
                            </div>
                          </div>
                          <span className="px-2 py-0.5 rounded-full bg-primary-600/20 text-primary-400 text-xs">
                            Connected
                          </span>
                        </div>
                        <button
                          onClick={() => {
                            if (confirm('Disconnect your Sleeper league? You can reconnect anytime.')) {
                              disconnect();
                            }
                          }}
                          className="flex items-center gap-2 text-xs text-dark-400 hover:text-red-400 transition-all"
                        >
                          <Unlink className="w-3.5 h-3.5" />
                          Disconnect
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setLeagueDialogOpen(true)}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-dark-700/50 border border-dark-700 text-sm text-dark-300 hover:border-primary-600 hover:text-primary-400 transition-all w-full"
                      >
                        <Link2 className="w-4 h-4" />
                        Connect Sleeper
                      </button>
                    )}
                  </div>

                  {/* ESPN Connection */}
                  <div>
                    <h3 className="text-sm font-medium text-dark-300 mb-2">ESPN Fantasy</h3>
                    {espnStatus?.connected ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-3 p-3 bg-dark-700/50 rounded-lg">
                          <Link2 className="w-4 h-4 text-primary-400 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">ESPN League</div>
                            <div className="text-xs text-dark-400 truncate">
                              {espnStatus.espn_league_id} &middot; {espnStatus.sport?.toUpperCase()} &middot; {espnStatus.roster_player_count} players
                            </div>
                          </div>
                          <span className="px-2 py-0.5 rounded-full bg-primary-600/20 text-primary-400 text-xs">
                            Connected
                          </span>
                        </div>
                        <button
                          onClick={handleDisconnectESPN}
                          disabled={espnLoading}
                          className="flex items-center gap-2 text-xs text-dark-400 hover:text-red-400 transition-all"
                        >
                          {espnLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unlink className="w-3.5 h-3.5" />}
                          Disconnect
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setLeagueDialogOpen(true)}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-dark-700/50 border border-dark-700 text-sm text-dark-300 hover:border-primary-600 hover:text-primary-400 transition-all w-full"
                      >
                        <Link2 className="w-4 h-4" />
                        Connect ESPN
                      </button>
                    )}
                  </div>

                  {/* Yahoo Connection */}
                  <div>
                    <h3 className="text-sm font-medium text-dark-300 mb-2">Yahoo Fantasy</h3>
                    {yahooStatus?.connected ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-3 p-3 bg-dark-700/50 rounded-lg">
                          <Link2 className="w-4 h-4 text-primary-400 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">Yahoo League</div>
                            <div className="text-xs text-dark-400 truncate">
                              {yahooStatus.yahoo_league_key} &middot; {yahooStatus.sport?.toUpperCase()} &middot; {yahooStatus.roster_player_count} players
                            </div>
                          </div>
                          <span className="px-2 py-0.5 rounded-full bg-primary-600/20 text-primary-400 text-xs">
                            Connected
                          </span>
                        </div>
                        <button
                          onClick={handleDisconnectYahoo}
                          disabled={yahooLoading}
                          className="flex items-center gap-2 text-xs text-dark-400 hover:text-red-400 transition-all"
                        >
                          {yahooLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unlink className="w-3.5 h-3.5" />}
                          Disconnect
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setLeagueDialogOpen(true)}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-dark-700/50 border border-dark-700 text-sm text-dark-300 hover:border-primary-600 hover:text-primary-400 transition-all w-full"
                      >
                        <Link2 className="w-4 h-4" />
                        Connect Yahoo
                      </button>
                    )}
                  </div>
                </div>
              </SettingsSection>
            )}

            <LeagueConnectDialog open={leagueDialogOpen} onOpenChange={setLeagueDialogOpen} />

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
            {isAuthenticated && (
              <SettingsSection
                title="Notifications"
                description={notifTokenCount > 0 ? `${notifTokenCount} device${notifTokenCount !== 1 ? 's' : ''} registered` : 'Register a device to receive push notifications'}
              >
                <div className="space-y-4">
                  {([
                    { key: 'injury_alerts' as const, icon: Bell, label: 'Injury Alerts', desc: 'Get notified when your players\' injury status changes' },
                    { key: 'lineup_reminders' as const, icon: Bell, label: 'Lineup Reminders', desc: 'Reminders before lineup locks' },
                    { key: 'decision_updates' as const, icon: Bell, label: 'Decision Updates', desc: 'Updates on players you\'ve asked about' },
                    { key: 'trending_players' as const, icon: Bell, label: 'Trending Players', desc: 'Alerts for trending waiver wire pickups' },
                  ]).map(({ key, label, desc }) => (
                    <div key={key} className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Bell className="w-5 h-5 text-dark-400" />
                        <div>
                          <div className="font-medium">{label}</div>
                          <div className="text-sm text-dark-400">{desc}</div>
                        </div>
                      </div>
                      <button
                        onClick={() => handleToggleNotifPref(key)}
                        disabled={notifSaving}
                        className={cn(
                          'w-12 h-7 rounded-full transition-all relative',
                          notifPrefs[key] ? 'bg-primary-600' : 'bg-dark-600'
                        )}
                      >
                        <div
                          className={cn(
                            'absolute w-5 h-5 rounded-full bg-white top-1 transition-all',
                            notifPrefs[key] ? 'left-6' : 'left-1'
                          )}
                        />
                      </button>
                    </div>
                  ))}
                </div>
              </SettingsSection>
            )}

            {/* Subscription */}
            <SettingsSection title="Subscription">
              <div className="flex items-center justify-between p-4 bg-dark-700/50 rounded-lg mb-4">
                <div>
                  <div className="font-medium">
                    {billingTier === 'pro' ? 'Pro Plan' : 'Free Tier'}
                  </div>
                  <div className="text-sm text-dark-400">
                    {billingTier === 'pro' ? 'Unlimited queries, all sports' : '5 queries per week, all sports'}
                  </div>
                  {billingTier === 'pro' && renewalDate && (
                    <div className="text-xs text-dark-500 mt-1">
                      {cancelAtPeriodEnd ? 'Cancels' : 'Renews'} {renewalDate}
                    </div>
                  )}
                </div>
                <span className={cn(
                  'px-3 py-1 rounded-full text-sm',
                  billingTier === 'pro'
                    ? 'bg-primary-600/20 text-primary-400'
                    : 'bg-dark-600 text-dark-300'
                )}>
                  {billingTier === 'pro' ? 'Active' : 'Current Plan'}
                </span>
              </div>
              {billingTier === 'pro' ? (
                <button
                  onClick={handleManageSubscription}
                  disabled={portalLoading}
                  className="w-full py-3 rounded-lg border border-dark-600 text-dark-200 font-medium hover:bg-dark-700/50 transition-all flex items-center justify-center gap-2"
                >
                  {portalLoading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      <CreditCard className="w-5 h-5" />
                      Manage Subscription
                    </>
                  )}
                </button>
              ) : (
                <button
                  onClick={() => router.push('/billing')}
                  className="w-full py-3 rounded-lg bg-primary-600 text-white font-medium hover:bg-primary-500 transition-all flex items-center justify-center gap-2"
                >
                  <CreditCard className="w-5 h-5" />
                  Upgrade to Pro
                </button>
              )}
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
                <p>BenchGoblin v0.9.0</p>
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
