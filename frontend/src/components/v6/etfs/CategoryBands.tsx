'use client'

// frontend/src/components/v6/etfs/CategoryBands.tsx
//
// Four canonical ETF category band cards:
//   Index (broad-cap) · Sector · Smart-beta · Commodity + International
//
// Derived from EtfListV6Row[] (34 rows). Each card shows:
//   ETF count · monthly turnover (ADV × ~20 trading days) · action mix · top tickers.
//
// Category mapping from etf_category column values in mv_etf_list_v6.

import type { EtfListV6Row } from '@/lib/queries/v6/etfs'

// ── Category config ───────────────────────────────────────────────────────────

type BandKey = 'index' | 'sector' | 'smartbeta' | 'commodity'

const BAND_CONFIG: Record<
  BandKey,
  {
    label: string
    title: string
    accentClass: string
    borderClass: string
    matchFn: (etf_category: string | null) => boolean
  }
> = {
  index: {
    label: 'Index ETFs',
    title: 'Broad-cap passive',
    accentClass: 'text-signal-info',
    borderClass: 'border-t-signal-info',
    matchFn: (c) => c != null && (c.includes('index') || c === 'broad_index'),
  },
  sector: {
    label: 'Sector ETFs',
    title: 'Single-sector exposure',
    accentClass: 'text-signal-pos',
    borderClass: 'border-t-signal-pos',
    matchFn: (c) => c != null && c === 'sector',
  },
  smartbeta: {
    label: 'Smart-beta ETFs',
    title: 'Factor-based passive',
    accentClass: 'text-teal',
    borderClass: 'border-t-teal',
    matchFn: (c) => c != null && (c === 'smart_beta' || c === 'smartbeta' || c === 'thematic'),
  },
  commodity: {
    label: 'Commodity + Intl',
    title: 'Diversifier ETFs',
    accentClass: 'text-signal-warn',
    borderClass: 'border-t-signal-warn',
    matchFn: (c) => c != null && (c === 'commodity' || c === 'international' || c === 'debt'),
  },
}

function fmtAdv(cr: number): string {
  if (cr >= 1_00_000) return `₹${(cr / 1_00_000).toFixed(2)} L cr`
  if (cr >= 1000) return `₹${(cr / 1000).toFixed(2)} K cr`
  return `₹${cr.toFixed(0)} cr`
}

// ── Band card ─────────────────────────────────────────────────────────────────

function BandCard({
  bandKey,
  etfs,
}: {
  bandKey: BandKey
  etfs: EtfListV6Row[]
}) {
  const config = BAND_CONFIG[bandKey]
  const bandEtfs = etfs.filter((e) => config.matchFn(e.etf_category))

  const buyCount = bandEtfs.filter((e) => e.action === 'BUY').length
  const watchCount = bandEtfs.filter((e) => e.action === 'WATCH').length
  const avoidCount = bandEtfs.filter((e) => e.action === 'AVOID').length
  const totalAdvCr = bandEtfs.reduce(
    (sum, e) => sum + ((e.adv_20d_inr ?? 0) / 1e7) * 30,
    0,
  )

  // Top 3 by composite_score desc
  const topTickers = [...bandEtfs]
    .sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0))
    .slice(0, 3)
    .map((e) => e.ticker)

  return (
    <div
      className={`bg-paper border border-paper-rule rounded-sm p-4 border-t-4 ${config.borderClass}`}
      data-testid={`category-band-${bandKey}`}
    >
      <div
        className={`font-sans text-[10px] uppercase tracking-[0.18em] font-semibold mb-1 ${config.accentClass}`}
      >
        {config.label}
      </div>
      <div className="font-serif text-lg text-ink-primary mb-3 leading-snug">
        {config.title}
      </div>

      <div className="grid grid-cols-2 gap-2 pb-2 mb-2.5 border-b border-paper-rule font-mono">
        <div className="flex flex-col">
          <span className="font-sans text-[9px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">
            ETFs
          </span>
          <span className="text-lg font-semibold text-ink-primary mt-0.5">
            {bandEtfs.length}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="font-sans text-[9px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">
            Monthly turnover
          </span>
          <span className="text-lg font-semibold text-ink-primary mt-0.5">
            {totalAdvCr > 0 ? fmtAdv(totalAdvCr) : '—'}
          </span>
        </div>
      </div>

      <div className="font-sans text-[11.5px] text-ink-secondary leading-relaxed">
        <strong className="text-ink-primary font-semibold">
          BUY: {buyCount} · WATCH: {watchCount} · AVOID: {avoidCount}
        </strong>
        {topTickers.length > 0 && (
          <>
            <br />
            Top: {topTickers.join(' · ')}
          </>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export interface CategoryBandsProps {
  etfs: EtfListV6Row[]
}

export function CategoryBands({ etfs }: CategoryBandsProps) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3"
      data-testid="category-bands"
    >
      {(Object.keys(BAND_CONFIG) as BandKey[]).map((key) => (
        <BandCard key={key} bandKey={key} etfs={etfs} />
      ))}
    </div>
  )
}

export default CategoryBands
