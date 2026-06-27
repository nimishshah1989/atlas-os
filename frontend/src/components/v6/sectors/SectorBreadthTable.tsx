'use client'
// Sector SCORES table — the score is the centrepiece. Per sector: the 0–100 composite conviction
// score + its four component lens scores (Tech/Fund/Flow/Cat), plus one breadth read at a glance.
// Click a row to DERIVE the composite (weight × lens score → composite) and see the rest of the
// breadth detail + top movers. Renamed from the old "EMA participation" table (FM 2026-06-27:
// the score must be visible on the list, and the number must be shown to derive). Sortable.
import { useState } from 'react'
import Link from 'next/link'
import type { SectorBreadthMVRow, SectorBreadthTrendRow } from '@/lib/queries/v6/sectors'
import type { SectorLensVector } from '@/lib/queries/v6/sector_lens'
import { TermInfo } from '@/components/v6/shared/TermInfo'
import { sectorComposite, compositeContributions } from '@/lib/v6/sectorScore'

const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`)
const breadthHeat = (v: number | null) => (v == null ? 'text-txt-3' : v * 100 >= 60 ? 'text-sig-pos' : v * 100 >= 40 ? 'text-txt-2' : 'text-sig-neg')
// 0–100 score → colour band (matches the conviction-score bands elsewhere).
const scoreCls = (v: number | null) => (v == null ? 'text-txt-3' : v >= 60 ? 'text-sig-pos' : v >= 45 ? 'text-brand' : 'text-sig-neg')
const fmtScore = (v: number | null) => (v == null ? '—' : v.toFixed(0))

const LENS_COLS = [
  { key: 'technical', label: 'Tech' },
  { key: 'fundamental', label: 'Fund' },
  { key: 'flow', label: 'Flow' },
  { key: 'catalyst', label: 'Cat' },
  { key: 'valuation', label: 'Val' },
] as const

type SortKey = 'composite' | 'technical' | 'fundamental' | 'flow' | 'catalyst' | 'valuation' | 'pct_above_ema21' | 'constituent_count'

type Row = SectorBreadthMVRow & { vec: SectorLensVector | undefined; composite: number | null }

// Tiny inline EMA21 trend: now · 1w · 1m, tinted by the now−1m direction.
function Ema21Trend({ t }: { t: SectorBreadthTrendRow | undefined }) {
  if (!t) return <span className="text-txt-3">—</span>
  const delta = t.ema21_now != null && t.ema21_1m != null ? t.ema21_now - t.ema21_1m : null
  const tint = delta == null ? 'text-txt-3' : delta > 0.02 ? 'text-sig-pos' : delta < -0.02 ? 'text-sig-neg' : 'text-txt-2'
  const n = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}`)
  return (
    <span className={`tabular-nums ${tint}`}>{n(t.ema21_now)}% <span className="text-txt-3">· {n(t.ema21_1w)} · {n(t.ema21_1m)}</span></span>
  )
}

export function SectorBreadthTable({
  rows,
  trend = [],
  lensBySector = {},
}: {
  rows: SectorBreadthMVRow[]
  trend?: SectorBreadthTrendRow[]
  lensBySector?: Record<string, SectorLensVector>
}) {
  const trendBySector = new Map(trend.map((t) => [t.sector_name, t]))
  const [sortKey, setSortKey] = useState<SortKey>('composite')
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')
  const [open, setOpen] = useState<string | null>(null)

  if (rows.length === 0) return <div className="py-6 text-center font-sans text-sm text-txt-3">Sector data unavailable.</div>

  const data: Row[] = rows.map((r) => {
    const vec = lensBySector[r.sector_name]
    return { ...r, vec, composite: vec ? sectorComposite(vec) : null }
  })

  const valOf = (r: Row): number => {
    if (sortKey === 'composite') return r.composite ?? -1
    if (sortKey === 'constituent_count') return r.constituent_count
    if (sortKey === 'pct_above_ema21') return r.pct_above_ema21 ?? -1
    return (r.vec?.[sortKey] as number | null) ?? -1
  }
  const sorted = [...data].sort((a, b) => (sortDir === 'desc' ? valOf(b) - valOf(a) : valOf(a) - valOf(b)))

  function onSort(k: SortKey) {
    if (k === sortKey) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    else { setSortKey(k); setSortDir('desc') }
  }
  function SortTh({ label, k, term, cls = '' }: { label: string; k: SortKey; term?: string; cls?: string }) {
    const active = sortKey === k
    return (
      <th onClick={() => onSort(k)} className={`py-1.5 font-semibold cursor-pointer select-none hover:text-txt-1 ${active ? 'text-txt-1' : ''} ${cls}`}
        aria-sort={active ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}>
        {label}{term && <TermInfo term={term} />}{active && <span className="ml-0.5">{sortDir === 'desc' ? '↓' : '↑'}</span>}
      </th>
    )
  }

  const NCOLS = 9
  return (
    <table className="w-full text-right" data-testid="sector-breadth-table">
      <thead>
        <tr className="font-num text-[10px] text-txt-3 uppercase tracking-wider border-b border-edge-rule">
          <th className="text-left py-1.5 font-semibold pl-5">Sector</th>
          <SortTh label="Score" k="composite" term="sector_composite" cls="pl-3" />
          {LENS_COLS.map((l) => <SortTh key={l.key} label={l.label} k={l.key} term="sector_lens" />)}
          <SortTh label="&gt;EMA21" k="pct_above_ema21" term="breadth_ema" cls="pl-3" />
          <SortTh label="Stocks" k="constituent_count" />
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => {
          const isOpen = open === r.sector_name
          const contribs = r.vec ? compositeContributions(r.vec) : []
          return (
            <>
              <tr key={r.sector_name}
                onClick={() => setOpen(isOpen ? null : r.sector_name)}
                className="cursor-pointer border-b border-edge-hair hover:bg-surface-raised">
                <td className="text-left py-1.5 font-sans text-xs text-txt-1">
                  <span className="flex items-center gap-1.5 pl-1">
                    <span className="w-3 shrink-0 font-num text-[10px] text-txt-3">{isOpen ? '▾' : '▸'}</span>
                    {r.sector_name}
                  </span>
                </td>
                <td className={`py-1.5 pl-3 font-num text-[13px] tabular-nums font-semibold ${scoreCls(r.composite)}`}>{fmtScore(r.composite)}</td>
                {LENS_COLS.map((l) => {
                  const v = (r.vec?.[l.key] as number | null) ?? null
                  return <td key={l.key} className={`py-1.5 font-num text-xs tabular-nums ${scoreCls(v)}`}>{fmtScore(v)}</td>
                })}
                <td className={`py-1.5 pl-3 font-num text-xs tabular-nums ${breadthHeat(r.pct_above_ema21)}`}>{pct(r.pct_above_ema21)}</td>
                <td className="py-1.5 font-num text-[11px] tabular-nums text-txt-3">{r.constituent_count}</td>
              </tr>
              {isOpen && (
                <tr key={`${r.sector_name}-x`} className="border-b border-edge-hair bg-surface-inset/40">
                  <td colSpan={NCOLS} className="px-5 py-3 text-left">
                    {/* derivation of the composite */}
                    {contribs.length > 0 ? (
                      <div className="mb-3">
                        <div className="mb-1 font-num text-[10px] uppercase tracking-wider text-txt-3">
                          How the score is built<TermInfo term="sector_composite" />
                        </div>
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-num text-[12px] tabular-nums">
                          <span className="font-semibold text-txt-1">{fmtScore(r.composite)}</span>
                          <span className="text-txt-3">=</span>
                          {contribs.map((c, i) => (
                            <span key={c.key} className="text-txt-2">
                              {i > 0 && <span className="text-txt-3">+ </span>}
                              {c.weight.toFixed(2)}·{c.short}
                              <span className="text-txt-1"> {c.score.toFixed(0)}</span>
                              <span className="text-txt-3"> ({c.contrib.toFixed(1)})</span>
                            </span>
                          ))}
                        </div>
                        <div className="mt-1 font-sans text-[11px] text-txt-3">
                          Each lens is the free-float-weighted average of the sector’s constituents; the composite weights them 0.30 / 0.25 / 0.25 / 0.20. Valuation &amp; Policy are context, not scored.
                        </div>
                      </div>
                    ) : (
                      <div className="mb-3 font-sans text-[12px] text-txt-3">No lens vector for this sector.</div>
                    )}
                    {/* breadth detail + movers */}
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 font-num text-[11px]">
                      <span className="text-txt-2">&gt;EMA50 <span className={`tabular-nums ${breadthHeat(r.pct_above_ema50)}`}>{pct(r.pct_above_ema50)}</span></span>
                      <span className="text-txt-2">&gt;EMA200 <span className={`tabular-nums ${breadthHeat(r.pct_above_ema200)}`}>{pct(r.pct_above_ema200)}</span></span>
                      <span className="text-txt-2">EMA21 trend <Ema21Trend t={trendBySector.get(r.sector_name)} /></span>
                      {r.vec?.dispersion != null && <span className="text-txt-2">dispersion <span className="tabular-nums text-txt-1">{r.vec.dispersion.toFixed(1)}</span></span>}
                    </div>
                    {r.top_movers.length > 0 && (
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="font-num text-[10px] uppercase tracking-wider text-txt-3">Top movers · 1M</span>
                        {r.top_movers.slice(0, 5).map((m) => (
                          <Link key={m.symbol} href={`/stocks/${encodeURIComponent(m.symbol)}`}
                            className="font-num text-[11px] tabular-nums text-sig-pos no-underline hover:underline">
                            {m.symbol} +{m.ret_pct.toFixed(1)}%
                          </Link>
                        ))}
                        <Link href={`/sectors/${encodeURIComponent(r.sector_name)}`} className="font-num text-[11px] text-brand hover:underline">open sector →</Link>
                      </div>
                    )}
                  </td>
                </tr>
              )}
            </>
          )
        })}
      </tbody>
    </table>
  )
}
