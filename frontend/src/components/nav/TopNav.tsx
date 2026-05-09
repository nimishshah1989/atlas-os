// src/components/nav/TopNav.tsx
import Link from 'next/link'
import { Suspense } from 'react'
import { HealthDot } from './HealthDot'

const NAV_LINKS = [
  { href: '/',               label: 'Regime' },
  { href: '/sectors',        label: 'Sectors' },
  { href: '/stocks',         label: 'Stocks' },
  { href: '/etfs',           label: 'ETFs' },
  { href: '/funds',          label: 'Funds' },
  { href: '/strategies',     label: 'Strategies' },
  { href: '/health',         label: 'Health' },
  { href: '/admin/policies', label: 'Policies' },
]

export function TopNav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-14 bg-paper border-b border-paper-rule flex items-center px-6 gap-6">
      <span className="font-serif text-base font-semibold text-ink-primary mr-2">
        Atlas
      </span>

      {NAV_LINKS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className="font-sans text-sm text-ink-secondary hover:text-ink-primary transition-colors"
        >
          {label}
        </Link>
      ))}

      <div className="ml-auto flex items-center gap-3">
        <Suspense fallback={<span className="inline-block w-2 h-2 rounded-full bg-paper-rule" />}>
          <HealthDot />
        </Suspense>
        {/* GlobalSearch added later */}
      </div>
    </nav>
  )
}
