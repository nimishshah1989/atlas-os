/** @type {import('next').NextConfig} */
const nextConfig = {
  // Served under a sub-path on the box (nginx -> atlas.jslwealth.in/global);
  // empty elsewhere, so the same build runs at the root.
  basePath: process.env.ATLAS_GLOBAL_BASE_PATH || undefined,
  reactStrictMode: true,
  // Behind nginx, Next compares a Server Action's Origin against the Host it thinks it serves,
  // and the proxy makes those differ. The sign-in form IS a Server Action (src/app/login/
  // actions.ts), so without this entry the first thing any reader does fails. The India board
  // carries the identical entry for the identical reason (frontend/next.config.js).
  experimental: { serverActions: { allowedOrigins: ['atlas.jslwealth.in'] } },
  // Typed routes stay off: the route inventory (docs/global/frontend-design.md §4) lands over
  // several phases and the rail already links to pages that arrive later.
  // No `typescript.ignoreBuildErrors` and no `eslint.ignoreDuringBuilds` — a type or lint error
  // fails the build here, not at request time on Vercel.
}

module.exports = nextConfig
