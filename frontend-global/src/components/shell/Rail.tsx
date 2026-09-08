'use client'
// src/components/shell/Rail.tsx — the 232 px left rail: product mark in serif, the sections,
// Admin and the theme toggle at the foot (docs/global/frontend-design.md § Layout).
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Icon, type IconName } from './icons'
import { ThemeToggle } from './ThemeToggle'

// The sections that exist. Countries, Sectors, Baskets, Methodology and Admin join the rail with
// their pages (docs/global/frontend-design.md §4) — a link to nothing is not navigation.
const SECTIONS: { href: string; label: string; icon: IconName }[] = [
  { href: '/', label: 'Today', icon: 'today' },
  { href: '/etfs', label: 'ETFs', icon: 'etfs' },
  { href: '/stocks', label: 'Stocks', icon: 'stocks' },
]

function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}

export function Rail() {
  const pathname = usePathname() ?? '/'
  return (
    <aside className="rail" aria-label="Sections">
      <Link href="/" className="rail-mark">
        <span className="font-serif text-section text-ink">Global Atlas</span>
        <span className="rail-sub block text-meta text-ink-3">US ETFs and the S&amp;P 500</span>
      </Link>

      <nav className="rail-nav" aria-label="Primary">
        <ul>
          {SECTIONS.map(({ href, label, icon }) => (
            <li key={href}>
              <Link
                href={href}
                className="rail-link text-body"
                aria-current={isActive(pathname, href) ? 'page' : undefined}
              >
                <Icon name={icon} />
                <span>{label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <div className="rail-foot">
        <Link href="/health" className="rail-link text-body" aria-current={isActive(pathname, '/health') ? 'page' : undefined}>
          <Icon name="health" />
          <span>Health</span>
        </Link>
        <ThemeToggle />
      </div>
    </aside>
  )
}
