import { NextRequest, NextResponse } from 'next/server';

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';
const GOOGLE_REDIRECT_URI = `${APP_URL}/api/auth/callback`;
const API_BASE_URL = process.env.NODE_ENV === 'production'
  ? 'https://backend.benchgoblins.com'
  : (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');

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

    // Authenticate with our backend to get a JWT
    const backendResponse = await fetch(`${API_BASE_URL}/auth/google`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: tokens.id_token }),
    });

    if (!backendResponse.ok) {
      const errText = await backendResponse.text();
      console.error('Backend auth failed:', backendResponse.status, errText);
      return NextResponse.redirect(`${APP_URL}/auth/login?error=backend_auth`);
    }

    const authData = await backendResponse.json();
    const { access_token, user } = authData;

    // Create response with redirect to onboarding (skips to /ask if already completed)
    const response = NextResponse.redirect(`${APP_URL}/onboarding`);

    // Store JWT in a JS-readable cookie so the auth store can pick it up
    response.cookies.set('benchgoblin_jwt', access_token, {
      httpOnly: false,
      secure: true,
      sameSite: 'lax',
      maxAge: 7 * 24 * 60 * 60, // 7 days (matches JWT expiry)
      path: '/',
    });

    // Store user info in a JS-readable cookie for quick hydration
    response.cookies.set('benchgoblin_user', encodeURIComponent(JSON.stringify({
      id: user.id,
      name: user.name || userInfo.name,
      email: user.email || userInfo.email,
      picture: user.picture_url || userInfo.picture,
      subscription_tier: user.subscription_tier || 'free',
    })), {
      httpOnly: false,
      secure: true,
      sameSite: 'lax',
      maxAge: 7 * 24 * 60 * 60,
      path: '/',
    });

    return response;
  } catch (error) {
    console.error('OAuth callback error:', error);
    return NextResponse.redirect(`${APP_URL}/auth/login?error=unknown`);
  }
}
