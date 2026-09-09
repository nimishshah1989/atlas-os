// src/app/layout.tsx — the shell: one serif, one light theme, the navy top bar over the page.
// The desk tool's language (globals.css): no font loading, no theme script, nothing before paint.
import type { Metadata } from 'next'
import './globals.css'
import { TopBar } from '@/components/shell/TopBar'

export const metadata: Metadata = {
  title: { default: 'Global Atlas', template: '%s — Global Atlas' },
  description: 'An adviser’s instrument for the US ETF universe and the S&P 500',
  robots: 'noindex, nofollow',
}

// EVERY ROUTE IS RENDERED ON REQUEST, exactly as it was before the board opened
// (src/lib/openAccess.ts). Until then requireUser() redirected, and a redirect makes a route
// dynamic; once the board opened nothing did, so `next build` on the box tried to PRERENDER
// /stocks at build time and met Explorer's useSearchParams() with no Suspense boundary:
//
//     ⨯ useSearchParams() should be wrapped in a suspense boundary at page "/stocks"
//     Export encountered an error on /stocks/page: /stocks, exiting the build.
//
// That error exists only at prerender, and only when a real, populated database mounts the
// explorer — which is why no local build reproduces it and CI (tsc + vitest) never saw it.
// Prerendering is also the wrong contract here: it would bake one session's data into HTML at
// deploy time. Dynamic per request, with unstable_cache under the 'eod' tag, is what the
// nightly's revalidate publishes against. Pinned by src/lib/__tests__/root-layout-dynamic.test.ts.
export const dynamic = 'force-dynamic'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-ground font-serif text-ink">
        <a href="#main" className="skip-link text-body">
          Skip to content
        </a>
        <TopBar />
        <main id="main" className="main">
          {children}
        </main>
      </body>
    </html>
  )
}
