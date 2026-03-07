'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useRouter, usePathname } from 'next/navigation';
import { History, MessageSquare, Settings, LogOut, CreditCard, Zap, User, Target, BookOpen, Sparkles, Gift, Trophy, Crown, LayoutDashboard } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from './ThemeToggle';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAuthStore } from '@/stores/authStore';
import { useSubscriptionStore } from '@/stores/subscriptionStore';

// Primary nav items always visible; secondary hidden on mobile
const navItems = [
  { href: '/ask', label: 'Ask', icon: MessageSquare, primary: true },
  { href: '/verdict', label: 'Verdict', icon: Sparkles, primary: true },
  { href: '/history', label: 'History', icon: History, primary: true },
  { href: '/leaderboard', label: 'Leaderboard', icon: Trophy, primary: true },
  { href: '/recaps', label: 'Recaps', icon: BookOpen, primary: false },
  { href: '/commissioner', label: 'Commissioner', icon: Crown, primary: false },
  { href: '/accuracy', label: 'Accuracy', icon: Target, primary: false },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, primary: false },
  { href: '/settings', label: 'Settings', icon: Settings, primary: false },
];

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function UsageIndicator({ queriesUsed, queriesLimit }: { queriesUsed: number; queriesLimit: number }) {
  const isUnlimited = queriesLimit === -1 || queriesLimit >= 999999;
  const percentage = isUnlimited ? 100 : (queriesUsed / queriesLimit) * 100;
  const isLow = !isUnlimited && percentage >= 80;

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-dark-800/50 border border-dark-700">
      <Zap className={cn('h-3.5 w-3.5', isLow ? 'text-yellow-400' : 'text-primary-400')} />
      <span className="text-xs font-medium">
        {isUnlimited ? (
          <span className="text-primary-400">Unlimited</span>
        ) : (
          <>
            <span className={isLow ? 'text-yellow-400' : 'text-dark-200'}>{queriesUsed}</span>
            <span className="text-dark-500">/{queriesLimit}</span>
          </>
        )}
      </span>
    </div>
  );
}

export function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isAuthenticated, signOut } = useAuthStore();
  const { isPro } = useSubscriptionStore();

  const handleSignOut = async () => {
    await signOut();
    router.push('/');
  };

  const handleSignIn = () => {
    router.push('/auth/login');
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-dark-800/50 bg-dark-900/90 backdrop-blur-md">
      <div className="container mx-auto px-4">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link href={isAuthenticated ? '/ask' : '/'} className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <Image src="/logo.png" alt="Bench Goblins" width={40} height={40} className="rounded" />
            <span className="text-xl font-bold gradient-text">Bench Goblins</span>
          </Link>

          {/* Navigation */}
          <nav className="flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link key={item.href} href={item.href} className={item.primary ? '' : 'hidden md:block'}>
                  <Button
                    variant={isActive ? 'secondary' : 'ghost'}
                    size="sm"
                    className={cn(
                      'gap-2',
                      isActive && 'bg-dark-800 text-primary-400'
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                    <span className="hidden lg:inline">{item.label}</span>
                  </Button>
                </Link>
              );
            })}
          </nav>

          {/* Right side */}
          <div className="flex items-center gap-3">
            {/* Usage indicator (only for authenticated users) */}
            {isAuthenticated && user && (
              <UsageIndicator
                queriesUsed={user.queries_today}
                queriesLimit={user.queries_limit}
              />
            )}

            <ThemeToggle />

            {/* User menu or Sign In button */}
            {isAuthenticated && user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="relative h-9 w-9 rounded-full">
                    <Avatar className="h-9 w-9">
                      {user.picture_url && (
                        <AvatarImage src={user.picture_url} alt={user.name} />
                      )}
                      <AvatarFallback className="bg-primary-600 text-white text-sm">
                        {getInitials(user.name)}
                      </AvatarFallback>
                    </Avatar>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-56" align="end" forceMount>
                  <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-medium leading-none">{user.name}</p>
                      <p className="text-xs leading-none text-dark-400">{user.email}</p>
                      <div className="flex items-center gap-1 pt-1">
                        <span
                          className={cn(
                            'text-xs font-medium px-2 py-0.5 rounded-full',
                            isPro
                              ? 'bg-primary-500/20 text-primary-400'
                              : 'bg-dark-700 text-dark-400'
                          )}
                        >
                          {isPro ? 'Pro' : 'Free'}
                        </span>
                      </div>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => router.push('/settings')}>
                    <Settings className="mr-2 h-4 w-4" />
                    Settings
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push('/billing')}>
                    <CreditCard className="mr-2 h-4 w-4" />
                    Billing
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push('/referral')}>
                    <Gift className="mr-2 h-4 w-4" />
                    Invite Friends
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleSignOut} className="text-red-400 focus:text-red-400">
                    <LogOut className="mr-2 h-4 w-4" />
                    Sign Out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Button
                onClick={handleSignIn}
                size="sm"
                className="gap-2 bg-primary-600 hover:bg-primary-500"
              >
                <User className="h-4 w-4" />
                <span className="hidden sm:inline">Sign In</span>
              </Button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
