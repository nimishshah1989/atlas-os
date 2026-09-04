'use client'
// src/components/shell/Rail.tsx — the 232 px left rail: product mark in serif, the sections,
// Admin and the theme toggle at the foot (docs/global/frontend-design.md § Layout).
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Icon, type IconName } from './icons'
import { ThemeToggle } from './ThemeToggle'

const SECTIONS: { href: string; label: string; icon: IconName }[] = [
  { href: '/', label: 'Today', icon: 'today' },
  { href: '/etfs', label: 'ETFs', icon: 'etfs' },
  { href: '/countries', label: 'Countries', icon: 'countries' },
  { href: '/sectors', label: 'Sectors', icon: 'sectors' },
  { href: '/stocks', label: 'Stocks', icon: 'stocks' },
  { href: '/baskets', label: 'Baskets', icon: 'baskets' },
  { href: '/methodology', label: 'Methodology', icon: 'methodology' },
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
        <Link
          href="/admin/thresholds"
          className="rail-link text-body"
          aria-current={pathname.startsWith('/admin') ? 'page' : undefined}
        >
          <Icon name="admin" />
          <span>Admin</span>
        </Link>
        <ThemeToggle />
      </div>
    </aside>
  )
}
