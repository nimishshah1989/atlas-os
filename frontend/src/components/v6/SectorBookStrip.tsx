'use client'

// frontend/src/components/v6/SectorBookStrip.tsx
// Book vs benchmark sector exposure strip (list + single variants).
// NOTE: query values are in pp ("5.50" = 5.50pp); divide by 100 for formatPct.

import { useMemo } from 'react'
import type { SectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'
import { formatPct, signedPct } from '@/lib/v6/decimal'

export type SectorBookStripVariant = 'list' | 'single'
export type SectorBookStripSortBy = 'delta' | 'book' | 'benchmark'

export interface SectorBookStripProps {
  exposures: SectorBookExposure[]
  variant?: SectorBookStripVariant
  sortBy?: SectorBookStripSortBy
  className?: string
}

// ---------------------------------------------------------------------------

/** Convert a pp string ("5.50") to decimal fraction ("0.0550") for formatPct. */
function ppToDecimal(s: string): string {
  const n = parseFloat(s)
  if (!Number.isFinite(n)) return '0'
  return String(n / 100)
}

type WeightClass = 'OVERWEIGHT' | 'UNDERWEIGHT' | 'NEUTRAL'

function classify(deltaPp: string): WeightClass {
  const n = parseFloat(deltaPp)
  if (!Number.isFinite(n) || Math.abs(n) < 0.005) return 'NEUTRAL'
  return n > 0 ? 'OVERWEIGHT' : 'UNDERWEIGHT'
}

const CHIP_CLASSES: Record<WeightClass, string> = {
  OVERWEIGHT:   'bg-signal-pos/15 text-signal-pos border border-signal-pos/30',
  UNDERWEIGHT:  'bg-signal-neg/15 text-signal-neg border border-signal-neg/30',
  NEUTRAL:      'bg-paper-deep text-ink-tertiary border border-paper-rule',
}

const BAR_MAX_PP = 10 // ±10pp = 100% bar width

function DeltaBar({ deltaPp }: { deltaPp: string }) {
  const n = parseFloat(deltaPp)
  if (!Number.isFinite(n) || n === 0) {
    return <span className="inline-block w-[60px] h-[6px] bg-paper-deep rounded-[1px]" aria-hidden="true" />
  }
  const capped = Math.min(Math.abs(n), BAR_MAX_PP)
  const widthPct = (capped / BAR_MAX_PP) * 100

  if (n > 0) {
    return (
      <span className="inline-flex items-center w-[60px] h-[6px] bg-paper-deep rounded-[1px] overflow-hidden" aria-hidden="true">
        <span className="h-full bg-signal-pos rounded-[1px]" style={{ width: `${widthPct}%` }} />
      </span>
    )
  }
  return (
    <span className="inline-flex items-center justify-end w-[60px] h-[6px] bg-paper-deep rounded-[1px] overflow-hidden" aria-hidden="true">
      <span className="h-full bg-signal-neg rounded-[1px]" style={{ width: `${widthPct}%` }} />
    </span>
  )
}

function ExposureRow({ row, isMuted }: { row: SectorBookExposure; isMuted: boolean }) {
  const weightClass = classify(row.delta_pp)
  const chipClasses = CHIP_CLASSES[weightClass]
  const textBase = isMuted ? 'text-ink-tertiary' : 'text-ink-primary'

  return (
    <div
      className="flex items-center gap-3 px-3 py-2.5 border-b border-paper-rule last:border-b-0 hover:bg-paper-deep/40 transition-colors"
      aria-label={`${row.sector_name}: book ${row.book_weight}%, benchmark ${row.benchmark_weight}%, delta ${row.delta_pp}pp`}
      role="row"
    >
      {/* Sector name — fixed width */}
      <span className={`w-[140px] shrink-0 font-sans text-[12px] font-medium truncate ${textBase}`}>
        {row.sector_name}
      </span>

      {/* Book weight | Benchmark weight */}
      <span className="flex items-center gap-1 font-mono text-[11px] tabular-nums shrink-0">
        <span className={isMuted ? 'text-ink-tertiary' : 'text-ink-primary'}>
          {formatPct(ppToDecimal(row.book_weight), { decimals: 1, signed: false })}
        </span>
        <span className="text-ink-tertiary">/</span>
        <span className="text-ink-secondary">
          {formatPct(ppToDecimal(row.benchmark_weight), { decimals: 1, signed: false })}
        </span>
      </span>

      {/* Delta pp */}
      <span
        className={[
          'font-mono text-[11px] tabular-nums shrink-0 w-[54px] text-right',
          isMuted
            ? 'text-ink-tertiary'
            : parseFloat(row.delta_pp) > 0
              ? 'text-signal-pos'
              : parseFloat(row.delta_pp) < 0
                ? 'text-signal-neg'
                : 'text-ink-tertiary',
        ].join(' ')}
      >
        {isMuted ? '—' : signedPct(ppToDecimal(row.delta_pp), { decimals: 1 })}
      </span>

      {/* Delta bar */}
      <span className="shrink-0">
        {isMuted
          ? <span className="inline-block w-[60px] h-[6px] bg-paper-deep rounded-[1px]" aria-hidden="true" />
          : <DeltaBar deltaPp={row.delta_pp} />
        }
      </span>

      {/* OVERWEIGHT / UNDERWEIGHT / NEUTRAL chip */}
      <span
        className={[
          'inline-flex items-center font-sans font-semibold uppercase rounded-[2px]',
          'px-[7px] py-[3px] text-[10px] shrink-0',
          chipClasses,
        ].join(' ')}
        style={{ letterSpacing: '0.12em' }}
      >
        {weightClass}
      </span>

      {row.holding_count > 0 && (
        <span className="font-mono text-[10px] text-ink-tertiary ml-auto shrink-0">{row.holding_count}h</span>
      )}
    </div>
  )
}

export function SectorBookStrip({
  exposures,
  variant = 'list',
  sortBy = 'delta',
  className = '',
}: SectorBookStripProps) {
  // Empty guard
  if (exposures.length === 0) {
    return <div className="sr-only">No sector exposure data</div>
  }

  const sorted = useMemo(() => {
    return [...exposures].sort((a, b) => {
      if (sortBy === 'delta') {
        return Math.abs(parseFloat(b.delta_pp)) - Math.abs(parseFloat(a.delta_pp))
      }
      if (sortBy === 'book') {
        return parseFloat(b.book_weight) - parseFloat(a.book_weight)
      }
      // benchmark
      return parseFloat(b.benchmark_weight) - parseFloat(a.benchmark_weight)
    })
  }, [exposures, sortBy])

  const isNoBook = exposures.every(
    (e) => e.book_weight === '0.00' && e.benchmark_weight === '0.00',
  )

  if (variant === 'single') {
    const row = sorted[0]
    const isMuted = row.book_weight === '0.00' && row.benchmark_weight === '0.00'
    return (
      <div
        className={['border border-paper-rule rounded-[2px] bg-paper', className].filter(Boolean).join(' ')}
        role="table"
        aria-label="Book exposure for this sector"
      >
        <ExposureRow row={row} isMuted={isMuted || isNoBook} />
      </div>
    )
  }

  // list variant
  return (
    <div
      className={['border border-paper-rule rounded-[2px] bg-paper overflow-hidden', className].filter(Boolean).join(' ')}
      role="table"
      aria-label="Book vs benchmark sector exposure"
    >
      {/* Column headers */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-paper-rule bg-paper-deep/40">
        <span className="w-[140px] shrink-0 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Sector</span>
        <span className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Book / Benchmark</span>
        <span className="w-[54px] shrink-0 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right ml-auto">Delta</span>
      </div>

      {sorted.map((row) => {
        const isMuted =
          isNoBook || (row.book_weight === '0.00' && row.benchmark_weight === '0.00')
        return <ExposureRow key={row.sector_name} row={row} isMuted={isMuted} />
      })}
    </div>
  )
}

export default SectorBookStrip
