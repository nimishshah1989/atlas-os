/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Typed routes stay off: the route inventory (docs/global/frontend-design.md §4) lands over
  // several phases and the rail already links to pages that arrive later.
  // No `typescript.ignoreBuildErrors` and no `eslint.ignoreDuringBuilds` — a type or lint error
  // fails the build here, not at request time on Vercel.
}

module.exports = nextConfig
