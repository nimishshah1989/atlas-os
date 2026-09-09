'use client'
// src/components/shell/Rail.tsx — the primary navigation, a row in the navy top bar: the product
// mark, then the sections, the current one underlined in gold (docs/global/frontend-design.md
// § Layout). A section joins the rail with its page — a link to nothing is not navigation.
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const SECTIONS: { href: string; label: string }[] = [
  { href: '/', label: 'Today' },
  { href: '/countries', label: 'Countries' },
  { href: '/etfs', label: 'ETFs' },
  { href: '/stocks', label: 'Stocks' },
  { href: '/health', label: 'Health' },
  // PORTFOLIOS HOOK — once src/app/portfolios exists, add: { href: '/portfolios', label: 'Portfolios' },
]

function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}

export function Rail() {
  const pathname = usePathname() ?? '/'
  return (
    <nav className="rail" aria-label="Primary">
      <Link href="/" className="rail-mark">
        Global Atlas
      </Link>
      <ul className="rail-nav">
        {SECTIONS.map(({ href, label }) => (
          <li key={href}>
            <Link href={href} className="rail-link" aria-current={isActive(pathname, href) ? 'page' : undefined}>
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
