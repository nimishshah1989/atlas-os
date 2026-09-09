// src/components/shell/TopBar.tsx — the navy bar: the product mark and the sections (Rail), global
// search (⌘K) and, at the right in `.who`, the "as of" stamp with its freshness dot. Server
// component: the stamp reads the database; the search box is a client island that reads the URL,
// so it sits in a Suspense boundary.
import { Suspense } from 'react'
import { FreshnessStamp } from '@/components/ui/FreshnessStamp'
import { Icon } from './icons'
import { Rail } from './Rail'
import { SearchBox } from './SearchBox'

export function TopBar() {
  return (
    <header className="topbar">
      <Rail />
      <Suspense
        fallback={
          <label className="search">
            <Icon name="search" />
            <input type="search" readOnly placeholder="Search symbol or name" aria-label="Search symbol or name" />
            <kbd aria-hidden="true">⌘K</kbd>
          </label>
        }
      >
        <SearchBox />
      </Suspense>
      <span className="who">
        <Suspense fallback={<span>Checking freshness</span>}>
          <FreshnessStamp />
        </Suspense>
      </span>
    </header>
  )
}
