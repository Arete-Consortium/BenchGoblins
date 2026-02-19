'use client';

import { useState } from 'react';
import { Mail, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/I18nProvider';
import api from '@/lib/api';

interface EmailCaptureProps {
  variant?: 'inline' | 'full';
  referrer?: string;
}

const SPORTS = [
  { value: '', label: 'Any sport' },
  { value: 'nfl', label: 'NFL' },
  { value: 'nba', label: 'NBA' },
  { value: 'mlb', label: 'MLB' },
  { value: 'nhl', label: 'NHL' },
  { value: 'soccer', label: 'Soccer' },
];

export function EmailCapture({ variant = 'inline', referrer }: EmailCaptureProps) {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [sport, setSport] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);

    try {
      await api.subscribeNewsletter(email.trim(), undefined, sport || undefined, referrer);
      setSuccess(true);
      setEmail('');
      setSport('');
    } catch (err) {
      if (err instanceof Error && err.message.includes('429')) {
        setError('Too many requests. Try again later.');
      } else {
        setError(t('newsletter.error'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className={`text-center ${variant === 'full' ? 'py-16' : 'py-8'}`}>
        <div className="mx-auto w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center mb-4">
          <CheckCircle className="h-8 w-8 text-green-400" />
        </div>
        <h3 className="text-xl font-bold mb-2">{t('newsletter.success')}</h3>
        <p className="text-dark-400 text-sm">{t('newsletter.privacy')}</p>
      </div>
    );
  }

  return (
    <div className={`${variant === 'full' ? 'max-w-lg' : 'max-w-2xl'} mx-auto text-center`}>
      <div className="inline-flex items-center gap-2 rounded-full bg-primary-500/10 border border-primary-500/20 px-4 py-1.5 mb-4">
        <Mail className="h-4 w-4 text-primary-400" />
        <span className="text-sm font-medium text-primary-400">{t('newsletter.badge')}</span>
      </div>

      <h2 className={`font-bold mb-3 ${variant === 'full' ? 'text-3xl' : 'text-2xl'}`}>
        {t('newsletter.title')}
      </h2>
      <p className="text-dark-400 mb-8 text-sm sm:text-base">
        {t('newsletter.subtitle')}
      </p>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex flex-col sm:flex-row gap-3">
          <Input
            type="email"
            placeholder={t('newsletter.placeholder')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isLoading}
            required
            className="flex-1"
          />
          <select
            value={sport}
            onChange={(e) => setSport(e.target.value)}
            disabled={isLoading}
            className="h-10 rounded-md border border-dark-700 bg-dark-800 px-3 py-2 text-sm text-dark-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 ring-offset-dark-900"
          >
            {SPORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <Button type="submit" disabled={isLoading || !email.trim()} className="gap-2 shrink-0">
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('newsletter.subscribing')}
              </>
            ) : (
              t('newsletter.subscribe')
            )}
          </Button>
        </div>

        {error && (
          <div className="flex items-center justify-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <p className="text-sm">{error}</p>
          </div>
        )}
      </form>

      <p className="mt-4 text-dark-500 text-xs">{t('newsletter.privacy')}</p>
    </div>
  );
}
