'use client'
// Atlas v4 nav — flat 7-page IA (§2), Graphite Terminal skin. Replaces the
// 2-tier group nav when LENS_V4 is on. India-Pulse retired (its breadth table
// moved to Market Pulse). Admin's sub-pages (Methodology · Data Health ·
// Thresholds · IC Optimization) live on the Admin page itself for now.
import Link from 'next/link'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { Menu, X } from 'lucide-react'
import { ThemeToggle } from '@/components/v4/ui/ThemeToggle'

type NavItem = { href: string; label: string; exact?: boolean }

export const NAV_V4: NavItem[] = [
  { href: '/', label: 'Market Pulse', exact: true },
  { href: '/sectors', label: 'Sector View' },
  { href: '/stocks', label: 'Stocks' },
  { href: '/etfs', label: 'ETF' },
  { href: '/funds', label: 'Funds' },
  { href: '/admin', label: 'Admin' },
]

function isActive(pathname: string, item: NavItem): boolean {
  return item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(item.href + '/') || pathname === item.href
}

export function TopNavV4({ healthDot }: { healthDot?: React.ReactNode }) {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  return (
    <>
      <nav className="fixed inset-x-0 top-0 z-50 flex h-12 items-center gap-1 border-b border-edge-rule bg-surface-base/95 px-5 backdrop-blur">
        <Link href="/" className="mr-4 flex shrink-0 items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-brand" style={{ boxShadow: '0 0 8px -1px var(--color-brand)' }} />
          <span className="font-display text-[16px] font-bold tracking-tight text-txt-1">Atlas</span>
        </Link>

        <div className="hidden items-center gap-0.5 md:flex">
          {NAV_V4.map((item) => {
            const active = isActive(pathname, item)
            return (
              <Link
                key={item.href}
                href={item.href}
                prefetch={false}
                className={`relative rounded-tile px-3 py-1.5 font-sans text-[12px] font-medium transition-colors ${
                  active ? 'text-txt-1' : 'text-txt-3 hover:text-txt-1'
                }`}
              >
                {item.label}
                {active && <span className="absolute inset-x-3 -bottom-px h-[2px] rounded-full bg-brand" />}
              </Link>
            )
          })}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <ThemeToggle />
          {healthDot}
          <button
            className="p-1 text-txt-3 hover:text-txt-1 md:hidden"
            onClick={() => setOpen((o) => !o)}
            aria-label="Toggle menu"
          >
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </nav>

      {open && (
        <div className="fixed inset-0 z-[60] md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 flex-col overflow-y-auto border-r border-edge-rule bg-surface-panel">
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-edge-rule px-5">
              <span className="font-display text-[16px] font-bold text-txt-1">Atlas</span>
              <button onClick={() => setOpen(false)} aria-label="Close menu"><X size={18} className="text-txt-3" /></button>
            </div>
            <div className="flex-1 p-3">
              {NAV_V4.map((item) => {
                const active = isActive(pathname, item)
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={`block rounded-tile px-3 py-2 font-sans text-[13px] transition-colors ${
                      active ? 'bg-surface-raised text-txt-1' : 'text-txt-2 hover:bg-surface-raised hover:text-txt-1'
                    }`}
                  >
                    {item.label}
                  </Link>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
