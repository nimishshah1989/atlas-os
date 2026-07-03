'use client'
import Link from 'next/link'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { Menu, X } from 'lucide-react'
import { TopNavV4 } from './TopNavV4'

// v4 redesign — flat 7-page IA + Graphite Terminal skin behind the flag.
// Pure dispatcher (no hooks) so the early branch is lint-safe; flag-off renders
// the byte-identical legacy nav below.
export function TopNav({ healthDot }: { healthDot?: React.ReactNode }) {
  if (process.env.NEXT_PUBLIC_LENS_V4 === '1') return <TopNavV4 healthDot={healthDot} />
  return <TopNavLegacy healthDot={healthDot} />
}

type SubLink = { href: string; label: string }
type Group   = { key: string; label: string; links: SubLink[] }

// Nav v6.2 (2026-05-28 IA): 5 top groups — Markets Today / Deep Dive /
// Portfolios / Admin / Reports. Per user direction:
//   - "Research" renamed to "Deep Dive"
//   - Markets RS moved into Deep Dive (was top-level)
//   - Setup + Methodology + Health collapsed into Admin
//   - Signal proposals / weight monitoring / validator / thresholds stay
//     under Admin (still LIVE per DB write activity 2026-05-25-27)
//   - Decision Policy removed (deprecated per user)
//   - Intelligence + Ask Atlas + Signals removed from nav
//   - Strategies removed from nav (Optuna-backed, dormant)
//   - Global / US pages removed from nav (will rebuild as "Global Pulse"
//     group when international markets work begins)
//   - Daily Brief moved to new Reports group (repository for future
//     daily/weekly/monthly reports)
// Only live pages. Links to unbuilt/retired features (india-pulse, markets-rs,
// calls, portfolios, setup, composite-proposals, intelligence/daily-brief) were
// pruned — re-add a link when its page.tsx exists, not before, so the nav never
// 404s.
export const GROUPS: Group[] = [
  {
    key: 'today',
    label: 'MARKETS TODAY',
    links: [
      { href: '/',                  label: 'Regime' },
    ],
  },
  {
    key: 'deepdive',
    label: 'DEEP DIVE',
    links: [
      { href: '/sectors',     label: 'Sectors' },
      { href: '/stocks',      label: 'Stocks' },
      { href: '/etfs',        label: 'ETFs' },
      { href: '/funds',       label: 'Funds' },
    ],
  },
  {
    key: 'admin',
    label: 'ADMIN',
    links: [
      { href: '/admin',            label: 'Overview & Health' },
      { href: '/admin/thresholds', label: 'Thresholds' },
    ],
  },
]

function activeGroup(pathname: string): Group {
  const byKey = (k: string) => GROUPS.find(g => g.key === k) ?? GROUPS[0]
  if (pathname.startsWith('/admin') ||
      pathname.startsWith('/methodology') ||
      pathname.startsWith('/health'))                                         return byKey('admin')
  if (pathname.startsWith('/sectors') || pathname.startsWith('/stocks') ||
      pathname.startsWith('/etfs')    || pathname.startsWith('/funds'))       return byKey('deepdive')
  return byKey('today') // markets-today is default for /
}

function TopNavLegacy({ healthDot }: { healthDot?: React.ReactNode }) {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const active = activeGroup(pathname)

  return (
    <>
      {/* Tier 1 — groups */}
      <nav className="fixed top-0 left-0 right-0 z-50 h-11 bg-paper border-b border-paper-rule flex items-center px-5 gap-1">
        <Link href="/" className="font-serif text-[15px] font-semibold text-ink-primary mr-3 shrink-0">
          Atlas
        </Link>

        {/* Desktop groups */}
        <div className="hidden md:flex items-center gap-0.5">
          {GROUPS.map(g => (
            <button
              key={g.key}
              onClick={() => {}} // group click navigates to first sub-link
              className={`px-3 py-1 rounded-sm font-sans text-[12px] font-medium transition-colors ${
                active.key === g.key
                  ? 'bg-ink-primary text-paper'
                  : 'text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/30'
              }`}
            >
              <Link href={g.links[0].href} className="block">
                {g.label}
              </Link>
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-3">
          {healthDot}
          {/* Mobile hamburger */}
          <button
            className="md:hidden p-1 text-ink-secondary hover:text-ink-primary"
            onClick={() => setMobileOpen(o => !o)}
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </nav>

      {/* Tier 2 — sub-pages of active group (desktop only) */}
      <div className="fixed top-11 left-0 right-0 z-40 h-9 bg-paper/95 border-b border-paper-rule/60 hidden md:flex items-center px-5 gap-1">
        <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mr-3">
          {active.label}
        </span>
        {active.links.map(link => {
          const isActive = pathname === link.href || (link.href !== '/' && pathname.startsWith(link.href))
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`px-2.5 py-0.5 rounded-sm font-sans text-[11px] transition-colors ${
                isActive
                  ? 'bg-teal/10 text-teal font-medium'
                  : 'text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/30'
              }`}
            >
              {link.label}
            </Link>
          )
        })}
      </div>

      {/* Mobile slide-over */}
      {mobileOpen && (
        <div className="fixed inset-0 z-[60] md:hidden">
          <div
            className="absolute inset-0 bg-ink-primary/20"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute top-0 left-0 bottom-0 w-72 bg-paper shadow-xl flex flex-col overflow-y-auto">
            <div className="flex items-center justify-between px-5 h-11 border-b border-paper-rule shrink-0">
              <span className="font-serif text-[15px] font-semibold text-ink-primary">Atlas</span>
              <button onClick={() => setMobileOpen(false)} aria-label="Close menu">
                <X size={18} className="text-ink-secondary" />
              </button>
            </div>
            <div className="flex-1 py-4 px-3">
              {GROUPS.map(g => (
                <div key={g.key} className="mb-4">
                  <div className="px-2 mb-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
                    {g.label}
                  </div>
                  {g.links.map(link => {
                    const isActive = pathname === link.href || (link.href !== '/' && pathname.startsWith(link.href))
                    return (
                      <Link
                        key={link.href}
                        href={link.href}
                        onClick={() => setMobileOpen(false)}
                        className={`block px-3 py-1.5 rounded-sm font-sans text-[13px] transition-colors ${
                          isActive
                            ? 'bg-teal/10 text-teal font-medium'
                            : 'text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/20'
                        }`}
                      >
                        {link.label}
                      </Link>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
