// Market Pulse — the dumb panel renderers (breadth, cap-tier, macro, sector
// leadership, regime chip). All values arrive pre-fetched from foundation_staging;
// these only format + lay out. Units per the market_pulse recon: tier returns &
// spreads are FRACTIONS (×100 for display); macro values are already in `unit`.
import Link from 'next/link'
import type { TierReturns, MacroRow, BreadthTableRow } from '@/lib/queries/v6/market_pulse'
import { Panel } from '../ui/Panel'
import { DecileMeter } from '../ui/DecileMeter'

// ── formatting ───────────────────────────────────────────────────────────────
const signed = (n: number, d: number) => `${n >= 0 ? '+' : ''}${n.toFixed(d)}`
const toneColor = (n: number | null | undefined) =>
  n == null ? 'var(--color-txt-2)' : n > 0 ? 'var(--color-sig-pos)' : n < 0 ? 'var(--color-sig-neg)' : 'var(--color-txt-2)'
const Num = ({ children, color }: { children: React.ReactNode; color?: string }) => (
  <span className="font-num text-[12px] tabular-nums" style={{ color: color ?? 'var(--color-txt-1)' }}>{children}</span>
)
const Head = ({ children, right }: { children: React.ReactNode; right?: boolean }) => (
  <th className={`px-2 py-2 font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3 ${right ? 'text-right' : 'text-left'}`}>{children}</th>
)

// ── regime verdict chip ──────────────────────────────────────────────────────
export function RegimeChip({ state, deploymentPct }: { state: string; deploymentPct: number | null }) {
  const s = state.toLowerCase()
  const color = /on|bull|strong|expansion/.test(s)
    ? 'var(--color-sig-pos)'
    : /off|bear|weak|contraction|stress/.test(s)
      ? 'var(--color-sig-neg)'
      : /caution|neutral|mixed|transition/.test(s)
        ? 'var(--color-sig-warn)'
        : 'var(--color-brand)'
  return (
    <div className="inline-flex items-center gap-2.5 rounded-full border border-edge-rule bg-surface-raised px-3.5 py-1.5">
      <span className="h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 8px -1px ${color}` }} />
      <span className="font-display text-[13px] font-semibold" style={{ color }}>{state}</span>
      {deploymentPct != null && (
        <span className="font-num text-[11px] tabular-nums text-txt-2">· {deploymentPct}% deployed</span>
      )}
    </div>
  )
}

// ── breadth detail (§3.e/§3.f — # stocks as integers, not decimals) ──────────
function fmtBreadth(kind: BreadthTableRow['kind'], v: number | null): string {
  if (v == null) return '—'
  if (kind === 'pct') return `${v.toFixed(1)}%`
  if (kind === 'count') return Math.round(v).toLocaleString('en-IN')
  if (kind === 'ratio') return v.toFixed(2)
  return signed(v, 0)
}
function fmtBreadthDelta(kind: BreadthTableRow['kind'], v: number | null): string {
  if (v == null) return '—'
  if (kind === 'pct') return `${signed(v, 1)}pp`
  if (kind === 'ratio') return signed(v, 2)
  return signed(v, 0)
}
export function BreadthTablePanel({ rows, asOf }: { rows: BreadthTableRow[]; asOf: string | null }) {
  return (
    <Panel
      eyebrow="Participation"
      title="Market breadth"
      info={{ title: 'Market breadth', body: 'How many Nifty 500 names participate in the move. Counts are instruments, not percentages; Δ columns are the change over the trailing week and month.' }}
      bodyClassName="px-2 pb-3 pt-1"
    >
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-hair">
            <Head>Metric</Head><Head right>Today</Head><Head right>Δ 1w</Head><Head right>Δ 1m</Head>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.metric} className="border-b border-edge-hair/60 last:border-0">
              <td className="px-2 py-1.5 font-sans text-[12px] text-txt-2">{r.label}</td>
              <td className="px-2 py-1.5 text-right"><Num>{fmtBreadth(r.kind, r.today)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(r.d1w)}>{fmtBreadthDelta(r.kind, r.d1w)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(r.d1m)}>{fmtBreadthDelta(r.kind, r.d1m)}</Num></td>
            </tr>
          ))}
        </tbody>
      </table>
      {asOf && <p className="px-2 pt-2 font-num text-[9px] uppercase tracking-wider text-txt-3">as of {asOf}</p>}
    </Panel>
  )
}

// ── cap-tier returns (§3.g — the "Tier Leadership" table, made readable) ──────
export function TierReturnsPanel({ data }: { data: TierReturns }) {
  const pct = (v: number | null) => (v == null ? '—' : `${signed(v * 100, 1)}%`)
  const z = data.smallcap_rs_z
  return (
    <Panel
      eyebrow="Cap-tier leadership"
      title="Returns by size"
      info={{ title: 'Returns by size', body: 'Total return of each size cohort over five windows, plus the small/mid-cap spread vs large-cap. A positive spread means smaller caps are leading. The z-score gauges how stretched small-cap leadership is vs its own 1-year norm.' }}
      bodyClassName="px-2 pb-3 pt-1"
    >
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-hair">
            <Head>Window</Head><Head right>Small 250</Head><Head right>Mid 150</Head><Head right>Nifty 100</Head><Head right>SC−LC</Head><Head right>MC−LC</Head>
          </tr>
        </thead>
        <tbody>
          {data.windows.map((w) => (
            <tr key={w.label} className="border-b border-edge-hair/60 last:border-0">
              <td className="px-2 py-1.5 font-num text-[11px] uppercase tracking-wider text-txt-3">{w.label}</td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(w.sc)}>{pct(w.sc)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(w.mc)}>{pct(w.mc)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(w.lc)}>{pct(w.lc)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(w.sc_lc)}>{pct(w.sc_lc)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(w.mc_lc)}>{pct(w.mc_lc)}</Num></td>
            </tr>
          ))}
        </tbody>
      </table>
      {z != null && (
        <p className="px-2 pt-2.5 font-sans text-[11px] text-txt-2">
          Small-cap relative strength is{' '}
          <span className="font-num tabular-nums" style={{ color: toneColor(z) }}>{signed(z, 1)}σ</span>{' '}
          vs its 1-year norm — {Math.abs(z) >= 1.5 ? 'stretched' : 'within normal range'}.
        </p>
      )}
    </Panel>
  )
}

// ── macro context ─────────────────────────────────────────────────────────────
function fmtMacro(unit: string, v: number | null): string {
  if (v == null) return '—'
  if (unit === '%') return `${v.toFixed(2)}%`
  if (unit === '₹') return `₹${v.toFixed(2)}`
  if (unit === '₹cr') return `₹${Math.round(v).toLocaleString('en-IN')}cr`
  return v.toFixed(2)
}
export function MacroPanel({ rows, asOf }: { rows: MacroRow[]; asOf: string | null }) {
  return (
    <Panel
      eyebrow="Backdrop"
      title="Macro context"
      info={{ title: 'Macro context', body: 'The rates, currency and flow backdrop equities trade against. Δ 1m is the one-month change; green/red marks the direction of travel, not whether it helps or hurts.' }}
      bodyClassName="px-2 pb-3 pt-1"
    >
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-hair">
            <Head>Indicator</Head><Head right>Value</Head><Head right>Δ 1d</Head><Head right>Δ 1m</Head>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-edge-hair/60 last:border-0">
              <td className="px-2 py-1.5 font-sans text-[12px] text-txt-2">{r.label}</td>
              <td className="px-2 py-1.5 text-right"><Num>{fmtMacro(r.unit, r.value)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(r.d1)}>{r.d1 == null ? '—' : signed(r.d1, 2)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color={toneColor(r.d1m)}>{r.d1m == null ? '—' : signed(r.d1m, 2)}</Num></td>
            </tr>
          ))}
        </tbody>
      </table>
      {asOf && <p className="px-2 pt-2 font-num text-[9px] uppercase tracking-wider text-txt-3">as of {asOf}</p>}
    </Panel>
  )
}

// ── sector leadership (§3.c — green vs deteriorating, derived from real stock
// strength; "deteriorating" = the weakest current cohorts pending MoM deltas) ──
export type SectorRollup = { name: string; avg: number; n: number; leaders: number }
function SectorRow({ s }: { s: SectorRollup }) {
  return (
    <Link
      href={`/sectors/${encodeURIComponent(s.name)}`}
      className="-mx-2 flex items-center gap-3 rounded-tile px-2 py-1.5 transition-colors hover:bg-surface-raised"
    >
      <span className="w-[132px] shrink-0 truncate font-sans text-[12px] text-txt-1">{s.name}</span>
      <span className="flex-1"><DecileMeter decile={Math.round(s.avg)} size="sm" /></span>
      <span className="w-[34px] shrink-0 text-right font-num text-[12px] tabular-nums text-txt-1">{s.avg.toFixed(1)}</span>
      <span className="w-[64px] shrink-0 text-right font-num text-[10px] tabular-nums text-txt-3">{s.leaders}/{s.n} lead</span>
    </Link>
  )
}
export function SectorLeadershipPanel({ top, weak }: { top: SectorRollup[]; weak: SectorRollup[] }) {
  return (
    <Panel
      eyebrow="Rotation"
      title="Sector leadership"
      info={{ title: 'Sector leadership', body: 'Sectors ranked by the average conviction decile of their constituents (D10 = top). The left column leads; the right column lags. Click a sector to drill in.' }}
    >
      <div className="grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-sig-pos">Leading</p>
          {top.map((s) => <SectorRow key={s.name} s={s} />)}
        </div>
        <div>
          <p className="mb-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-sig-neg">Lagging</p>
          {weak.map((s) => <SectorRow key={s.name} s={s} />)}
        </div>
      </div>
    </Panel>
  )
}
