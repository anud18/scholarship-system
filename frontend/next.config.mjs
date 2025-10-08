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
