// src/components/shell/TopBar.tsx — global search (⌘K, placeholder until the ETF explorer lands)
// and the "as of" stamp with its freshness dot. Server component: the stamp reads the database.
import { Suspense } from 'react'
import { FreshnessStamp } from '@/components/ui/FreshnessStamp'
import { Icon } from './icons'

export function TopBar() {
  return (
    <header className="topbar">
      <label className="search text-body">
        <Icon name="search" />
        <input
          type="search"
          readOnly
          placeholder="Search symbols, countries, sectors"
          aria-label="Search (arrives with the ETF explorer)"
          title="Search arrives with the ETF explorer"
        />
        <kbd aria-hidden="true">⌘K</kbd>
      </label>
      <Suspense fallback={<span className="text-meta text-ink-3">Checking freshness</span>}>
        <FreshnessStamp />
      </Suspense>
    </header>
  )
}
