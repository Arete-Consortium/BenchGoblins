import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Routes that require authentication — redirect to /login if no token.
 */
const PROTECTED_ROUTES = [
  '/dashboard',
  '/history',
  '/billing',
  '/settings',
];

/**
 * Routes that authenticated users should not see — redirect to /dashboard.
 */
const AUTH_ROUTES = ['/login', '/signup'];

const AUTH_TOKEN_COOKIE = 'benchgoblin_auth_token';

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token =
    request.cookies.get(AUTH_TOKEN_COOKIE)?.value ??
    (typeof request.headers.get('authorization') === 'string'
      ? request.headers.get('authorization')!.replace('Bearer ', '')
      : null);

  const isAuthenticated = !!token;

  // Protect authenticated-only routes
  if (PROTECTED_ROUTES.some((route) => pathname.startsWith(route))) {
    if (!isAuthenticated) {
      const loginUrl = new URL('/login', request.url);
      loginUrl.searchParams.set('redirect', pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  // Redirect authenticated users away from login/signup
  if (AUTH_ROUTES.some((route) => pathname.startsWith(route))) {
    if (isAuthenticated) {
      return NextResponse.redirect(new URL('/dashboard', request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/dashboard/:path*',
    '/history/:path*',
    '/billing/:path*',
    '/settings/:path*',
    '/login',
    '/signup',
  ],
};
