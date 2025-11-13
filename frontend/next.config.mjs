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

  // Webpack optimization for development performance
  webpack: (config, { dev, isServer }) => {
    if (dev) {
      // Optimize development builds for faster compilation and smaller chunks
      config.optimization = {
        ...config.optimization,
        // Disable module concatenation in dev for faster rebuilds
        concatenateModules: false,
        // Minimize chunk overhead
        removeAvailableModules: false,
        removeEmptyChunks: false,
        // Keep default splitChunks for code splitting
      };

      // Increase chunk loading timeout to handle large chunks
      if (!isServer) {
        config.output = {
          ...config.output,
          // Increase timeout from default 120s to 300s (5 minutes)
          chunkLoadTimeout: 300000,
        };
      }
    }

    return config;
  },

  // Enable experimental features for better performance
  experimental: {
    // Use worker threads for webpack builds (faster compilation)
    webpackBuildWorker: true,
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
