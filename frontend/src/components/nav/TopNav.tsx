'use client'
import Link from 'next/link'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { Menu, X } from 'lucide-react'

type SubLink = { href: string; label: string }
type Group   = { key: string; label: string; links: SubLink[] }

const GROUPS: Group[] = [
  {
    key: 'research',
    label: 'Research',
    links: [
      { href: '/',        label: 'Regime' },
      { href: '/sectors', label: 'Sectors' },
      { href: '/stocks',  label: 'Stocks' },
      { href: '/etfs',    label: 'ETFs' },
      { href: '/funds',   label: 'Funds' },
    ],
  },
  {
    key: 'portfolio',
    label: 'Portfolio',
    links: [
      { href: '/strategies', label: 'Strategies' },
      { href: '/portfolios', label: 'Portfolios' },
    ],
  },
  {
    key: 'intelligence',
    label: 'Intelligence',
    links: [
      { href: '/intelligence',               label: 'Dashboard' },
      { href: '/intelligence/daily-brief',   label: 'Daily Brief' },
      { href: '/intelligence/agents',        label: 'Ask Atlas' },
    ],
  },
  {
    key: 'reference',
    label: 'Reference',
    links: [
      { href: '/methodology', label: 'Methodology' },
      { href: '/health',      label: 'Health' },
    ],
  },
  {
    key: 'admin',
    label: 'Admin',
    links: [
      { href: '/admin/policies',              label: 'Policies' },
      { href: '/admin/composite-proposals',   label: 'Signal Proposals' },
      { href: '/admin/validator',             label: 'Data Validator' },
      { href: '/admin/weight-performance',    label: 'Weight Monitoring' },
    ],
  },
]

function activeGroup(pathname: string): Group {
  if (pathname.startsWith('/admin'))        return GROUPS[4]
  if (pathname.startsWith('/intelligence')) return GROUPS[2]
  if (pathname.startsWith('/strategies') || pathname.startsWith('/portfolios')) return GROUPS[1]
  if (pathname.startsWith('/methodology') || pathname.startsWith('/health'))    return GROUPS[3]
  return GROUPS[0] // research is default
}

export function TopNav({ healthDot }: { healthDot?: React.ReactNode }) {
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
