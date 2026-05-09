// frontend/src/components/sectors/SectorDeepDiveTabs.tsx
'use client'
import Link from 'next/link'
import type { TimeRange } from '@/lib/time-range'

type Tab = 'overview' | 'stocks'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'stocks',   label: 'Stocks' },
]

export function SectorDeepDiveTabs({
  sectorName,
  activeTab,
  range,
}: {
  sectorName: string
  activeTab: Tab
  range: TimeRange
}) {
  return (
    <div className="sticky top-[150px] bg-paper border-b border-paper-rule z-20">
      <div className="px-6">
        <div className="flex gap-1" role="tablist" aria-label="Sector deep dive tabs">
          {TABS.map(tab => {
            const isActive = tab.id === activeTab
            const params = new URLSearchParams()
            if (tab.id !== 'overview') params.set('tab', tab.id)
            params.set('range', range)
            const href = `/sectors/${encodeURIComponent(sectorName)}${params.toString() ? `?${params.toString()}` : ''}`
            return (
              <Link
                key={tab.id}
                href={href}
                role="tab"
                aria-selected={isActive}
                className={`relative px-4 py-3 font-sans text-sm transition-colors ${
                  isActive
                    ? 'text-ink-primary font-semibold'
                    : 'text-ink-tertiary hover:text-ink-secondary'
                }`}
              >
                {tab.label}
                {isActive && (
                  <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-teal" aria-hidden="true" />
                )}
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  )
}
