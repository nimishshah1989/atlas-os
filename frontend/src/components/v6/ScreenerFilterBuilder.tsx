// frontend/src/components/v6/ScreenerFilterBuilder.tsx
// Filter panel for the /v6/screening page.
// Renders all 8 filter dimensions from the D.11 spec.
// All state is lifted to the parent ScreenerClient via onFilterChange.

'use client'

import type { ScreenFilter } from '@/lib/queries/v6/screen-filter'

// ── Constants ─────────────────────────────────────────────────────────────────

export const SECTOR_OPTIONS = [
  'Automobile', 'Banking', 'Capital Goods', 'Cement', 'Chemicals',
  'Consumer Durables', 'Consumer Staples', 'Energy', 'FMCG', 'Healthcare',
  'IT', 'Infrastructure', 'Insurance', 'Media', 'Metals & Mining',
  'Pharma', 'Real Estate', 'Retail', 'Telecom', 'Utilities',
]

const DRIFT_STATUS_OPTIONS: Array<{ value: 'healthy' | 'drift_warn' | 'deprecated'; label: string }> = [
  { value: 'healthy',    label: 'Healthy' },
  { value: 'drift_warn', label: 'Drift warn' },
  { value: 'deprecated', label: 'Deprecated' },
]

const ACTION_OPTIONS: Array<{ value: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'; label: string }> = [
  { value: 'POSITIVE', label: 'BUY' },
  { value: 'NEUTRAL',  label: 'WATCH' },
  { value: 'NEGATIVE', label: 'AVOID' },
]

const CAP_TIER_OPTIONS: Array<{ value: 'Small' | 'Mid' | 'Large'; label: string }> = [
  { value: 'Large', label: 'Large' },
  { value: 'Mid',   label: 'Mid' },
  { value: 'Small', label: 'Small' },
]

const SECTOR_RANK_OPTIONS = [
  { value: 1,  label: 'Top 1' },
  { value: 3,  label: 'Top 3' },
  { value: 5,  label: 'Top 5' },
  { value: 10, label: 'Top 10' },
]

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ScreenerFilterBuilderProps {
  filter: ScreenFilter
  onFilterChange: (f: ScreenFilter) => void
  onReset: () => void
  resultCount: number
  loading: boolean
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary mb-1.5">
      {children}
    </p>
  )
}

function ChipGroup<T extends string>({
  options,
  selected,
  onChange,
  testIdPrefix,
}: {
  options: Array<{ value: T; label: string }>
  selected: T[]
  onChange: (next: T[]) => void
  testIdPrefix: string
}) {
  const toggle = (v: T) => {
    if (selected.includes(v)) onChange(selected.filter(x => x !== v))
    else onChange([...selected, v])
  }
  return (
    <div className="flex items-center gap-1 flex-wrap" role="group">
      {options.map(opt => (
        <button
          key={opt.value}
          type="button"
          onClick={() => toggle(opt.value)}
          data-testid={`${testIdPrefix}-${opt.value}`}
          aria-pressed={selected.includes(opt.value)}
          className={[
            'px-2.5 py-1 rounded-[2px] font-sans text-[11px] border transition-colors',
            selected.includes(opt.value)
              ? 'bg-teal/10 text-teal border-teal/30'
              : 'bg-paper text-ink-secondary border-paper-rule hover:bg-paper-rule/20',
          ].join(' ')}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

function RangeSlider({
  id,
  label,
  min,
  max,
  step,
  value,
  onChange,
  format,
}: {
  id: string
  label: string
  min: number
  max: number
  step: number
  value: number | undefined
  onChange: (v: number | undefined) => void
  format: (v: number) => string
}) {
  const resolved = value ?? min
  const active = value != null

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label htmlFor={id} className="font-sans text-[11px] text-ink-secondary">
          {label}
          {active && (
            <span className="ml-1.5 font-mono text-[11px] text-teal">{format(resolved)}</span>
          )}
        </label>
        {active && (
          <button
            type="button"
            onClick={() => onChange(undefined)}
            className="font-sans text-[10px] text-ink-tertiary hover:text-signal-neg transition-colors"
            aria-label={`Clear ${label} filter`}
          >
            Clear
          </button>
        )}
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={resolved}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-teal"
        aria-valuenow={resolved}
        aria-valuemin={min}
        aria-valuemax={max}
        data-testid={id}
      />
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function ScreenerFilterBuilder({
  filter,
  onFilterChange,
  onReset,
  resultCount,
  loading,
}: ScreenerFilterBuilderProps) {
  const set = <K extends keyof ScreenFilter>(k: K, v: ScreenFilter[K]) =>
    onFilterChange({ ...filter, [k]: v })

  const toggleSector = (sector: string) => {
    const current = filter.sectors ?? []
    const next = current.includes(sector)
      ? current.filter(s => s !== sector)
      : [...current, sector]
    set('sectors', next.length > 0 ? next : undefined)
  }

  const toggleInBook = () => {
    if (filter.in_book === true) set('in_book', false)
    else if (filter.in_book === false) set('in_book', undefined)
    else set('in_book', true)
  }

  const inBookLabel =
    filter.in_book === true ? 'In my book' :
    filter.in_book === false ? 'Not in book' :
    'Book (any)'

  const hasFilters = Object.keys(filter).some(k => {
    const v = filter[k as keyof ScreenFilter]
    if (Array.isArray(v)) return v.length > 0
    return v != null
  })

  return (
    <aside
      className="border-r border-paper-rule bg-paper h-full overflow-y-auto"
      aria-label="Screener filters"
      data-testid="screener-filter-builder"
    >
      <div className="px-4 pt-4 pb-3 border-b border-paper-rule flex items-center justify-between">
        <h2 className="font-sans text-sm font-semibold text-ink-primary">Filters</h2>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-ink-tertiary" data-testid="result-count">
            {loading ? '…' : `${resultCount} stocks`}
          </span>
          {hasFilters && (
            <button
              type="button"
              onClick={onReset}
              className="font-sans text-[11px] text-teal hover:underline"
              data-testid="reset-filters"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      <div className="px-4 py-4 space-y-5">

        {/* Cap Tier */}
        <div>
          <SectionLabel>Cap Tier</SectionLabel>
          <ChipGroup
            options={CAP_TIER_OPTIONS}
            selected={filter.cap_tiers ?? []}
            onChange={v => set('cap_tiers', v.length > 0 ? v : undefined)}
            testIdPrefix="cap-tier"
          />
        </div>

        {/* Action */}
        <div>
          <SectionLabel>Action</SectionLabel>
          <ChipGroup
            options={ACTION_OPTIONS}
            selected={filter.actions ?? []}
            onChange={v => set('actions', v.length > 0 ? v : undefined)}
            testIdPrefix="action"
          />
        </div>

        {/* Drift Status */}
        <div>
          <SectionLabel>Cell drift status</SectionLabel>
          <ChipGroup
            options={DRIFT_STATUS_OPTIONS}
            selected={filter.drift_statuses ?? []}
            onChange={v => set('drift_statuses', v.length > 0 ? v : undefined)}
            testIdPrefix="drift"
          />
        </div>

        {/* RS Percentile */}
        <div>
          <SectionLabel>RS Percentile (min)</SectionLabel>
          <RangeSlider
            id="rs-pct-min"
            label="RS %ile ≥"
            min={0}
            max={100}
            step={5}
            value={filter.rs_pct_min}
            onChange={v => set('rs_pct_min', v)}
            format={v => `${v}`}
          />
        </div>

        {/* IC Range */}
        <div className="space-y-3">
          <SectionLabel>IC Range</SectionLabel>
          <RangeSlider
            id="ic-min"
            label="IC min"
            min={-100}
            max={100}
            step={5}
            value={filter.ic_min != null ? Math.round(filter.ic_min * 100) : undefined}
            onChange={v => set('ic_min', v != null ? v / 100 : undefined)}
            format={v => `${v > 0 ? '+' : ''}${v}`}
          />
          <RangeSlider
            id="ic-max"
            label="IC max"
            min={-100}
            max={100}
            step={5}
            value={filter.ic_max != null ? Math.round(filter.ic_max * 100) : undefined}
            onChange={v => set('ic_max', v != null ? v / 100 : undefined)}
            format={v => `${v > 0 ? '+' : ''}${v}`}
          />
        </div>

        {/* Sector Rank */}
        <div>
          <SectionLabel>Sector rank (top-N)</SectionLabel>
          <div className="flex items-center gap-1 flex-wrap" role="group" aria-label="Sector rank filter">
            {SECTOR_RANK_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => set('sector_rank_max', filter.sector_rank_max === opt.value ? undefined : opt.value)}
                data-testid={`sector-rank-${opt.value}`}
                aria-pressed={filter.sector_rank_max === opt.value}
                className={[
                  'px-2.5 py-1 rounded-[2px] font-sans text-[11px] border transition-colors',
                  filter.sector_rank_max === opt.value
                    ? 'bg-teal/10 text-teal border-teal/30'
                    : 'bg-paper text-ink-secondary border-paper-rule hover:bg-paper-rule/20',
                ].join(' ')}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Sectors */}
        <div>
          <SectionLabel>
            Sectors
            {(filter.sectors?.length ?? 0) > 0 && (
              <span className="ml-1 normal-case font-normal text-teal">
                ({filter.sectors!.length} selected)
              </span>
            )}
          </SectionLabel>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Sector multi-select">
            {SECTOR_OPTIONS.map(sec => {
              const active = filter.sectors?.includes(sec) ?? false
              return (
                <button
                  key={sec}
                  type="button"
                  onClick={() => toggleSector(sec)}
                  data-testid={`sector-${sec}`}
                  aria-pressed={active}
                  className={[
                    'px-2 py-0.5 rounded-[2px] font-sans text-[10px] border transition-colors',
                    active
                      ? 'bg-teal/10 text-teal border-teal/30'
                      : 'bg-paper text-ink-tertiary border-paper-rule hover:bg-paper-rule/20',
                  ].join(' ')}
                >
                  {sec}
                </button>
              )
            })}
          </div>
        </div>

        {/* In/out book */}
        <div>
          <SectionLabel>Portfolio book</SectionLabel>
          <button
            type="button"
            onClick={toggleInBook}
            data-testid="in-book-toggle"
            className={[
              'px-2.5 py-1 rounded-[2px] font-sans text-[11px] border transition-colors',
              filter.in_book != null
                ? 'bg-teal/10 text-teal border-teal/30'
                : 'bg-paper text-ink-secondary border-paper-rule hover:bg-paper-rule/20',
            ].join(' ')}
          >
            {inBookLabel}
          </button>
        </div>

      </div>
    </aside>
  )
}
