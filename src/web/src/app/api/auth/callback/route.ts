import { NextRequest, NextResponse } from 'next/server';

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';
const GOOGLE_REDIRECT_URI = `${APP_URL}/api/auth/callback`;

interface GoogleTokenResponse {
  access_token: string;
  id_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
}

interface GoogleUserInfo {
  sub: string;
  name: string;
  given_name: string;
  family_name?: string;
  picture?: string;
  email: string;
  email_verified: boolean;
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get('code');
  const error = searchParams.get('error');

  // Handle OAuth errors
  if (error) {
    console.error('Google OAuth error:', error);
    return NextResponse.redirect(`${APP_URL}/auth/login?error=${error}`);
  }

  if (!code) {
    return NextResponse.redirect(`${APP_URL}/auth/login?error=no_code`);
  }

  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
    console.error('Google OAuth credentials not configured');
    return NextResponse.redirect(`${APP_URL}/auth/login?error=config_error`);
  }

  try {
    // Exchange code for tokens
    const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        code,
        client_id: GOOGLE_CLIENT_ID,
        client_secret: GOOGLE_CLIENT_SECRET,
        redirect_uri: GOOGLE_REDIRECT_URI,
        grant_type: 'authorization_code',
      }),
    });

    if (!tokenResponse.ok) {
      const error = await tokenResponse.text();
      console.error('Token exchange failed:', error);
      return NextResponse.redirect(`${APP_URL}/auth/login?error=token_exchange`);
    }

    const tokens: GoogleTokenResponse = await tokenResponse.json();

    // Get user info from Google
    const userResponse = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
      },
    });

    if (!userResponse.ok) {
      console.error('Failed to get user info');
      return NextResponse.redirect(`${APP_URL}/auth/login?error=user_info`);
    }

    const userInfo: GoogleUserInfo = await userResponse.json();

    // Create response with redirect to onboarding (skips to /ask if already completed)
    const response = NextResponse.redirect(`${APP_URL}/onboarding`);

    // Store user info directly in cookies (temporary workaround while DB is being fixed)
    // In production, this should create a session in the backend
    const sessionData = {
      user_id: userInfo.sub,
      email: userInfo.email,
      name: userInfo.name,
      picture: userInfo.picture,
      exp: Date.now() + (30 * 24 * 60 * 60 * 1000), // 30 days
    };

    // Set session data in httpOnly cookie (URL encoded for safety)
    response.cookies.set('benchgoblin_session', encodeURIComponent(JSON.stringify(sessionData)), {
      httpOnly: true,
      secure: true, // Always secure on Vercel
      sameSite: 'lax',
      maxAge: 30 * 24 * 60 * 60, // 30 days
      path: '/',
    });

    // Set a non-httpOnly cookie for client-side to know user is logged in
    response.cookies.set('benchgoblin_user', encodeURIComponent(JSON.stringify({
      name: userInfo.name,
      email: userInfo.email,
      picture: userInfo.picture,
    })), {
      httpOnly: false,
      secure: true, // Always secure on Vercel
      sameSite: 'lax',
      maxAge: 30 * 24 * 60 * 60,
      path: '/',
    });

    return response;
  } catch (error) {
    console.error('OAuth callback error:', error);
    return NextResponse.redirect(`${APP_URL}/auth/login?error=unknown`);
  }
}
