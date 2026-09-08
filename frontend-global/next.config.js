/** @type {import('next').NextConfig} */
const nextConfig = {
  // Served under a sub-path on the box (nginx -> atlas.jslwealth.in/global);
  // empty elsewhere, so the same build runs at the root.
  basePath: process.env.ATLAS_GLOBAL_BASE_PATH || undefined,
  reactStrictMode: true,
  // Behind nginx, Next compares a Server Action's Origin against the Host it thinks it serves,
  // and the proxy makes those differ. The sign-in form IS a Server Action (src/app/login/
  // actions.ts), so an origin missing here means the FIRST thing any reader does fails —
  // silently. The button does nothing, no error reaches the page, and nothing lands in the
  // server log. The India board carries the identical entry for the identical reason
  // (frontend/next.config.js).
  //
  // Every hostname this board is reachable by has to be listed, and this list fell behind the
  // deployment twice over:
  //   global.jslwealth.in  the board's own host, since it moved off the atlas sub-path
  //                        (docs/global/deploy-subdomain.md). Its absence is what made the
  //                        sign-in button dead on the real domain.
  //   localhost:8080       an SSH tunnel to the box, which is how the board gets looked at
  //                        before DNS and TLS exist. The browser sends Origin
  //                        http://localhost:8080 and Next rejected it.
  //   atlas.jslwealth.in   kept: the superseded sub-path route still resolves, and dropping it
  //                        would break that deployment silently rather than loudly.
  experimental: {
    serverActions: {
      allowedOrigins: ['global.jslwealth.in', 'atlas.jslwealth.in', 'localhost:8080'],
    },
  },
  // Typed routes stay off: the route inventory (docs/global/frontend-design.md §4) lands over
  // several phases and the rail already links to pages that arrive later.
  // No `typescript.ignoreBuildErrors` and no `eslint.ignoreDuringBuilds` — a type or lint error
  // fails the build here, not at request time on Vercel.
}

module.exports = nextConfig
