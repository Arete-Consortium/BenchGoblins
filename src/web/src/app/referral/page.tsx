'use client';

import { useState, useEffect, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';
import { Copy, Check, Users, Gift, Trophy, Share2 } from 'lucide-react';
import api from '@/lib/api';

export default function ReferralPage() {
  const { isAuthenticated } = useAuthStore();

  const [referralCode, setReferralCode] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [stats, setStats] = useState<{
    total_referrals: number;
    pro_days_remaining: number;
    max_referrals: number;
  } | null>(null);

  const [applyCode, setApplyCode] = useState('');
  const [applyResult, setApplyResult] = useState<{ success: boolean; message: string } | null>(null);
  const [applyLoading, setApplyLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    try {
      const [codeData, statsData] = await Promise.all([
        api.getReferralCode(),
        api.getReferralStats(),
      ]);
      setReferralCode(codeData.referral_code);
      setShareUrl(codeData.share_url);
      setStats(statsData);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCopy = async () => {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleApply = async () => {
    if (!applyCode.trim()) return;
    setApplyLoading(true);
    setApplyResult(null);
    try {
      const result = await api.applyReferralCode(applyCode.trim().toUpperCase());
      setApplyResult({ success: true, message: result.message });
      setApplyCode('');
      fetchData();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setApplyResult({ success: false, message: detail || 'Failed to apply code' });
    } finally {
      setApplyLoading(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="pt-20 pb-8 px-4">
          <div className="max-w-2xl mx-auto text-center">
            <Gift className="w-16 h-16 text-primary-400 mx-auto mb-4" />
            <h1 className="text-3xl font-bold mb-2">Invite Friends, Earn Pro</h1>
            <p className="text-dark-400 mb-6">
              Sign in to get your referral code and start earning free Pro access.
            </p>
            <a
              href="/auth/login"
              className="inline-block px-6 py-3 rounded-lg bg-primary-600 text-white font-medium hover:bg-primary-500 transition-all"
            >
              Sign In
            </a>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="pt-20 pb-8 px-4">
        <div className="max-w-2xl mx-auto">
          {/* Header */}
          <div className="text-center mb-8">
            <Gift className="w-12 h-12 text-primary-400 mx-auto mb-3" />
            <h1 className="text-3xl font-bold">Invite Leaguemates</h1>
            <p className="text-dark-400 mt-2">
              Share your code. You both get <span className="text-primary-400 font-semibold">7 days of free Pro</span>.
            </p>
          </div>

          {loading ? (
            <div className="text-center text-dark-400 py-12">Loading...</div>
          ) : (
            <div className="space-y-6">
              {/* Your Referral Code */}
              <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                <h2 className="text-lg font-semibold mb-4">Your Referral Code</h2>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-dark-900 border border-dark-600 rounded-lg px-4 py-3 font-mono text-xl text-center tracking-wider">
                    {referralCode || '--------'}
                  </div>
                  <button
                    onClick={handleCopy}
                    className={cn(
                      'px-4 py-3 rounded-lg font-medium transition-all flex items-center gap-2',
                      copied
                        ? 'bg-green-600/20 text-green-400 border border-green-600/30'
                        : 'bg-primary-600 text-white hover:bg-primary-500'
                    )}
                  >
                    {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
                    {copied ? 'Copied' : 'Copy Link'}
                  </button>
                </div>
                {shareUrl && (
                  <p className="text-xs text-dark-500 mt-2 truncate">{shareUrl}</p>
                )}

                {/* Share buttons */}
                <div className="flex gap-3 mt-4">
                  <a
                    href={`sms:?body=Join me on BenchGoblins and get 7 days of Pro free! ${shareUrl}`}
                    className="flex-1 py-2 rounded-lg border border-dark-600 text-dark-300 text-sm font-medium hover:border-primary-600 hover:text-primary-400 transition-all text-center flex items-center justify-center gap-2"
                  >
                    <Share2 className="w-4 h-4" />
                    Text
                  </a>
                  <a
                    href={`https://twitter.com/intent/tweet?text=Join me on BenchGoblins — AI-powered fantasy decisions. Use my link for 7 days free Pro!&url=${encodeURIComponent(shareUrl || '')}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 py-2 rounded-lg border border-dark-600 text-dark-300 text-sm font-medium hover:border-primary-600 hover:text-primary-400 transition-all text-center"
                  >
                    Twitter/X
                  </a>
                </div>
              </div>

              {/* Stats */}
              {stats && (
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 text-center">
                    <Users className="w-6 h-6 text-primary-400 mx-auto mb-2" />
                    <div className="text-2xl font-bold">{stats.total_referrals}</div>
                    <div className="text-xs text-dark-400 mt-1">Referrals</div>
                  </div>
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 text-center">
                    <Trophy className="w-6 h-6 text-yellow-400 mx-auto mb-2" />
                    <div className="text-2xl font-bold">{stats.pro_days_remaining}</div>
                    <div className="text-xs text-dark-400 mt-1">Pro Days Left</div>
                  </div>
                  <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-4 text-center">
                    <Gift className="w-6 h-6 text-green-400 mx-auto mb-2" />
                    <div className="text-2xl font-bold">{stats.max_referrals - stats.total_referrals}</div>
                    <div className="text-xs text-dark-400 mt-1">Remaining</div>
                  </div>
                </div>
              )}

              {/* How it Works */}
              <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                <h2 className="text-lg font-semibold mb-4">How It Works</h2>
                <div className="space-y-3">
                  {[
                    { step: '1', text: 'Share your referral link with a friend' },
                    { step: '2', text: 'They sign up using your link' },
                    { step: '3', text: 'You both get 7 days of free Pro access' },
                  ].map(({ step, text }) => (
                    <div key={step} className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary-600/20 text-primary-400 flex items-center justify-center text-sm font-bold shrink-0">
                        {step}
                      </div>
                      <span className="text-dark-300">{text}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Apply a Code */}
              <div className="bg-dark-800/50 border border-dark-700 rounded-xl p-6">
                <h2 className="text-lg font-semibold mb-4">Have a Referral Code?</h2>
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={applyCode}
                    onChange={(e) => setApplyCode(e.target.value.toUpperCase())}
                    placeholder="Enter code"
                    maxLength={12}
                    className="flex-1 bg-dark-900 border border-dark-600 rounded-lg px-4 py-3 font-mono tracking-wider text-center uppercase placeholder:text-dark-500 focus:border-primary-600 focus:outline-none transition-all"
                  />
                  <button
                    onClick={handleApply}
                    disabled={applyLoading || applyCode.length < 6}
                    className="px-6 py-3 rounded-lg bg-primary-600 text-white font-medium hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    {applyLoading ? 'Applying...' : 'Apply'}
                  </button>
                </div>
                {applyResult && (
                  <div
                    className={cn(
                      'mt-3 px-4 py-2 rounded-lg text-sm',
                      applyResult.success
                        ? 'bg-green-600/20 text-green-400 border border-green-600/30'
                        : 'bg-red-600/20 text-red-400 border border-red-600/30'
                    )}
                  >
                    {applyResult.message}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
