'use client'
// src/components/shell/Rail.tsx — the primary navigation, a row in the navy top bar: the product
// mark, then the sections, the current one underlined in gold (docs/global/frontend-design.md
// § Layout). A section joins the rail with its page — a link to nothing is not navigation.
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const SECTIONS: { href: string; label: string }[] = [
  // Countries leads because it IS the front door (the FM's D1): / redirects here, so there is
  // no separate Today section to link to until one has scored movement to show.
  { href: '/countries', label: 'Countries' },
  { href: '/pulse', label: 'Pulse' },
  { href: '/themes', label: 'Themes' },
  { href: '/etfs', label: 'ETFs' },
  { href: '/stocks', label: 'Stocks' },
  { href: '/portfolios', label: 'Portfolios' },
  { href: '/methodology', label: 'Methodology' },
  { href: '/health', label: 'Health' },
]

function isActive(pathname: string, href: string): boolean {
  // `/` redirects to /countries, so the root is Countries' own section rather than a link of
  // its own — otherwise landing on the board would leave every item unlit.
  if (href === '/countries' && pathname === '/') return true
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
