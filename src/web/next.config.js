/** @type {import('next').NextConfig} */
// Backend: https://backend.benchgoblins.com
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        // Proxy backend API calls through same-origin to avoid CORS.
        // /bapi/* is rewritten to the backend; /api/* is reserved for
        // Next.js API routes (OAuth callback, etc.).
        source: '/bapi/:path*',
        destination: process.env.NEXT_PUBLIC_API_URL
          ? `${process.env.NEXT_PUBLIC_API_URL}/:path*`
          : 'http://localhost:8000/:path*',
      },
    ];
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://accounts.google.com https://apis.google.com",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https: blob:",
              "font-src 'self' data:",
              "connect-src 'self' https://backend.benchgoblins.com https://www.google-analytics.com https://analytics.google.com https://sleepercdn.com https://accounts.google.com https://oauth2.googleapis.com",
              "frame-src 'self' https://js.stripe.com https://checkout.stripe.com https://accounts.google.com",
              "object-src 'none'",
              "base-uri 'self'",
            ].join('; '),
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
