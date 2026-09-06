// src/components/shell/TopBar.tsx — global search (⌘K) and the "as of" stamp with its freshness
// dot. Server component: the stamp reads the database; the search box is a client island that
// reads the URL, so it sits in a Suspense boundary for the statically rendered pages.
import { Suspense } from 'react'
import { FreshnessStamp } from '@/components/ui/FreshnessStamp'
import { Icon } from './icons'
import { SearchBox } from './SearchBox'

export function TopBar() {
  return (
    <header className="topbar">
      <Suspense
        fallback={
          <label className="search text-body">
            <Icon name="search" />
            <input type="search" readOnly placeholder="Search symbol or name" aria-label="Search symbol or name" />
            <kbd aria-hidden="true">⌘K</kbd>
          </label>
        }
      >
        <SearchBox />
      </Suspense>
      <Suspense fallback={<span className="text-meta text-ink-3">Checking freshness</span>}>
        <FreshnessStamp />
      </Suspense>
    </header>
  )
}
