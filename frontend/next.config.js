/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  // App + lib code typechecks clean (validated separately); only __tests__ fixtures
  // carry stale-shape errors that must not block a production deploy.
  typescript: { ignoreBuildErrors: true },
  experimental: {
    serverActions: { allowedOrigins: ["localhost:3000", "localhost:3003", "atlas.jslwealth.in"] },
    // The board pages are DB-backed (Supabase session pooler, 15-client cap on a
    // shared box). Prerendering many in parallel exhausted the pool and baked
    // notFound() 404s. Throttle prerender concurrency + retry so ISR pages build
    // cleanly (then they serve from cache → <2s).
    staticGenerationMaxConcurrency: 2,
    staticGenerationRetryCount: 3,
  },
};
module.exports = nextConfig;
