'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Users2, Crown, Shield, ArrowLeft, Loader2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/stores/authStore';
import api from '@/lib/api';

interface ManagedLeague {
  id: number;
  external_league_id: string;
  platform: string;
  name: string;
  sport: string;
  season: string;
  role: string;
  member_count: number;
  has_pro: boolean;
  invite_code: string | null;
}

export default function LeaguesPage() {
  const { isAuthenticated } = useAuthStore();
  const [leagues, setLeagues] = useState<ManagedLeague[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;

    const fetchLeagues = async () => {
      try {
        const data = await api.getManagedLeagues();
        setLeagues(data);
      } catch {
        setError('Failed to load leagues');
      } finally {
        setLoading(false);
      }
    };

    fetchLeagues();
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-background p-6">
        <div className="max-w-4xl mx-auto text-center py-20">
          <Users2 className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
          <h1 className="text-2xl font-bold mb-2">Sign in to manage leagues</h1>
          <p className="text-muted-foreground mb-6">Connect your fantasy leagues and manage your team.</p>
          <Link href="/auth">
            <Button>Sign In</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <Link href="/dashboard">
              <Button variant="ghost" size="icon">
                <ArrowLeft className="w-5 h-5" />
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-bold">My Leagues</h1>
              <p className="text-muted-foreground">Manage your fantasy leagues</p>
            </div>
          </div>
          <Link href="/settings">
            <Button variant="outline">
              <Plus className="w-4 h-4 mr-2" />
              Connect League
            </Button>
          </Link>
        </div>

        {loading && (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && (
          <div className="text-center py-20 text-destructive">{error}</div>
        )}

        {!loading && !error && leagues.length === 0 && (
          <div className="text-center py-20">
            <Users2 className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
            <h2 className="text-xl font-semibold mb-2">No leagues yet</h2>
            <p className="text-muted-foreground mb-6">
              Connect a Sleeper, ESPN, or Yahoo league to get started.
            </p>
            <Link href="/settings">
              <Button>Connect a League</Button>
            </Link>
          </div>
        )}

        <div className="grid gap-4">
          {leagues.map((league) => (
            <Link key={league.id} href={`/league/${league.id}`}>
              <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {league.role === 'commissioner' ? (
                        <Crown className="w-5 h-5 text-yellow-500" />
                      ) : (
                        <Shield className="w-5 h-5 text-blue-500" />
                      )}
                      <div>
                        <CardTitle className="text-lg">{league.name}</CardTitle>
                        <p className="text-sm text-muted-foreground">
                          {league.sport.toUpperCase()} &middot; {league.season} &middot; {league.platform}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-medium capitalize">{league.role}</span>
                      {league.has_pro && (
                        <span className="ml-2 text-xs bg-primary/20 text-primary px-2 py-0.5 rounded-full">
                          PRO
                        </span>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Users2 className="w-4 h-4" />
                      {league.member_count} members
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
