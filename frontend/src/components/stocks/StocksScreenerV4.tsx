'use client'

// StocksScreenerV4 — the interactive /stocks screener (client). Orchestrates:
//   (A) the ONE strong 2×2 (Strength × Leadership, size=liquidity) — respects active filters
//   (B) filter + smart-screen bar (cap · sector · lens focus · min lead · min liq · 6 screens)
//   (C) sortable decile table (5 lens deciles · strength · lead · compact RS · liquidity)
// Presentational only — all data is pre-coerced to numbers server-side (StockListRow).
import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { StockListRow } from '@/lib/queries/stock_lens'
import { StocksBubble2x2 } from './StocksBubble2x2'
import { Panel } from '@/components/ui/Panel'
import { decileColor } from '@/components/ui/decile'
import { TermInfo } from '@/components/shared/TermInfo'
import { AddToBasketButton } from '@/components/portfolios/AddToBasketButton'

// ── colour helpers (shared idioms) ────────────────────────────────────────
// Decile cells colour the figure via the shared perceptual ramp (decileColor);
// null falls back to the tertiary text token.
const decileStyle = (d: number | null) => ({ color: d == null ? 'var(--color-txt-3)' : decileColor(d) })

const leadText = (lead: number) =>
  lead >= 1 ? 'text-sig-pos' : 'text-txt-3'  // leader = top-decile composite (0/1)

const pctText = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const fmtPct = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)

const fmtLiq = (v: number | null) =>
  v == null ? '—' : v < 10 ? v.toFixed(1) : v.toFixed(0)

const CAPS = ['large', 'mid', 'small', 'micro'] as const

// ── lens focus → which decile column it sorts/emphasizes ──────────────────
type LensKey = 'd_tech' | 'd_fund' | 'd_cat' | 'd_flow' | 'd_val'
const LENS_FOCUS: { label: string; key: LensKey | null }[] = [
  { label: 'None', key: null },
  { label: 'Technical', key: 'd_tech' },
  { label: 'Fundamental', key: 'd_fund' },
  { label: 'Catalyst', key: 'd_cat' },
  { label: 'Flow', key: 'd_flow' },
  { label: 'Valuation', key: 'd_val' },
]

// ── smart screens (one active at a time) ──────────────────────────────────
type ScreenId = 'leaders' | 'cheap' | 'accum' | 'catalyst' | 'breakout' | 'quality'
const SCREENS: { id: ScreenId; label: string; pred: (s: StockListRow) => boolean }[] = [
  { id: 'leaders', label: 'Leaders (top-decile)', pred: s => s.lead >= 1 },
  { id: 'cheap', label: 'Cheap & strong', pred: s => (s.d_val ?? 0) >= 8 && (s.strength ?? 0) >= 7 },
  { id: 'accum', label: 'Rising accumulation', pred: s => (s.d_flow ?? 0) >= 8 },
  { id: 'catalyst', label: 'Fresh catalyst', pred: s => (s.d_cat ?? 0) >= 8 },
  { id: 'breakout', label: 'Momentum breakouts', pred: s => (s.d_tech ?? 0) >= 8 && (s.rs_3m ?? -1) > 0 },
  { id: 'quality', label: 'Quality compounders', pred: s => (s.d_fund ?? 0) >= 8 },
]

// ── sortable table columns ────────────────────────────────────────────────
type SortKey =
  | 'symbol' | 'cap' | 'sector'
  | 'd_tech' | 'd_fund' | 'd_cat' | 'd_flow' | 'd_val'
  | 'strength' | 'lead'
  | 'rs_1m' | 'rs_3m' | 'rs_6m' | 'rs_sector_3m' | 'liq_cr'

type Col = { key: SortKey; label: string; align: 'left' | 'right'; emphLens?: LensKey; term?: string }
const COLS: Col[] = [
  { key: 'symbol', label: 'Symbol', align: 'left' },
  { key: 'cap', label: 'Cap', align: 'left', term: 'cap_tier' },
  { key: 'sector', label: 'Sector', align: 'left', term: 'sector_name' },
  { key: 'd_tech', label: 'Tch', align: 'right', emphLens: 'd_tech', term: 'decile' },
  { key: 'd_fund', label: 'Fnd', align: 'right', emphLens: 'd_fund', term: 'decile' },
  { key: 'd_cat', label: 'Cat', align: 'right', emphLens: 'd_cat', term: 'decile' },
  { key: 'd_flow', label: 'Flw', align: 'right', emphLens: 'd_flow', term: 'decile' },
  { key: 'd_val', label: 'Val', align: 'right', emphLens: 'd_val', term: 'decile' },
  { key: 'strength', label: 'Strength', align: 'right', term: 'strength' },
  { key: 'lead', label: 'Lead', align: 'right', term: 'lead' },
  { key: 'rs_1m', label: 'RS 1M', align: 'right', term: 'rs' },
  { key: 'rs_3m', label: 'RS 3M', align: 'right', term: 'rs' },
  { key: 'rs_6m', label: 'RS 6M', align: 'right', term: 'rs' },
  { key: 'rs_sector_3m', label: 'RS Sec 3M', align: 'right', term: 'rs_sector' },
  { key: 'liq_cr', label: 'Liq(₹Cr)', align: 'right', term: 'liq' },
]

// Show the whole scored universe (~498). Kept as a generous guardrail, not a 300-row truncation.
const ROW_CAP = 1000

// numeric value for a sort key; nulls sink to -Infinity so they sort last on desc.
function numFor(s: StockListRow, key: SortKey): number {
  switch (key) {
    case 'lead': return s.lead
    case 'strength': return s.strength ?? -Infinity
    case 'd_tech': return s.d_tech ?? -Infinity
    case 'd_fund': return s.d_fund ?? -Infinity
    case 'd_cat': return s.d_cat ?? -Infinity
    case 'd_flow': return s.d_flow ?? -Infinity
    case 'd_val': return s.d_val ?? -Infinity
    case 'rs_1m': return s.rs_1m ?? -Infinity
    case 'rs_3m': return s.rs_3m ?? -Infinity
    case 'rs_6m': return s.rs_6m ?? -Infinity
    case 'rs_sector_3m': return s.rs_sector_3m ?? -Infinity
    case 'liq_cr': return s.liq_cr ?? -Infinity
    default: return 0
  }
}

const CONTROL = 'font-sans text-[12px] bg-surface-raised border border-edge-rule rounded-tile px-2 py-1 text-txt-2'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-sans text-[10px] uppercase tracking-wider text-txt-3">{label}</span>
      {children}
    </label>
  )
}

export function StocksScreenerV4({ stocks }: { stocks: StockListRow[] }) {
  const router = useRouter()

  const [cap, setCap] = useState<string>('all')
  const [sector, setSector] = useState<string>('all')
  const [lensFocus, setLensFocus] = useState<LensKey | null>(null)
  const [minLead, setMinLead] = useState<number>(0)
  const [minLiq, setMinLiq] = useState<number>(0)
  const [screen, setScreen] = useState<ScreenId | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('strength')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const sectors = useMemo(
    () => Array.from(new Set(stocks.map(s => s.sector).filter((x): x is string => !!x))).sort(),
    [stocks],
  )

  const activeScreen = SCREENS.find(s => s.id === screen) ?? null

  // (1) filter by all active controls
  const filtered = useMemo(() => {
    return stocks.filter(s => {
      if (cap !== 'all' && s.cap !== cap) return false
      if (sector !== 'all' && s.sector !== sector) return false
      if (s.lead < minLead) return false
      if ((s.liq_cr ?? 0) < minLiq) return false
      if (activeScreen && !activeScreen.pred(s)) return false
      return true
    })
  }, [stocks, cap, sector, minLead, minLiq, activeScreen])

  // (2) sort — lens focus overrides the column sort key (sort by that lens desc)
  const sorted = useMemo(() => {
    const key: SortKey = lensFocus ?? sortKey
    const dir: 'asc' | 'desc' = lensFocus ? 'desc' : sortDir
    const sign = dir === 'desc' ? -1 : 1
    const out = [...filtered]
    out.sort((a, b) => {
      if (key === 'symbol') return sign * a.symbol.localeCompare(b.symbol)
      if (key === 'cap') return sign * a.cap.localeCompare(b.cap)
      if (key === 'sector') return sign * (a.sector ?? '').localeCompare(b.sector ?? '')
      return sign * (numFor(a, key) - numFor(b, key))
    })
    return out
  }, [filtered, sortKey, sortDir, lensFocus])

  const total = stocks.length
  const shown = sorted.length
  const rows = sorted.slice(0, ROW_CAP)
  const truncated = shown > ROW_CAP

  const effectiveSortKey: SortKey = lensFocus ?? sortKey
  const effectiveSortDir: 'asc' | 'desc' = lensFocus ? 'desc' : sortDir

  function toggleSort(key: SortKey) {
    setLensFocus(null)  // an explicit header click takes over from lens-focus sort (else the click looks inert)
    if (sortKey === key) setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))
    else { setSortKey(key); setSortDir('desc') }
  }

  function clearAll() {
    setCap('all'); setSector('all'); setLensFocus(null)
    setMinLead(0); setMinLiq(0); setScreen(null)
    setSortKey('strength'); setSortDir('desc')
  }

  return (
    <div className="flex flex-col gap-5">
      {/* (A) The 2×2 — respects active filters/screens */}
      <Panel
        eyebrow="Map"
        title="Strength × Leadership"
        info={{
          title: 'How to read the 2×2',
          body: 'Each dot is a stock — x = average decile across the active lenses (Technical & Flow), y = how many of those 2 lenses it leads (D9/D10). Bubble size = ~20-session liquidity, colour = leadership. Click any dot for its evidence.',
        }}
      >
        <StocksBubble2x2 stocks={filtered} />
      </Panel>

      {/* (B) Filter + smart-screen bar + (C) table */}
      <Panel
        eyebrow="Screener"
        title="Screen the universe"
        info={{
          title: 'Screening the universe',
          body: 'Filter by cap, sector and conviction, or jump to a smart screen. Every column header sorts. Click a row for the full lens read.',
        }}
      >
        {/* control row */}
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <Field label="Cap">
            <select className={CONTROL} value={cap} onChange={e => setCap(e.target.value)}>
              <option value="all">All</option>
              {CAPS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>

          <Field label="Sector">
            <select className={CONTROL} value={sector} onChange={e => setSector(e.target.value)}>
              <option value="all">All</option>
              {sectors.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>

          <Field label="Lens focus">
            <select
              className={CONTROL}
              value={lensFocus ?? ''}
              onChange={e => setLensFocus((e.target.value || null) as LensKey | null)}
            >
              {LENS_FOCUS.map(l => <option key={l.label} value={l.key ?? ''}>{l.label}</option>)}
            </select>
          </Field>

          <Field label="Min leadership">
            <select className={CONTROL} value={minLead} onChange={e => setMinLead(parseInt(e.target.value, 10))}>
              <option value={0}>0</option>
              <option value={1}>≥1</option>
              <option value={2}>≥2</option>
              <option value={3}>≥3</option>
              <option value={4}>4</option>
            </select>
          </Field>

          <Field label="Min liquidity (₹Cr)">
            <select className={CONTROL} value={minLiq} onChange={e => setMinLiq(parseInt(e.target.value, 10))}>
              {[0, 1, 5, 25, 100].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </Field>

          <button
            type="button"
            onClick={clearAll}
            className="font-sans text-[12px] bg-surface-raised border border-edge-rule rounded-tile px-3 py-1 text-txt-2 hover:border-edge-strong transition-colors self-end"
          >
            Clear all
          </button>

          <span className="font-num text-[12px] tabular-nums text-txt-3 self-end ml-auto">
            {shown} of {total} stocks
          </span>
        </div>

        {/* smart screens */}
        <div className="flex flex-wrap gap-2 mb-6">
          {SCREENS.map(sc => {
            const active = screen === sc.id
            return (
              <button
                key={sc.id}
                type="button"
                onClick={() => setScreen(active ? null : sc.id)}
                className={`font-sans text-[12px] rounded-tile px-3 py-1 transition-colors ${
                  active
                    ? 'border border-brand bg-brand-soft text-brand'
                    : 'bg-surface-raised border border-edge-rule text-txt-2 hover:border-edge-strong'
                }`}
              >
                {sc.label}
              </button>
            )
          })}
        </div>

        {/* (C) decile table */}
        <div className="overflow-x-auto">
          <table className="tbl-centered w-full border-collapse">
            <thead>
              <tr className="border-b border-edge-rule">
                {COLS.map(col => {
                  const isSorted = effectiveSortKey === col.key
                  const emphasized = lensFocus != null && col.emphLens === lensFocus
                  const arrow = isSorted ? (effectiveSortDir === 'desc' ? ' ▼' : ' ▲') : ''
                  return (
                    <th
                      key={col.key}
                      onClick={() => toggleSort(col.key)}
                      className={`font-sans text-[10px] uppercase tracking-wider pb-2 px-2 cursor-pointer select-none whitespace-nowrap ${
                        col.align === 'right' ? 'text-right' : 'text-left'
                      } ${emphasized ? 'text-txt-1 font-semibold' : 'text-txt-3'} hover:text-txt-2`}
                    >
                      {col.label}{col.term && <TermInfo term={col.term} />}{arrow}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map(s => {
                const emph = (k: LensKey) => (lensFocus === k ? 'font-semibold' : '')
                return (
                  <tr
                    key={s.symbol}
                    onClick={() => router.push('/stocks/' + s.symbol)}
                    className="border-b border-edge-hair cursor-pointer hover:bg-surface-raised"
                  >
                    <td className="py-1.5 px-2 font-num text-[12px] font-semibold tabular-nums text-txt-1 whitespace-nowrap">
                      {s.symbol}
                      <span className="ml-1 inline-block align-middle"><AddToBasketButton pick={{ key: `stock:${s.symbol}`, label: s.symbol }} /></span>
                    </td>
                    <td className="py-1.5 px-2 font-sans text-[11px] text-txt-3 whitespace-nowrap">{s.cap}</td>
                    <td className="py-1.5 px-2 font-sans text-[11px] text-txt-2 truncate max-w-[160px]">{s.sector ?? '—'}</td>

                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${emph('d_tech')}`} style={decileStyle(s.d_tech)}>{s.d_tech ?? '—'}</td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${emph('d_fund')}`} style={decileStyle(s.d_fund)}>{s.d_fund ?? '—'}</td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${emph('d_cat')}`} style={decileStyle(s.d_cat)}>{s.d_cat ?? '—'}</td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${emph('d_flow')}`} style={decileStyle(s.d_flow)}>{s.d_flow ?? '—'}</td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${emph('d_val')}`} style={decileStyle(s.d_val)}>{s.d_val ?? '—'}</td>

                    <td className="py-1.5 px-2 text-right font-num text-[12px] tabular-nums text-txt-2">
                      {s.strength == null ? '—' : s.strength.toFixed(1)}
                    </td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${leadText(s.lead)}`}>{s.lead >= 1 ? 'Leader' : '—'}</td>

                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${pctText(s.rs_1m)}`}>{fmtPct(s.rs_1m)}</td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${pctText(s.rs_3m)}`}>{fmtPct(s.rs_3m)}</td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${pctText(s.rs_6m)}`}>{fmtPct(s.rs_6m)}</td>
                    <td className={`py-1.5 px-2 text-right font-num text-[12px] tabular-nums ${pctText(s.rs_sector_3m)}`}>{fmtPct(s.rs_sector_3m)}</td>

                    <td className="py-1.5 px-2 text-right font-num text-[12px] tabular-nums text-txt-2">{fmtLiq(s.liq_cr)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {truncated && (
          <p className="font-sans text-[11px] text-txt-3 mt-3">
            showing top {ROW_CAP} of {shown} — refine filters to narrow
          </p>
        )}
      </Panel>
    </div>
  )
}
