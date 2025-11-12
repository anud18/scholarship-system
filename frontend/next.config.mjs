/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  output: 'standalone',
  transpilePackages: ['lucide-react'],

  // SECURITY: Remove X-Powered-By header to prevent information disclosure
  poweredByHeader: false,

  // SECURITY: Strip ALL console logs in production to prevent information leakage
  // Use the centralized logger (lib/utils/logger.ts) for production-safe logging
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? true : false,
  },

  // API Proxy for development environment
  // Proxies /api/* requests to backend server
  async rewrites() {
    // Use INTERNAL_API_URL for Docker, fallback to localhost for local dev
    const apiUrl = process.env.INTERNAL_API_URL || 'http://localhost:8000';

    console.log(`[Next.js Rewrites] Proxying /api/* to ${apiUrl}/api/*`);

    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
}

export default nextConfig
