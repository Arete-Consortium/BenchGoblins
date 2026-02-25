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
};

module.exports = nextConfig;
