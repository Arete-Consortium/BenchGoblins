'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import {
  Sparkles,
  TrendingUp,
  Shield,
  Target,
  Zap,
  BarChart3,
  Users,
  ArrowRight,
  CheckCircle,
  LogIn,
  Clock,
  MessageSquare,
  Brain,
  Trophy,
  Crown,
  Calendar,
  Users2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { EmailCapture } from '@/components/EmailCapture';
import { LanguageSelector } from '@/components/LanguageSelector';
import { useTranslation } from '@/i18n/I18nProvider';

// Upcoming sports events — countdown auto-rotates to the nearest future event
const SPORTS_EVENTS = [
  { name: 'NFL Draft', location: 'Pittsburgh', date: '2026-04-23T20:00:00-04:00', sport: 'NFL' },
  { name: 'NBA Playoffs', location: '', date: '2026-04-18T12:00:00-04:00', sport: 'NBA' },
  { name: 'NHL Playoffs', location: '', date: '2026-04-15T19:00:00-04:00', sport: 'NHL' },
  { name: 'MLB Opening Day', location: '', date: '2026-03-26T13:00:00-04:00', sport: 'MLB' },
  { name: 'NFL Season Kickoff', location: '', date: '2026-09-10T20:20:00-04:00', sport: 'NFL' },
  { name: 'Premier League Starts', location: '', date: '2026-08-15T12:30:00+01:00', sport: 'Soccer' },
  { name: 'NBA Season Tipoff', location: '', date: '2026-10-20T19:30:00-04:00', sport: 'NBA' },
];

function getNextEvent() {
  const now = Date.now();
  const upcoming = SPORTS_EVENTS
    .map((e) => ({ ...e, ms: new Date(e.date).getTime() }))
    .filter((e) => e.ms > now)
    .sort((a, b) => a.ms - b.ms);
  return upcoming[0] ?? { ...SPORTS_EVENTS[0], ms: new Date(SPORTS_EVENTS[0].date).getTime() };
}

function useCountdown() {
  const [event, setEvent] = useState(getNextEvent);
  const [timeLeft, setTimeLeft] = useState({ days: 0, hours: 0, minutes: 0, seconds: 0 });

  useEffect(() => {
    function tick() {
      const current = getNextEvent();
      if (current.name !== event.name) setEvent(current);
      const diff = current.ms - Date.now();
      if (diff <= 0) {
        setTimeLeft({ days: 0, hours: 0, minutes: 0, seconds: 0 });
        return;
      }
      setTimeLeft({
        days: Math.floor(diff / (1000 * 60 * 60 * 24)),
        hours: Math.floor((diff / (1000 * 60 * 60)) % 24),
        minutes: Math.floor((diff / (1000 * 60)) % 60),
        seconds: Math.floor((diff / 1000) % 60),
      });
    }
    tick();
    // Update every 30s instead of 1s — reduces re-renders 30x
    const interval = setInterval(tick, 30000);
    return () => clearInterval(interval);
  }, [event.name]);

  return { event, timeLeft };
}

const jsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Bench Goblins',
  applicationCategory: 'SportsApplication',
  operatingSystem: 'Web',
  description:
    'AI-powered fantasy sports decision engine with Five-Index scoring for NBA, NFL, MLB, NHL, and Soccer.',
  url: 'https://benchgoblins.com',
  offers: {
    '@type': 'Offer',
    price: '0',
    priceCurrency: 'USD',
  },
};

export default function LandingPage() {
  const { t } = useTranslation();
  const { event, timeLeft: countdown } = useCountdown();

  const features = [
    {
      icon: Sparkles,
      title: t('landing.featureAI'),
      description: t('landing.featureAIDesc'),
    },
    {
      icon: BarChart3,
      title: t('landing.featureScoring'),
      description: t('landing.featureScoringDesc'),
    },
    {
      icon: Zap,
      title: t('landing.featureRealTime'),
      description: t('landing.featureRealTimeDesc'),
    },
    {
      icon: Users,
      title: t('landing.featureMultiSport'),
      description: t('landing.featureMultiSportDesc'),
    },
    {
      icon: Trophy,
      title: 'Leaderboards',
      description: 'See top-ranked players across every sport and position, powered by our five-index scoring.',
    },
    {
      icon: Crown,
      title: 'Commissioner Tools',
      description: 'League-level analytics, trade fairness scoring, and collusion detection for league managers.',
    },
  ];

  const riskModes = [
    {
      icon: Shield,
      name: t('landing.floorMode'),
      description: t('landing.floorDesc'),
      color: 'text-green-400',
      bg: 'bg-green-400/10',
    },
    {
      icon: Target,
      name: t('landing.medianMode'),
      description: t('landing.medianDesc'),
      color: 'text-blue-400',
      bg: 'bg-blue-400/10',
    },
    {
      icon: TrendingUp,
      name: t('landing.ceilingMode'),
      description: t('landing.ceilingDesc'),
      color: 'text-orange-400',
      bg: 'bg-orange-400/10',
    },
  ];

  const decisionTypes = [
    { name: t('landing.startSit'), description: t('landing.startSitDesc') },
    { name: t('landing.tradeAnalysis'), description: t('landing.tradeAnalysisDesc') },
    { name: t('landing.waiverWire'), description: t('landing.waiverWireDesc') },
    { name: t('landing.explanations'), description: t('landing.explanationsDesc') },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      {/* Header */}
      <header className="border-b border-dark-800/50">
        <div className="container mx-auto px-4">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-2">
              <Image src="/logo.png" alt="Bench Goblins" width={40} height={40} className="rounded" />
              <span className="text-xl font-bold gradient-text">Bench Goblins</span>
            </div>
            <div className="flex items-center gap-1 sm:gap-2">
              <LanguageSelector />
              <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
                <Link href="/leaderboard">Leaderboard</Link>
              </Button>
              <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
                <Link href="/dossier">Dossier</Link>
              </Button>
              <Button asChild variant="outline" size="sm" className="gap-1.5 border-dark-700">
                <Link href="/auth/login">
                  <LogIn className="h-4 w-4" />
                  <span className="hidden sm:inline">{t('common.signIn')}</span>
                </Link>
              </Button>
              <Button asChild size="sm" className="shadow-lg shadow-primary-500/20">
                <Link href="/ask">
                  {t('common.getStarted')}
                  <ArrowRight className="ml-1.5 h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="container mx-auto px-4 pt-12 pb-16 text-center">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
            <span className="gradient-text">{t('landing.heroTitle1')}</span>
            <br />
            <span className="text-dark-100">{t('landing.heroTitle2')}</span>
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-dark-400 max-w-2xl mx-auto">
            {t('landing.heroSubtitle')}
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button asChild size="lg" className="gap-2 shadow-lg shadow-primary-500/25 hover:shadow-primary-500/40 transition-shadow text-base px-8 py-3">
              <Link href="/ask">
                <Sparkles className="h-5 w-5" />
                {t('landing.startAsking')}
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="gap-2 border-dark-700">
              <Link href="/auth/login">
                <LogIn className="h-5 w-5" />
                {t('common.signIn')}
              </Link>
            </Button>
          </div>

          {/* Countdown badge — compact, below CTA */}
          <div className="mt-8 inline-flex items-center gap-3 rounded-full bg-dark-800/80 border border-dark-700 px-5 py-2.5">
            <Clock className="h-4 w-4 text-primary-400" />
            <span className="text-sm font-medium text-dark-300">
              {event.name}{event.location ? ` — ${event.location}` : ''}
            </span>
            <span className="text-sm font-bold tabular-nums gradient-text">
              {countdown.days}d {String(countdown.hours).padStart(2, '0')}h {String(countdown.minutes).padStart(2, '0')}m
            </span>
            <span className="text-xs text-dark-500 border-l border-dark-700 pl-2">{event.sport}</span>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="container mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold">{t('landing.whyTitle')}</h2>
          <p className="mt-4 text-dark-400">
            {t('landing.whySubtitle')}
          </p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <Card key={feature.title} className="bg-dark-800/50 border-dark-700">
              <CardContent className="pt-6">
                <feature.icon className="h-10 w-10 text-primary-400 mb-4" />
                <h3 className="font-semibold text-lg mb-2">{feature.title}</h3>
                <p className="text-dark-400 text-sm">{feature.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section className="container mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold">{t('landing.howTitle')}</h2>
          <p className="mt-4 text-dark-400">
            {t('landing.howSubtitle')}
          </p>
        </div>
        <div className="grid gap-8 md:grid-cols-3 max-w-4xl mx-auto">
          {[
            { step: 1, icon: MessageSquare, title: t('landing.howStep1Title'), desc: t('landing.howStep1Desc'), color: 'text-primary-400', bg: 'bg-primary-500/10' },
            { step: 2, icon: Brain, title: t('landing.howStep2Title'), desc: t('landing.howStep2Desc'), color: 'text-purple-400', bg: 'bg-purple-500/10' },
            { step: 3, icon: Trophy, title: t('landing.howStep3Title'), desc: t('landing.howStep3Desc'), color: 'text-amber-400', bg: 'bg-amber-500/10' },
          ].map((item) => (
            <div key={item.step} className="text-center">
              <div className="relative mx-auto mb-4">
                <div className={`w-16 h-16 rounded-2xl ${item.bg} flex items-center justify-center mx-auto`}>
                  <item.icon className={`h-8 w-8 ${item.color}`} />
                </div>
                <div className="absolute -top-2 -right-2 w-7 h-7 rounded-full bg-dark-800 border border-dark-600 flex items-center justify-center">
                  <span className="text-xs font-bold text-dark-300">{item.step}</span>
                </div>
              </div>
              <h3 className="font-semibold text-lg mb-2">{item.title}</h3>
              <p className="text-dark-400 text-sm">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Risk Modes */}
      <section className="container mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold">{t('landing.riskTitle')}</h2>
          <p className="mt-4 text-dark-400">
            {t('landing.riskSubtitle')}
          </p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {riskModes.map((mode) => (
            <Card key={mode.name} className="bg-dark-800/50 border-dark-700">
              <CardContent className="pt-6 text-center">
                <div
                  className={`w-16 h-16 rounded-2xl ${mode.bg} flex items-center justify-center mx-auto mb-4`}
                >
                  <mode.icon className={`h-8 w-8 ${mode.color}`} />
                </div>
                <h3 className="font-semibold text-lg mb-2">{mode.name}</h3>
                <p className="text-dark-400 text-sm">{mode.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Decision Types */}
      <section className="container mx-auto px-4 py-16">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold">{t('landing.askTitle')}</h2>
            <p className="mt-4 text-dark-400">
              {t('landing.askSubtitle')}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {decisionTypes.map((type) => (
              <div
                key={type.name}
                className="flex items-start gap-3 p-4 rounded-lg bg-dark-800/30 border border-dark-700"
              >
                <CheckCircle className="h-5 w-5 text-primary-400 mt-0.5" />
                <div>
                  <div className="font-medium">{type.name}</div>
                  <div className="text-sm text-dark-400">{type.description}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-8 p-4 rounded-lg bg-dark-800/50 border border-dark-700">
            <p className="text-dark-300 italic">
              {t('landing.exampleQuery')}
            </p>
            <p className="mt-2 text-dark-500 text-sm">
              {t('landing.exampleNote')}
            </p>
          </div>
        </div>
      </section>

      {/* Social Proof */}
      <section className="container mx-auto px-4 py-16 border-t border-dark-800/50">
        <div className="grid gap-8 grid-cols-2 md:grid-cols-4 max-w-4xl mx-auto text-center">
          <div>
            <div className="text-4xl font-bold gradient-text">5</div>
            <p className="text-dark-400 mt-1">Sports Covered</p>
          </div>
          <div>
            <div className="text-4xl font-bold gradient-text">3</div>
            <p className="text-dark-400 mt-1">Risk Modes</p>
          </div>
          <div>
            <div className="text-4xl font-bold gradient-text">5</div>
            <p className="text-dark-400 mt-1">Index Scores Per Player</p>
          </div>
          <div>
            <div className="text-4xl font-bold gradient-text">9</div>
            <p className="text-dark-400 mt-1">Languages</p>
          </div>
        </div>
        <div className="mt-12 max-w-5xl mx-auto">
          <div className="grid gap-6 md:grid-cols-3">
            <div className="p-6 rounded-xl bg-dark-800/50 border border-dark-700">
              <p className="text-dark-300 italic mb-3">
                &ldquo;The Goblin told me to bench my gut feeling and start the data. Won my league.&rdquo;
              </p>
              <p className="text-sm text-dark-500">— Fantasy manager, NFL</p>
            </div>
            <div className="p-6 rounded-xl bg-dark-800/50 border border-dark-700">
              <p className="text-dark-300 italic mb-3">
                &ldquo;Commissioner alerts saved my league from a collusion trade. Worth every penny.&rdquo;
              </p>
              <p className="text-sm text-dark-500">— League commissioner, NBA</p>
            </div>
            <div className="p-6 rounded-xl bg-dark-800/50 border border-dark-700">
              <p className="text-dark-300 italic mb-3">
                &ldquo;The five-index player dossiers are insane. Like having a fantasy analyst on speed dial.&rdquo;
              </p>
              <p className="text-sm text-dark-500">— Dynasty league owner, MLB</p>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="container mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold">{t('landing.pricingTitle')}</h2>
          <p className="mt-4 text-dark-400">
            {t('landing.pricingSubtitle')}
          </p>
        </div>

        {/* Core Plans — 4 columns */}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4 max-w-6xl mx-auto">
          {/* Free */}
          <Card className="bg-dark-800/50 border-dark-700">
            <CardContent className="pt-6">
              <h3 className="text-xl font-bold mb-1">{t('landing.pricingFree')}</h3>
              <div className="mb-6">
                <span className="text-3xl font-bold">{t('landing.pricingFreePrice')}</span>
              </div>
              <ul className="space-y-3 mb-6">
                {[
                  t('landing.pricingFreeFeature1'),
                  t('landing.pricingFreeFeature2'),
                  t('landing.pricingFreeFeature3'),
                  t('landing.pricingFreeFeature4'),
                ].map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                    <CheckCircle className="h-4 w-4 text-green-400 shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>
              <Button asChild variant="outline" className="w-full border-dark-600">
                <Link href="/ask">
                  {t('landing.pricingGetStarted')}
                </Link>
              </Button>
            </CardContent>
          </Card>

          {/* Weekly */}
          <Card className="bg-dark-800/50 border-dark-700">
            <CardContent className="pt-6">
              <h3 className="text-xl font-bold mb-1">{t('landing.pricingWeekly')}</h3>
              <div className="mb-6">
                <span className="text-3xl font-bold">{t('landing.pricingWeeklyPrice')}</span>
                <span className="text-dark-500 text-sm">{t('landing.pricingPerWeek')}</span>
              </div>
              <ul className="space-y-3 mb-6">
                {[
                  t('landing.pricingFeatureUnlimited'),
                  t('landing.pricingFeatureAllSports'),
                  t('landing.pricingFeatureAdvancedAI'),
                  t('landing.pricingFeatureTradeRecs'),
                  t('landing.pricingFeatureNoCommitment'),
                ].map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                    <CheckCircle className="h-4 w-4 text-primary-400 shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>
              <Button asChild variant="outline" className="w-full border-primary-500/50 text-primary-400 hover:bg-primary-500/10">
                <Link href="/billing">
                  {t('landing.pricingChooseWeekly')}
                </Link>
              </Button>
            </CardContent>
          </Card>

          {/* Monthly — Most Popular */}
          <Card className="bg-dark-800/50 border-primary-500/50 ring-2 ring-primary-500/30">
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-xl font-bold">{t('landing.pricingMonthly')}</h3>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary-500/20 text-primary-400">
                  <Crown className="inline h-3 w-3 mr-0.5 -mt-0.5" />
                  {t('landing.pricingMostPopular')}
                </span>
              </div>
              <div className="mb-6">
                <span className="text-3xl font-bold gradient-text">{t('landing.pricingMonthlyPrice')}</span>
                <span className="text-dark-500 text-sm">{t('landing.pricingPerMonth')}</span>
              </div>
              <ul className="space-y-3 mb-6">
                {[
                  t('landing.pricingFeatureUnlimited'),
                  t('landing.pricingFeatureAllSports'),
                  t('landing.pricingFeatureAdvancedAI'),
                  t('landing.pricingFeatureTradeRecs'),
                  t('landing.pricingFeaturePriority'),
                  t('landing.pricingFeatureNoCommitment'),
                ].map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                    <CheckCircle className="h-4 w-4 text-primary-400 shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>
              <Button asChild className="w-full shadow-lg shadow-primary-500/20">
                <Link href="/billing">
                  {t('landing.pricingChooseMonthly')}
                </Link>
              </Button>
            </CardContent>
          </Card>

          {/* Annual — Best Value */}
          <Card className="bg-dark-800/50 border-green-500/50 ring-2 ring-green-500/30">
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-xl font-bold">{t('landing.pricingAnnual')}</h3>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-500/20 text-green-400">
                  {t('landing.pricingBestValue')}
                </span>
              </div>
              <div className="mb-6">
                <span className="text-3xl font-bold text-green-400">{t('landing.pricingAnnualPrice')}</span>
                <span className="text-dark-500 text-sm">{t('landing.pricingPerYear')}</span>
                <div className="text-green-400 text-sm mt-1">{t('landing.pricingAnnualSavings')}</div>
              </div>
              <ul className="space-y-3 mb-6">
                {[
                  t('landing.pricingFeatureUnlimited'),
                  t('landing.pricingFeatureAllSports'),
                  t('landing.pricingFeatureAdvancedAI'),
                  t('landing.pricingFeatureTradeRecs'),
                  t('landing.pricingFeaturePriority'),
                  t('landing.pricingFeatureExport'),
                ].map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                    <CheckCircle className="h-4 w-4 text-green-400 shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>
              <Button asChild className="w-full bg-green-600 hover:bg-green-700 shadow-lg shadow-green-500/20">
                <Link href="/billing">
                  {t('landing.pricingChooseAnnual')}
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Specialized Plans */}
        <div className="mt-12 max-w-4xl mx-auto">
          <h3 className="text-xl font-semibold text-center mb-6 text-dark-300">
            {t('landing.pricingSpecializedTitle')}
          </h3>
          <div className="grid gap-6 md:grid-cols-2">
            {/* Seasonal Pass */}
            <Card className="bg-dark-800/50 border-dark-700">
              <CardContent className="pt-6 flex gap-4">
                <div className="shrink-0">
                  <div className="w-12 h-12 rounded-full bg-orange-500/20 flex items-center justify-center">
                    <Calendar className="h-6 w-6 text-orange-400" />
                  </div>
                </div>
                <div className="flex-1">
                  <h4 className="text-lg font-bold">{t('landing.pricingSeasonal')}</h4>
                  <div className="mb-3">
                    <span className="text-2xl font-bold text-orange-400">{t('landing.pricingSeasonalPrice')}</span>
                    <span className="text-dark-500 text-sm">{t('landing.pricingPerSeason')}</span>
                  </div>
                  <ul className="space-y-2 mb-4">
                    {[
                      t('landing.pricingFeatureOneSport'),
                      t('landing.pricingFeatureUnlimited'),
                      t('landing.pricingFeatureAdvancedAI'),
                    ].map((feature) => (
                      <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                        <CheckCircle className="h-3.5 w-3.5 text-orange-400 shrink-0" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <Button asChild variant="outline" className="w-full border-orange-500/50 text-orange-400 hover:bg-orange-500/10">
                    <Link href="/billing">
                      {t('landing.pricingChooseSeasonal')}
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* League Plan */}
            <Card className="bg-dark-800/50 border-dark-700">
              <CardContent className="pt-6 flex gap-4">
                <div className="shrink-0">
                  <div className="w-12 h-12 rounded-full bg-blue-500/20 flex items-center justify-center">
                    <Users2 className="h-6 w-6 text-blue-400" />
                  </div>
                </div>
                <div className="flex-1">
                  <h4 className="text-lg font-bold">{t('landing.pricingLeague')}</h4>
                  <div className="mb-3">
                    <span className="text-2xl font-bold text-blue-400">{t('landing.pricingLeaguePrice')}</span>
                    <span className="text-dark-500 text-sm">{t('landing.pricingPerMoPerLeague')}</span>
                  </div>
                  <ul className="space-y-2 mb-4">
                    {[
                      t('landing.pricingFeatureOneLeague'),
                      t('landing.pricingFeatureLeagueScoped'),
                      t('landing.pricingFeatureTradeRecs'),
                    ].map((feature) => (
                      <li key={feature} className="flex items-center gap-2 text-sm text-dark-300">
                        <CheckCircle className="h-3.5 w-3.5 text-blue-400 shrink-0" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <Button asChild variant="outline" className="w-full border-blue-500/50 text-blue-400 hover:bg-blue-500/10">
                    <Link href="/billing">
                      {t('landing.pricingChooseLeague')}
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-4 py-24 text-center">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">{t('landing.ctaTitle')}</h2>
          <p className="text-dark-400 mb-8 text-lg">
            {t('landing.ctaSubtitle')}
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button asChild size="lg" className="gap-2 text-base px-8 py-3 shadow-lg shadow-primary-500/25">
              <Link href="/ask">
                <Sparkles className="h-5 w-5" />
                {t('common.startFree')}
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="gap-2 border-dark-700">
              <Link href="/leaderboard">
                <Trophy className="h-5 w-5" />
                View Leaderboard
              </Link>
            </Button>
          </div>
          <p className="mt-4 text-sm text-dark-500">No credit card required. Free tier includes 3 queries/day.</p>
        </div>
      </section>

      {/* Newsletter */}
      <section className="border-t border-dark-800">
        <div className="container mx-auto px-4 py-16">
          <EmailCapture variant="inline" referrer="landing-page" />
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-dark-800">
        <div className="container mx-auto px-4 py-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Image src="/logo.png" alt="Bench Goblins" width={32} height={32} className="rounded" />
              <span className="font-semibold">Bench Goblins</span>
            </div>
            <div className="flex items-center gap-4 text-sm text-dark-500">
              <Link href="/privacy" className="hover:text-dark-300 transition-colors">
                {t('landing.footerPrivacy')}
              </Link>
              <Link href="/terms" className="hover:text-dark-300 transition-colors">
                {t('landing.footerTerms')}
              </Link>
              <Link href="/billing" className="hover:text-dark-300 transition-colors">
                {t('landing.footerBilling')}
              </Link>
            </div>
            <p className="text-dark-500 text-sm">
              {t('landing.footerTagline')}
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
