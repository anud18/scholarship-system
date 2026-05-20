/** @type {import('next').NextConfig} */
const nextConfig = {
  // SECURITY / PRODUCTION-READINESS: Surface ESLint warnings and TypeScript
  // errors at build time so they fail the deploy pipeline instead of
  // silently shipping. The repo's CI also runs `tsc --noEmit` in the
  // "Verify OpenAPI Types are Up-to-Date" workflow as a backstop, but
  // these flags add a second guardrail directly to the `next build` path
  // (used by the "Build Frontend with Generated Types" CI job).
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    ignoreBuildErrors: false,
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

      // Speed up development builds
      config.cache = {
        type: 'filesystem',
        compression: false, // Disable compression for faster caching
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

  // Experimental features for better performance
  experimental: {
    // Use worker threads for webpack builds (faster compilation)
    webpackBuildWorker: true,
    // Faster dev builds via package-level import optimization
    optimizePackageImports: ['lucide-react', '@radix-ui/react-icons'],
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
