// Two faces of the same board: the engine-run books, and the FM's weekly document.
import Link from 'next/link'

const TABS = [
  { href: '/portfolios', key: 'books', label: 'Books' },
  { href: '/portfolios/maal', key: 'maal', label: 'MaaL Process' },
] as const

export function PortfolioTabs({ active }: { active: 'books' | 'maal' }) {
  return (
    <nav className="flex gap-6 border-b border-edge-hair" aria-label="Portfolios sections">
      {TABS.map((t) => (
        <Link
          key={t.key}
          href={t.href}
          aria-current={t.key === active ? 'page' : undefined}
          className={`-mb-px border-b-2 px-0.5 pb-2.5 font-sans text-[13px] no-underline transition-colors ${
            t.key === active
              ? 'border-brand font-semibold text-txt-1'
              : 'border-transparent text-txt-3 hover:text-txt-2'
          }`}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  )
}
