'use client';

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
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { LanguageSelector } from '@/components/LanguageSelector';
import { useTranslation } from '@/i18n/I18nProvider';

export default function LandingPage() {
  const { t } = useTranslation();

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
            <p className="text-dark-500 text-sm">
              {t('landing.footerTagline')}
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
