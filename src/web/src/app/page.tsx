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
    const interval = setInterval(tick, 1000);
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
            <div className="flex items-center gap-2">
              <LanguageSelector />
              <Link href="/history">
                <Button variant="ghost" size="sm">{t('common.history')}</Button>
              </Link>
              <Link href="/auth/login">
                <Button variant="outline" size="sm" className="gap-1.5 border-dark-700">
                  <LogIn className="h-4 w-4" />
                  {t('common.signIn')}
                </Button>
              </Link>
              <Link href="/ask">
                <Button size="sm" className="shadow-lg shadow-primary-500/20">
                  {t('common.getStarted')}
                  <ArrowRight className="ml-1.5 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="container mx-auto px-4 py-16 text-center">
        <div className="mx-auto max-w-3xl">
          {/* Centered Logo */}
          <div className="flex justify-center mb-8">
            <Image
              src="/logo.png"
              alt="Bench Goblins"
              width={280}
              height={280}
              className="drop-shadow-2xl"
              priority
            />
          </div>

          {/* Dynamic Sports Countdown */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full bg-dark-800/80 border border-dark-700 px-4 py-2">
            <Clock className="h-4 w-4 text-primary-400" />
            <span className="text-sm font-medium text-dark-300">
              {event.name}{event.location ? ` — ${event.location}` : ''}
            </span>
            <span className="text-xs text-dark-500 border-l border-dark-700 pl-2">{event.sport}</span>
          </div>
          <div className="mb-8 flex justify-center gap-4">
            {[
              { value: countdown.days, label: 'Days' },
              { value: countdown.hours, label: 'Hrs' },
              { value: countdown.minutes, label: 'Min' },
              { value: countdown.seconds, label: 'Sec' },
            ].map((unit) => (
              <div key={unit.label} className="flex flex-col items-center">
                <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-xl bg-dark-800/80 border border-dark-700 flex items-center justify-center">
                  <span className="text-2xl sm:text-3xl font-bold tabular-nums gradient-text">
                    {String(unit.value).padStart(2, '0')}
                  </span>
                </div>
                <span className="mt-1 text-xs text-dark-500 uppercase tracking-wider">{unit.label}</span>
              </div>
            ))}
          </div>

          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            <span className="gradient-text">{t('landing.heroTitle1')}</span>
            <br />
            <span className="text-dark-100">{t('landing.heroTitle2')}</span>
          </h1>
          <p className="mt-6 text-lg text-dark-400">
            {t('landing.heroSubtitle')}
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/ask">
              <Button size="lg" className="gap-2 shadow-lg shadow-primary-500/25 hover:shadow-primary-500/40 transition-shadow">
                <Sparkles className="h-5 w-5" />
                {t('landing.startAsking')}
              </Button>
            </Link>
            <Link href="/auth/login">
              <Button size="lg" variant="outline" className="gap-2 border-dark-700">
                <LogIn className="h-5 w-5" />
                {t('common.signIn')}
              </Button>
            </Link>
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
              <Link href="/ask" className="block">
                <Button variant="outline" className="w-full border-dark-600">
                  {t('landing.pricingGetStarted')}
                </Button>
              </Link>
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
              <Link href="/auth/login" className="block">
                <Button variant="outline" className="w-full border-primary-500/50 text-primary-400 hover:bg-primary-500/10">
                  {t('landing.pricingChooseWeekly')}
                </Button>
              </Link>
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
              <Link href="/auth/login" className="block">
                <Button className="w-full shadow-lg shadow-primary-500/20">
                  {t('landing.pricingChooseMonthly')}
                </Button>
              </Link>
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
              <Link href="/auth/login" className="block">
                <Button className="w-full bg-green-600 hover:bg-green-700 shadow-lg shadow-green-500/20">
                  {t('landing.pricingChooseAnnual')}
                </Button>
              </Link>
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
                  <Link href="/auth/login" className="block">
                    <Button variant="outline" className="w-full border-orange-500/50 text-orange-400 hover:bg-orange-500/10">
                      {t('landing.pricingChooseSeasonal')}
                    </Button>
                  </Link>
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
                  <Link href="/auth/login" className="block">
                    <Button variant="outline" className="w-full border-blue-500/50 text-blue-400 hover:bg-blue-500/10">
                      {t('landing.pricingChooseLeague')}
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-4 py-24 text-center">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl font-bold mb-4">{t('landing.ctaTitle')}</h2>
          <p className="text-dark-400 mb-8">
            {t('landing.ctaSubtitle')}
          </p>
          <Link href="/ask">
            <Button size="lg" className="gap-2">
              <Sparkles className="h-5 w-5" />
              {t('common.startFree')}
            </Button>
          </Link>
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
