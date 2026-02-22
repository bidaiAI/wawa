/** @type {import('next').NextConfig} */
const nextConfig = {
  // Vercel deployment: standalone output for minimal Docker/serverless
  output: 'standalone',

  env: {
    // AI instance API — MUST set NEXT_PUBLIC_API_URL in Vercel env vars for production
    // Self-hosted forks: set to your VPS URL e.g. https://api.yourdomain.com
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '',
    // Platform API (mortal-ai.net orchestrator)
    NEXT_PUBLIC_PLATFORM_API_URL: process.env.NEXT_PUBLIC_PLATFORM_API_URL || 'https://api.mortal-ai.net',
  },

  // Turbopack (Next.js 16 default) — empty config to acknowledge it
  turbopack: {},

  // Web3 compatibility: wagmi/viem need these Node polyfill fallbacks
  // (webpack config used when explicitly building with --webpack flag)
  webpack: (config) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      fs: false,
      net: false,
      tls: false,
    }
    config.externals.push('pino-pretty', 'lokijs', 'encoding')
    return config
  },

  // Security headers (complement vercel.json headers)
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-XSS-Protection', value: '1; mode=block' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ]
  },

  // Disable X-Powered-By header (security)
  poweredByHeader: false,
}

module.exports = nextConfig
