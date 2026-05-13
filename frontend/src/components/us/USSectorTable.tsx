// allow-large: sector table requires full column set — 14 columns, sortable, with derived state + decision logic
'use client'
import { useState } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { USSectorRow } from '@/lib/queries/us-sectors'

// ── Derived logic ────────────────────────────────────────────────────────────

// rs_pctile values are stored 0-1 (rank/count). 0.65 = 65th percentile.
function deriveSectorState(avgRsPctile: number): 'Overweight' | 'Neutral' | 'Underweight' | 'Avoid' {
  if (avgRsPctile >= 0.60) return 'Overweight'
  if (avgRsPctile >= 0.42) return 'Neutral'
  if (avgRsPctile >= 0.28) return 'Underweight'
  return 'Avoid'
}

// rs_momentum = avg(rs_pctile_1m) - avg(rs_pctile_3m), also in 0-1 delta range
function deriveSectorDecision(rs: number, partRs: number, mom: number): string {
  if (rs >= 0.62 && partRs >= 35 && mom >= 0) return 'ENTER'
  if (rs >= 0.55 || (rs >= 0.48 && mom > 0.03)) return 'WATCH'
  if (rs >= 0.42 && mom >= -0.02) return 'HOLD'
  if (rs >= 0.30) return 'PASS'
  return 'EXIT'
}

// ── Color maps ───────────────────────────────────────────────────────────────

const STATE_COLORS = {
  Overweight:  { bg: 'bg-teal/10',   text: 'text-teal',        dot: 'bg-teal' },
  Neutral:     { bg: 'bg-amber-50',  text: 'text-amber-700',   dot: 'bg-amber-500' },
  Underweight: { bg: 'bg-orange-50', text: 'text-orange-700',  dot: 'bg-orange-400' },
  Avoid:       { bg: 'bg-red-50',    text: 'text-red-700',     dot: 'bg-red-500' },
}

const DECISION_COLORS: Record<string, string> = {
  ENTER: 'bg-teal text-white',
  WATCH: 'bg-teal/10 text-teal',
  HOLD:  'bg-paper-rule/40 text-ink-secondary',
  PASS:  'bg-orange-50 text-orange-700',
  EXIT:  'bg-red-50 text-red-700',
}

// ── Format helpers ────────────────────────────────────────────────────────────

function fmtPct(v: string | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const n = parseFloat(v) * 100
  if (isNaN(n)) return { text: '—', cls: 'text-ink-tertiary' }
  return {
    text: (n >= 0 ? '+' : '') + n.toFixed(1) + '%',
    cls:  n >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function fmtRaw(v: string | null, decimals = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v)
  return isNaN(n) ? '—' : n.toFixed(decimals)
}

// rs_momentum is a pctile delta (0-1 range), convert to pp for display
function fmtMom(v: string | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const n = parseFloat(v)
  if (isNaN(n)) return { text: '—', cls: 'text-ink-tertiary' }
  const pp = n * 100
  return {
    text: (pp >= 0 ? '+' : '') + pp.toFixed(1) + 'pp',
    cls:  n >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function ProgressBar({ value, max = 100, colorCls }: { value: number; max?: number; colorCls: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1 bg-paper-rule/30 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${colorCls}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-sans text-[11px] tabular-nums text-ink-secondary w-7 text-right">
        {Math.round(value)}
      </span>
    </div>
  )
}

// ── Sort types ────────────────────────────────────────────────────────────────

type SortCol =
  | 'sector' | 'state' | 'decision' | 'rs_pctile' | 'rs_mom'
  | 'leader_strong' | 'part_rs' | 'part_30w' | 'ret_1m' | 'ret_3m'
  | 'ret_6m' | 'extension' | 'vol_63' | 'live_count'

type SortDir = 'asc' | 'desc'

// ── Enriched row (computed fields added to raw query row) ─────────────────────

type EnrichedRow = USSectorRow & {
  _rsPctile: number
  _rsMom: number
  _partRs: number
  _state: ReturnType<typeof deriveSectorState>
  _decision: string
}

function enrich(r: USSectorRow): EnrichedRow {
  const _rsPctile = parseFloat(r.avg_rs_pctile_3m_vt ?? '0') || 0
  const _rsMom    = parseFloat(r.rs_momentum ?? '0') || 0
  const _partRs   = parseFloat(r.participation_rs ?? '0') || 0
  return {
    ...r,
    _rsPctile,
    _rsMom,
    _partRs,
    _state:    deriveSectorState(_rsPctile),
    _decision: deriveSectorDecision(_rsPctile, _partRs, _rsMom),
  }
}

function sortRows(rows: EnrichedRow[], col: SortCol, dir: SortDir): EnrichedRow[] {
  return [...rows].sort((a, b) => {
    let va: number | string = 0
    let vb: number | string = 0
    switch (col) {
      case 'sector':       va = a.gics_sector;  vb = b.gics_sector;  break
      case 'state':        va = a._state;        vb = b._state;        break
      case 'decision':     va = a._decision;     vb = b._decision;     break
      case 'rs_pctile':    va = a._rsPctile;     vb = b._rsPctile;     break
      case 'rs_mom':       va = a._rsMom;        vb = b._rsMom;        break
      case 'leader_strong': va = a.rs_state_leader + a.rs_state_strong; vb = b.rs_state_leader + b.rs_state_strong; break
      case 'part_rs':      va = a._partRs;       vb = b._partRs;       break
      case 'part_30w':     va = parseFloat(a.participation_30w ?? '0') || 0; vb = parseFloat(b.participation_30w ?? '0') || 0; break
      case 'ret_1m':       va = parseFloat(a.avg_ret_1m ?? '0') || 0;  vb = parseFloat(b.avg_ret_1m ?? '0') || 0;  break
      case 'ret_3m':       va = parseFloat(a.avg_ret_3m ?? '0') || 0;  vb = parseFloat(b.avg_ret_3m ?? '0') || 0;  break
      case 'ret_6m':       va = parseFloat(a.avg_ret_6m ?? '0') || 0;  vb = parseFloat(b.avg_ret_6m ?? '0') || 0;  break
      case 'extension':    va = parseFloat(a.avg_extension_pct ?? '0') || 0; vb = parseFloat(b.avg_extension_pct ?? '0') || 0; break
      case 'vol_63':       va = parseFloat(a.avg_vol_63 ?? '0') || 0;  vb = parseFloat(b.avg_vol_63 ?? '0') || 0;  break
      case 'live_count':   va = a.live_count;    vb = b.live_count;    break
    }
    if (typeof va === 'string' && typeof vb === 'string') {
      return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    }
    return dir === 'asc' ? (va as number) - (vb as number) : (vb as number) - (va as number)
  })
}

// ── Column header with sort ────────────────────────────────────────────────

function TH({
  col, label, active, dir, onSort, align = 'right',
}: {
  col: SortCol
  label: string
  active: SortCol
  dir: SortDir
  onSort: (c: SortCol) => void
  align?: 'left' | 'right'
}) {
  const isActive = active === col
  return (
    <th
      className={`py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide cursor-pointer select-none whitespace-nowrap ${align === 'right' ? 'text-right' : 'text-left'}`}
      onClick={() => onSort(col)}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        {isActive
          ? dir === 'desc'
            ? <ChevronDown className="w-3 h-3 text-teal" />
            : <ChevronUp className="w-3 h-3 text-teal" />
          : <ChevronDown className="w-3 h-3 opacity-0 group-hover:opacity-50" />
        }
      </span>
    </th>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

type Props = { sectors: USSectorRow[] }

export function USSectorTable({ sectors }: Props) {
  const [sortCol, setSortCol] = useState<SortCol>('rs_pctile')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const rows = sortRows(sectors.map(enrich), sortCol, sortDir)

  function handleSort(col: SortCol) {
    if (col === sortCol) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortCol(col)
      setSortDir('desc')
    }
  }

  const thProps = { active: sortCol, dir: sortDir, onSort: handleSort }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse min-w-[1100px]">
        <thead>
          <tr className="border-b border-paper-rule">
            <TH col="sector"       label="Sector"      {...thProps} align="left" />
            <TH col="state"        label="State"       {...thProps} align="left" />
            <TH col="decision"     label="Decision"    {...thProps} align="left" />
            <TH col="rs_pctile"    label="RS Pctile"   {...thProps} />
            <TH col="rs_mom"       label="RS Mom"      {...thProps} />
            <TH col="leader_strong" label="Ldr/Str"    {...thProps} />
            <TH col="part_rs"      label="Part RS%"    {...thProps} />
            <TH col="part_30w"     label="30W%"        {...thProps} />
            <TH col="ret_1m"       label="1M Ret"      {...thProps} />
            <TH col="ret_3m"       label="3M Ret"      {...thProps} />
            <TH col="ret_6m"       label="6M Ret"      {...thProps} />
            <TH col="extension"    label="Ext%"        {...thProps} />
            <TH col="vol_63"       label="Vol 63D"     {...thProps} />
            <TH col="live_count"   label="Stocks"      {...thProps} />
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const sc = STATE_COLORS[r._state]
            const partRaw = parseFloat(r.participation_30w ?? '0') || 0
            const volRaw  = parseFloat(r.avg_vol_63 ?? '0') || 0
            const mom     = fmtMom(r.rs_momentum)
            const ret1m   = fmtPct(r.avg_ret_1m)
            const ret3m   = fmtPct(r.avg_ret_3m)
            const ret6m   = fmtPct(r.avg_ret_6m)
            const ext     = fmtPct(r.avg_extension_pct)
            const leaderStrong = r.rs_state_leader + r.rs_state_strong

            return (
              <tr
                key={r.gics_sector}
                className="border-b border-paper-rule/40 hover:bg-paper-rule/10 transition-colors"
              >
                {/* Sector name — links to stocks tab pre-filtered by sector */}
                <td className="py-2.5 px-2 font-sans text-xs whitespace-nowrap">
                  <Link
                    href={`/us?tab=Stocks&sector=${encodeURIComponent(r.gics_sector)}`}
                    className="text-ink-primary hover:text-teal hover:underline transition-colors"
                  >
                    {r.gics_sector}
                  </Link>
                </td>

                {/* State badge */}
                <td className="py-2.5 px-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium ${sc.bg} ${sc.text}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
                    {r._state}
                  </span>
                </td>

                {/* Decision badge */}
                <td className="py-2.5 px-2">
                  <span className={`inline-block px-2 py-0.5 rounded-sm font-sans text-[11px] font-semibold ${DECISION_COLORS[r._decision] ?? 'bg-paper-rule/20 text-ink-secondary'}`}>
                    {r._decision}
                  </span>
                </td>

                {/* RS Pctile progress bar — convert 0-1 to 0-100 for bar */}
                <td className="py-2.5 px-2 min-w-[110px]">
                  <ProgressBar
                    value={r._rsPctile * 100}
                    colorCls={
                      r._rsPctile >= 0.60 ? 'bg-teal' :
                      r._rsPctile >= 0.42 ? 'bg-amber-500' :
                      r._rsPctile >= 0.28 ? 'bg-orange-400' : 'bg-signal-neg'
                    }
                  />
                </td>

                {/* RS Momentum */}
                <td className={`py-2.5 px-2 font-sans text-xs tabular-nums text-right ${mom.cls}`}>
                  {mom.text}
                </td>

                {/* Leader / Strong count */}
                <td className="py-2.5 px-2 text-right">
                  <span className="font-sans text-xs tabular-nums text-ink-primary">{leaderStrong}</span>
                  <span className="ml-1">
                    {r.rs_state_leader > 0 && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-teal mr-0.5" title={`${r.rs_state_leader} Leader`} />
                    )}
                    {r.rs_state_strong > 0 && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-teal/60" title={`${r.rs_state_strong} Strong`} />
                    )}
                  </span>
                </td>

                {/* Participation RS */}
                <td className="py-2.5 px-2 min-w-[100px]">
                  <ProgressBar
                    value={r._partRs}
                    colorCls={r._partRs >= 50 ? 'bg-teal' : r._partRs >= 30 ? 'bg-amber-500' : 'bg-signal-neg'}
                  />
                </td>

                {/* Participation 30W */}
                <td className="py-2.5 px-2 min-w-[100px]">
                  <ProgressBar
                    value={partRaw}
                    colorCls={partRaw >= 60 ? 'bg-teal' : partRaw >= 40 ? 'bg-amber-500' : 'bg-signal-neg'}
                  />
                </td>

                {/* 1M / 3M / 6M returns */}
                <td className={`py-2.5 px-2 font-sans text-xs tabular-nums text-right ${ret1m.cls}`}>
                  {ret1m.text}
                </td>
                <td className={`py-2.5 px-2 font-sans text-xs tabular-nums text-right ${ret3m.cls}`}>
                  {ret3m.text}
                </td>
                <td className={`py-2.5 px-2 font-sans text-xs tabular-nums text-right ${ret6m.cls}`}>
                  {ret6m.text}
                </td>

                {/* Extension % */}
                <td className={`py-2.5 px-2 font-sans text-xs tabular-nums text-right ${ext.cls}`}>
                  {ext.text}
                </td>

                {/* Vol 63D */}
                <td className="py-2.5 px-2 font-sans text-xs tabular-nums text-right text-ink-secondary">
                  {fmtRaw(r.avg_vol_63, 1) === '—' ? '—' : (volRaw * 100).toFixed(1) + '%'}
                </td>

                {/* Live count */}
                <td className="py-2.5 px-2 font-sans text-xs tabular-nums text-right text-ink-secondary">
                  {r.live_count}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="py-8 text-center font-sans text-sm text-ink-tertiary">No sector data available.</p>
      )}
    </div>
  )
}
