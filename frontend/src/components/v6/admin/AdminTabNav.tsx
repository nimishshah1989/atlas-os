'use client'
// AdminTabNav — the three Admin sub-tabs. Highlights the active route. Client so it can read
// the pathname; the tabs themselves are real routes (each fetches only its own data).
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const TABS = [
  { href: '/admin/methodology', label: 'Methodology' },
  { href: '/admin/thresholds', label: 'Thresholds' },
  { href: '/admin/data-status', label: 'Data status' },
]

export function AdminTabNav() {
  const pathname = usePathname()
  return (
    <div className="mb-6 flex items-center gap-1 border-b border-edge-rule">
      {TABS.map((t) => {
        const active = pathname === t.href || pathname.startsWith(t.href + '/')
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`relative px-3.5 py-2 font-sans text-[13px] font-medium transition-colors ${
              active ? 'text-txt-1' : 'text-txt-3 hover:text-txt-1'
            }`}
          >
            {t.label}
            {active && <span className="absolute inset-x-3 -bottom-px h-[2px] rounded-full bg-brand" />}
          </Link>
        )
      })}
    </div>
  )
}
