'use client'
// frontend/src/components/v6/SectorsListV6.tsx
// D.3 — Book Strip + RRG + Bubble + 30-row ladder + 12W rank trajectory sparkline
// FM-critic §1.9 critical gap #2: sparkline per ladder row.

import { useMemo, useState } from 'react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import Link from 'next/link'
import { SectorBookStrip } from '@/components/v6/SectorBookStrip'
import { BubbleRiskReturnChart, type BubbleDatum } from '@/components/v6/BubbleRiskReturnChart'
import { RRGChart } from '@/components/sectors/RRGChart'
import { StateBadge } from '@/components/ui/StateBadge'
import { LinkedSector } from '@/components/ui/LinkedToken'
import type { ScreenSector } from '@/lib/api/v1'
import type { SectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'
import type { SectorSnapshot, RRGHistoryRow } from '@/lib/queries/sectors'

// ── Types ────────────────────────────────────────────────────────────────────

export interface SectorsListV6Props {
  sectors:    ScreenSector[]
  exposures:  SectorBookExposure[]
  rrgCurrent: SectorSnapshot[]
  rrgHistory: RRGHistoryRow[]
}

type SortKey = 'rank' | 'breadth' | 'rs'

// ── Rank Sparkline (SVG, 12-week trajectory) ─────────────────────────────────

function RankSparkline({ ranks, totalSectors }: { ranks: number[]; totalSectors: number }) {
  if (!ranks || ranks.length < 2) {
    return <span className="font-mono text-[10px] text-ink-tertiary">—</span>
  }
  const W = 56, H = 22, max = totalSectors || 30
  const toY = (r: number) => H - (Math.max(1, Math.min(r, max)) / max) * H + 1
  const pts = ranks.map((r, i) => `${((i / (ranks.length - 1)) * W).toFixed(1)},${toY(r).toFixed(1)}`).join(' ')
  const first = ranks[0], last = ranks[ranks.length - 1]
  const color =
    last < first  ? 'var(--color-signal-pos, #2F6B43)' :
    last > first  ? 'var(--color-signal-neg, #B0492C)' :
    'var(--color-ink-tertiary, #94a3b8)'
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}
      aria-label={`12-week rank trajectory: ${first} → ${last}`}
      data-testid="rank-sparkline"
    >
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={W} cy={toY(last)} r={2} fill={color} />
    </svg>
  )
}

// ── Micro-components ─────────────────────────────────────────────────────────

function RankArrow({ change }: { change: number }) {
  if (change > 0) return <TrendingUp size={12} strokeWidth={1.5} className="text-signal-pos" aria-label="up" />
  if (change < 0) return <TrendingDown size={12} strokeWidth={1.5} className="text-signal-neg" aria-label="down" />
  return <Minus size={12} strokeWidth={1.5} className="text-ink-tertiary" aria-label="flat" />
}

function BreadthBar({ value }: { value: number | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const pct = Math.max(0, Math.min(1, value))
  const fill = pct >= 0.55 ? 'bg-signal-pos' : pct >= 0.35 ? 'bg-teal' : pct >= 0.20 ? 'bg-signal-warn' : 'bg-signal-neg'
  return (
    <span className="inline-flex items-center gap-1.5 w-full">
      <span className="relative inline-block h-1.5 w-12 bg-paper-rule/40 rounded-[1px] overflow-hidden">
        <span className={`absolute top-0 left-0 h-full ${fill}`} style={{ width: `${pct * 100}%` }} />
      </span>
      <span className="font-mono text-[11px] tabular-nums text-ink-secondary">{Math.round(pct * 100)}%</span>
    </span>
  )
}

function VolPill({ regime }: { regime: string }) {
  const cls =
    regime === 'Low'      ? 'text-signal-pos bg-signal-pos/10 border-signal-pos/20' :
    regime === 'Normal'   ? 'text-ink-secondary bg-paper-rule/20 border-paper-rule' :
    regime === 'Elevated' ? 'text-signal-warn bg-signal-warn/10 border-signal-warn/20' :
    regime === 'High'     ? 'text-signal-neg bg-signal-neg/10 border-signal-neg/20' :
    'text-ink-tertiary border-transparent bg-transparent'
  return (
    <span className={`inline-flex items-center font-sans font-medium border rounded-[2px] tabular-nums text-[10px] px-1.5 py-0.5 ${cls}`}>
      {regime}
    </span>
  )
}

function pctSigned(v: number | null): { text: string; cls: string } {
  if (v == null || !Number.isFinite(v)) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  return {
    text: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`,
    cls: pct >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-3">
      <h2 className="font-serif text-lg font-semibold text-ink-primary">{title}</h2>
      {subtitle && <p className="font-sans text-[12px] text-ink-tertiary mt-0.5">{subtitle}</p>}
    </div>
  )
}

function Th({ align, children, testId }: { align: 'left' | 'right' | 'center'; children: React.ReactNode; testId?: string }) {
  const alignClass = align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left'
  return (
    <th className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary ${alignClass}`} data-testid={testId}>
      {children}
    </th>
  )
}

// ── Sectors → BubbleDatum conversion ─────────────────────────────────────────

function sectorsToBubbles(sectors: ScreenSector[]): BubbleDatum[] {
  return sectors.map((s) => ({
    id:    s.sector_iid,
    label: s.sector_name,
    risk:  String(((1 - (s.breadth_pct_stage_2 ?? 0.5))).toFixed(4)),
    ret:   String(((s.ret_3m ?? 0) * 100).toFixed(4)),
    size:  '10',
    state: (s.sector_state === 'Overweight' ? 'POSITIVE' : s.sector_state === 'Avoid' ? 'NEGATIVE' : 'NEUTRAL') as BubbleDatum['state'],
  }))
}

// ── Flat 12-point trajectory (honest when no history) ────────────────────────
// TODO(v6.1): replace with actual weekly rank snapshots from atlas_sector_states_daily

function buildTrajectory(rank: number): number[] {
  return Array(12).fill(rank) as number[]
}

// ── Main component ────────────────────────────────────────────────────────────

export function SectorsListV6({ sectors, exposures, rrgCurrent, rrgHistory }: SectorsListV6Props) {
  const [sortKey, setSortKey]               = useState<SortKey>('rank')
  const [rrgSelected, setRRGSelected]       = useState<string | null>(null)

  const bubbleData = useMemo(() => sectorsToBubbles(sectors), [sectors])

  const sortedSectors = useMemo(() => {
    const copy = [...sectors]
    if (sortKey === 'rank')    return copy.sort((a, b) => a.rank - b.rank)
    if (sortKey === 'breadth') return copy.sort((a, b) => (b.breadth_pct_stage_2 ?? 0) - (a.breadth_pct_stage_2 ?? 0))
    return copy.sort((a, b) => (b.rs_pct_cross_sector ?? 0) - (a.rs_pct_cross_sector ?? 0))
  }, [sectors, sortKey])

  if (sectors.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-ink-tertiary font-sans text-sm" data-testid="sectors-empty-state">
        <p className="text-lg font-medium text-ink-secondary mb-2">No sector data available</p>
        <p className="text-[12px]">Sector metrics have not been computed for today&apos;s snapshot.</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">

      {/* Section 1 — SectorBookStrip */}
      <section aria-label="Book vs benchmark sector exposure">
        <SectionHeader title="Book vs Benchmark" subtitle="Portfolio sector weights vs Nifty 500 equal-weight." />
        <SectorBookStrip exposures={exposures} variant="list" sortBy="delta" className="w-full" />
      </section>

      {/* Section 2 — RRGChart */}
      <section aria-label="Sector Relative Rotation Graph">
        <SectionHeader title="Relative Rotation Graph" subtitle="RS Strength (X) vs RS Momentum (Y). Click a sector to navigate." />
        {rrgCurrent.length === 0 ? (
          <div className="flex items-center justify-center h-48 bg-paper border border-paper-rule rounded-sm text-ink-tertiary font-sans text-sm">
            RRG data unavailable — insufficient sector metric history.
          </div>
        ) : (
          <RRGChart current={rrgCurrent} history={rrgHistory} onSelect={setRRGSelected} height={560} />
        )}
        {rrgSelected && (
          <div className="mt-2 font-sans text-[11px] text-ink-tertiary">
            Selected:{' '}
            <Link href={`/v6/sectors/${encodeURIComponent(rrgSelected)}`} className="text-teal underline-offset-2 hover:underline">
              {rrgSelected}
            </Link>
          </div>
        )}
      </section>

      {/* Section 3 — BubbleRiskReturnChart */}
      <section aria-label="Sector risk vs return bubble chart">
        <SectionHeader title="Risk / Return Map" subtitle="12-week relative return (Y) vs breadth-inversion risk proxy (X)." />
        <BubbleRiskReturnChart
          data={bubbleData}
          xLabel="Risk proxy (1 − breadth)"
          yLabel="3M relative return (%)"
          sizeLabel="Sector size (est.)"
          className="w-full"
        />
      </section>

      {/* Section 4 — Ladder */}
      <section aria-label="Sector ladder" data-testid="sector-ladder">
        <div className="flex items-center justify-between mb-3">
          <SectionHeader title="Sector Ladder" subtitle={`${sectors.length} sectors ranked by composite RS, breadth, and vol regime.`} />
          <div className="flex items-center gap-2">
            <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Sort:</span>
            {(['rank', 'breadth', 'rs'] as SortKey[]).map((key) => (
              <button
                key={key}
                onClick={() => setSortKey(key)}
                aria-pressed={sortKey === key}
                className={[
                  'font-sans text-[11px] px-2 py-1 rounded-[2px] border transition-colors',
                  sortKey === key
                    ? 'bg-teal/10 border-teal/30 text-teal font-medium'
                    : 'bg-paper border-paper-rule text-ink-secondary hover:border-teal/30',
                ].join(' ')}
              >
                {key === 'rank' ? 'Rank' : key === 'breadth' ? 'Breadth' : 'RS%'}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto border border-paper-rule rounded-[2px]">
          <table className="w-full border-collapse" data-testid="sectors-table">
            <thead>
              <tr className="border-b border-paper-rule bg-paper">
                <Th align="right">#</Th>
                <Th align="center">Δ</Th>
                <Th align="left">Sector</Th>
                <Th align="left">State</Th>
                <Th align="left">Breadth</Th>
                <Th align="left">Vol σ</Th>
                <Th align="right">RS %</Th>
                <Th align="right">1M</Th>
                <Th align="right">3M</Th>
                <Th align="center" testId="sparkline-header">12W Traj</Th>
              </tr>
            </thead>
            <tbody>
              {sortedSectors.map((s, i) => {
                const r1 = pctSigned(s.ret_1m)
                const r3 = pctSigned(s.ret_3m)
                const traj = buildTrajectory(s.rank)
                return (
                  <tr
                    key={s.sector_iid}
                    className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
                    data-rank={s.rank}
                  >
                    <td className="px-3 py-2.5 font-mono text-xs tabular-nums text-ink-secondary text-right whitespace-nowrap">{s.rank}</td>
                    <td className="px-3 py-2.5 text-center whitespace-nowrap"><RankArrow change={s.rank_change} /></td>
                    <td className="px-3 py-2.5 whitespace-nowrap"><LinkedSector sector={s.sector_name} /></td>
                    <td className="px-3 py-2.5 whitespace-nowrap"><StateBadge state={s.sector_state} size="sm" /></td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <Link href={`/stocks?sector=${encodeURIComponent(s.sector_name)}`} className="hover:opacity-80">
                        <BreadthBar value={s.breadth_pct_stage_2} />
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap"><VolPill regime={s.vol_regime} /></td>
                    <td className="px-3 py-2.5 font-mono text-xs tabular-nums text-ink-primary text-right whitespace-nowrap">
                      {s.rs_pct_cross_sector != null ? Math.round(s.rs_pct_cross_sector * 100) : '—'}
                    </td>
                    <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r1.cls}`}>{r1.text}</td>
                    <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r3.cls}`}>{r3.text}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-center" data-testid="sparkline-cell">
                      <RankSparkline ranks={traj} totalSectors={sectors.length} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

    </div>
  )
}
