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
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const features = [
  {
    icon: Sparkles,
    title: 'AI-Powered Decisions',
    description:
      'Get instant recommendations powered by Claude AI with deep understanding of fantasy sports strategy.',
  },
  {
    icon: BarChart3,
    title: 'Five-Index Scoring',
    description:
      'Proprietary scoring system analyzing Space Creation, Role Motion, Gravity Impact, Opportunity Delta, and Matchup Fit.',
  },
  {
    icon: Zap,
    title: 'Real-Time Analysis',
    description: 'Live player data from ESPN, Yahoo, and Sleeper integrated into every decision.',
  },
  {
    icon: Users,
    title: 'Multi-Sport Support',
    description: 'NBA, NFL, MLB, and NHL coverage with sport-specific scoring and analysis.',
  },
];

const riskModes = [
  {
    icon: Shield,
    name: 'Floor Mode',
    description: 'Prioritize consistent, safe players. Minimize variance and protect your lead.',
    color: 'text-green-400',
    bg: 'bg-green-400/10',
  },
  {
    icon: Target,
    name: 'Median Mode',
    description: 'Balanced approach weighing floor and ceiling equally. Best for most matchups.',
    color: 'text-blue-400',
    bg: 'bg-blue-400/10',
  },
  {
    icon: TrendingUp,
    name: 'Ceiling Mode',
    description: 'Chase upside and boom potential. When you need a big week to come back.',
    color: 'text-orange-400',
    bg: 'bg-orange-400/10',
  },
];

const decisionTypes = [
  { name: 'Start/Sit', description: 'Who to play this week' },
  { name: 'Trade Analysis', description: 'Fair value and upside' },
  { name: 'Waiver Wire', description: 'Pickup priorities' },
  { name: 'Explanations', description: 'Deep dives on players' },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950">
      {/* Header */}
      <header className="border-b border-dark-800/50">
        <div className="container mx-auto px-4">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-2">
              <Image src="/logo.png" alt="Bench Goblins" width={40} height={40} className="rounded" />
              <span className="text-xl font-bold gradient-text">Bench Goblins</span>
            </div>
            <div className="flex items-center gap-4">
              <Link href="/history">
                <Button variant="ghost">History</Button>
              </Link>
              <Link href="/ask">
                <Button className="shadow-lg shadow-primary-500/20">
                  Get Started
                  <ArrowRight className="ml-2 h-4 w-4" />
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
            <span className="gradient-text">Fantasy Sports Decisions,</span>
            <br />
            <span className="text-dark-100">Powered by AI</span>
          </h1>
          <p className="mt-6 text-lg text-dark-400">
            Stop second-guessing your lineups. Bench Goblins analyzes player data, matchups, and trends
            to give you confident start/sit, trade, and waiver recommendations in seconds.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/ask">
              <Button size="lg" className="gap-2 shadow-lg shadow-primary-500/25 hover:shadow-primary-500/40 transition-shadow">
                <Sparkles className="h-5 w-5" />
                Start Asking Questions
              </Button>
            </Link>
            <Link href="/history">
              <Button size="lg" variant="outline" className="gap-2">
                View History
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="container mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold">Why Bench Goblins?</h2>
          <p className="mt-4 text-dark-400">
            More than just rankings. Personalized analysis for your specific situation.
          </p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
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
          <h2 className="text-3xl font-bold">Three Risk Modes</h2>
          <p className="mt-4 text-dark-400">
            Tailor recommendations to your matchup situation and risk tolerance.
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
            <h2 className="text-3xl font-bold">Ask Anything</h2>
            <p className="mt-4 text-dark-400">
              Bench Goblins understands natural language questions about your fantasy team.
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
              &ldquo;Should I start Jayson Tatum or Anthony Edwards this week? I&apos;m projected to
              lose by 10 points.&rdquo;
            </p>
            <p className="mt-2 text-dark-500 text-sm">
              Bench Goblins will factor in your situation when making recommendations.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-4 py-24 text-center">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl font-bold mb-4">Ready to win your league?</h2>
          <p className="text-dark-400 mb-8">
            Join thousands of fantasy managers making smarter decisions with Bench Goblins.
          </p>
          <Link href="/ask">
            <Button size="lg" className="gap-2">
              <Sparkles className="h-5 w-5" />
              Start Free
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
              Built by fantasy sports enthusiasts, for fantasy sports enthusiasts.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
