'use client'
import { ColumnToggle } from '@/components/ui/ColumnToggle'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { OPTIONAL_COLS, CHIPS, type FilterChip } from './screener-utils'

interface ScreenerFilterPanelProps {
  search: string
  sectorFilter: string
  chip: FilterChip
  sectorOptions: string[]
  pagedRows: StockRowWithSector[]
  filtered: StockRowWithSector[]
  stocks: StockRowWithSector[]
  visibleCols: Set<string>
  onSearch: (v: string) => void
  onSectorFilter: (v: string) => void
  onChip: (v: FilterChip) => void
  onVisibleColsChange: (cols: Set<string>) => void
  onClearFilters: () => void
}

export function ScreenerFilterPanel({
  search, sectorFilter, chip, sectorOptions, pagedRows, filtered, stocks,
  visibleCols, onSearch, onSectorFilter, onChip, onVisibleColsChange,
}: ScreenerFilterPanelProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        placeholder="Search symbol or company..."
        value={search}
        onChange={e => onSearch(e.target.value)}
        className="px-3 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper placeholder:text-ink-tertiary focus:outline-none focus:ring-1 focus:ring-teal/50 w-56"
      />
      <select
        value={sectorFilter}
        onChange={e => onSectorFilter(e.target.value)}
        aria-label="Filter by sector"
        className="px-2 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper focus:outline-none focus:ring-1 focus:ring-teal/50"
      >
        {sectorOptions.map(s => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <div className="flex flex-wrap gap-1.5">
        {CHIPS.map(c => (
          <button
            key={c.key}
            type="button"
            aria-pressed={chip === c.key}
            onClick={() => onChip(c.key)}
            className={`px-2.5 py-1 min-h-[44px] rounded-sm font-sans text-xs font-medium transition-colors ${
              chip === c.key
                ? 'bg-teal text-paper'
                : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <span className="font-sans text-xs text-ink-tertiary whitespace-nowrap">
          {pagedRows.length} of {filtered.length} shown ({stocks.length} total)
        </span>
        <ColumnToggle columns={OPTIONAL_COLS} visible={visibleCols} onChange={onVisibleColsChange} />
      </div>
    </div>
  )
}
