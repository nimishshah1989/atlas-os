// frontend/src/components/v6/ScreenerClient.tsx
// Client component for /v6/screening.
//
// Architecture:
//   - Filter state lives in URL searchParams (shareable links).
//   - Filter changes call router.replace() which triggers RSC re-render.
//   - The RSC page passes the filtered `stocks` array as a prop — no
//     client-side fetch needed (server does the SQL).
//   - Results are rendered via StocksListV6 (reuse existing virtualized table).
//
// v6.0 scope: stocks only.

'use client'

import { useCallback, useState, useTransition } from 'react'
import { useRouter, usePathname, useSearchParams } from 'next/navigation'

import { ScreenerFilterBuilder } from '@/components/v6/ScreenerFilterBuilder'
import { StocksListV6 } from '@/components/v6/StocksListV6'
import { filterToParams, paramsToFilter, type ScreenFilter } from '@/lib/queries/v6/screen'
import type { StockV6Row } from '@/lib/queries/v6/stocks'

// ── Props ─────────────────────────────────────────────────────────────────────

export interface ScreenerClientProps {
  /** Pre-filtered stocks from the RSC layer. */
  stocks: StockV6Row[]
  /** Currently-applied filter (decoded from URL by the page shell). */
  initialFilter: ScreenFilter
  /** Held iids array (from B.1 getHeldIidSet). */
  heldIids: string[]
  /** Snapshot date used for the query. */
  snapshotDate: string
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ScreenerClient({
  stocks,
  initialFilter,
  heldIids,
  snapshotDate,
}: ScreenerClientProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isPending, startTransition] = useTransition()

  // Local filter state mirrors URL; changes trigger URL update → RSC re-fetch.
  const [filter, setFilter] = useState<ScreenFilter>(initialFilter)

  const applyFilter = useCallback(
    (next: ScreenFilter) => {
      setFilter(next)
      const params = filterToParams(next)
      const urlParams = new URLSearchParams(searchParams.toString())

      // Clear all screener params first, then set the new ones.
      const screenerKeys = [
        'ic_min', 'ic_max', 'sectors', 'sector_rank_max', 'drift_statuses',
        'rs_pct_min', 'in_book', 'actions', 'cap_tiers',
      ]
      screenerKeys.forEach(k => urlParams.delete(k))
      Object.entries(params).forEach(([k, v]) => urlParams.set(k, v))

      startTransition(() => {
        router.replace(
          `${pathname}?${urlParams.toString()}`,
          { scroll: false },
        )
      })
    },
    [router, pathname, searchParams],
  )

  const resetFilter = useCallback(() => {
    setFilter({})
    const urlParams = new URLSearchParams()
    startTransition(() => {
      router.replace(pathname, { scroll: false })
    })
    void urlParams // suppress unused variable lint
  }, [router, pathname])

  const activeFilterCount = Object.keys(filter).filter(k => {
    const v = filter[k as keyof ScreenFilter]
    if (Array.isArray(v)) return v.length > 0
    return v != null
  }).length

  return (
    <div className="flex h-full min-h-0" data-testid="screener-client">
      {/* ── Left rail: filter panel ─────────────────────────────────────── */}
      <div className="w-64 shrink-0 flex flex-col border-r border-paper-rule overflow-y-auto">
        <ScreenerFilterBuilder
          filter={filter}
          onFilterChange={applyFilter}
          onReset={resetFilter}
          resultCount={stocks.length}
          loading={isPending}
        />
      </div>

      {/* ── Main panel: results table ───────────────────────────────────── */}
      <div className="flex-1 min-w-0 overflow-auto">
        {/* Results header */}
        <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-3">
          <span className="font-sans text-sm text-ink-primary font-semibold">
            Results
          </span>
          {activeFilterCount > 0 && (
            <span
              className="font-sans text-[11px] text-teal bg-teal/10 border border-teal/30 px-2 py-0.5 rounded-full"
              data-testid="active-filter-badge"
            >
              {activeFilterCount} filter{activeFilterCount > 1 ? 's' : ''} active
            </span>
          )}
          {isPending && (
            <span className="font-sans text-[11px] text-ink-tertiary" data-testid="loading-indicator">
              Updating…
            </span>
          )}
          <span className="ml-auto font-mono text-[11px] text-ink-tertiary">
            {stocks.length} stocks · as of {snapshotDate}
          </span>
        </div>

        {/* Empty state */}
        {stocks.length === 0 ? (
          <div
            className="px-6 py-16 text-center"
            data-testid="screener-empty-state"
            role="status"
            aria-live="polite"
          >
            <p className="font-sans text-sm text-ink-secondary mb-2">
              No stocks match the current filters.
            </p>
            <p className="font-sans text-xs text-ink-tertiary mb-4">
              Try widening the filter criteria.
            </p>
            <button
              type="button"
              onClick={resetFilter}
              className="font-sans text-xs text-teal hover:underline"
            >
              Reset all filters
            </button>
          </div>
        ) : (
          <div
            aria-live="polite"
            aria-busy={isPending}
            data-testid="screener-results"
            className={isPending ? 'opacity-60 transition-opacity' : ''}
          >
            <StocksListV6
              stocks={stocks}
              heldIids={heldIids}
              snapshotDate={snapshotDate}
            />
          </div>
        )}
      </div>
    </div>
  )
}

// ── URL helper (used by the page shell to decode incoming params) ─────────────

/**
 * Decode search params from a Next.js page searchParams prop into a ScreenFilter.
 * Safe to call on server side (no `useSearchParams` hook).
 */
export function decodeScreenerParams(
  searchParams: Record<string, string | string[] | undefined>,
): ScreenFilter {
  const flat: Record<string, string> = {}
  for (const [k, v] of Object.entries(searchParams)) {
    if (typeof v === 'string') flat[k] = v
    else if (Array.isArray(v) && v.length > 0) flat[k] = v[v.length - 1]
  }
  return paramsToFilter(flat)
}
