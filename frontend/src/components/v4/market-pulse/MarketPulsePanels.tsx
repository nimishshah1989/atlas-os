// Market Pulse — the dumb panel renderers (breadth, cap-tier, macro, sector
// leadership, regime chip). All values arrive pre-fetched from foundation_staging;
// these only format + lay out. Units per the market_pulse recon: tier returns &
// spreads are FRACTIONS (×100 for display); macro values are already in `unit`.
import type { TierReturns, MacroRow } from '@/lib/queries/v6/market_pulse'
import { Panel } from '../ui/Panel'
import { SectorLeadershipBoard } from './SectorLeadershipBoard'
import { TermInfo } from '@/components/v6/shared/TermInfo'

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

// ── breadth detail — ABSOLUTE COUNTS of Nifty-500 names at three points in time, so the
// trend reads directly (today vs a week ago vs a month ago — no deltas to decode). ──
export type BreadthCountRow = { label: string; today: number | null; wkAgo: number | null; moAgo: number | null }
const fmtCount = (v: number | null) => (v == null ? '—' : Math.round(v).toLocaleString('en-IN'))
// Resolve a breadth metric row label → its glossary term (explainer on the row label).
const breadthTerm = (label: string): string | undefined => {
  const l = label.toLowerCase()
  if (l.includes('golden')) return 'golden_cross'
  if (l.includes('new high')) return 'net_new_highs'
  if (l.includes('ema')) return 'above_ema_count'
  return undefined
}
export function BreadthTablePanel({ rows, total, asOf }: { rows: BreadthCountRow[]; total: number | null; asOf: string | null }) {
  return (
    <Panel
      eyebrow="Participation"
      title="Market breadth"
      info={{ title: 'Market breadth', body: 'How many of the Nifty 500 are taking part — counts of names, not percentages. Above-EMA rows count names trading above that moving average; golden crosses are names whose 50-EMA sits above their 200-EMA; net new highs is 52-week highs minus lows. Each column is the count on that day, so you can read the trend directly.' }}
      bodyClassName="px-2 pb-3 pt-1"
    >
      <p className="px-2 pb-2 font-sans text-[11.5px] leading-snug text-txt-2">
        Number of Nifty 500 stocks{total ? <> out of <span className="font-num tabular-nums text-txt-1">{fmtCount(total)}</span></> : ''} participating — compare today with a week and a month ago to see if breadth is widening or narrowing.
      </p>
      <table className="tbl-centered w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-hair">
            <Head>Metric</Head><Head right>Today</Head><Head right>1 wk ago</Head><Head right>1 mo ago</Head>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-edge-hair/60 last:border-0">
              <td className="px-2 py-1.5 font-sans text-[12px] text-txt-2">{r.label}{breadthTerm(r.label) && <TermInfo term={breadthTerm(r.label)} />}</td>
              <td className="px-2 py-1.5 text-right"><Num>{fmtCount(r.today)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color="var(--color-txt-3)">{fmtCount(r.wkAgo)}</Num></td>
              <td className="px-2 py-1.5 text-right"><Num color="var(--color-txt-3)">{fmtCount(r.moAgo)}</Num></td>
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
      <p className="px-2 pb-2 font-sans text-[11.5px] leading-snug text-txt-2">
        How each size band has performed. <span className="text-txt-1">SC−LC</span> / <span className="text-txt-1">MC−LC</span> are small- and mid-cap returns minus large-cap — positive means smaller companies are leading the market.
      </p>
      <table className="tbl-centered w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-hair">
            <Head>Window</Head><Head right>Small 250<TermInfo term="tier_return" /></Head><Head right>Mid 150<TermInfo term="tier_return" /></Head><Head right>Nifty 100<TermInfo term="tier_return" /></Head><Head right>SC−LC<TermInfo term="tier_return" /></Head><Head right>MC−LC<TermInfo term="tier_return" /></Head>
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
          Small-cap relative strength<TermInfo term="smallcap_rs_z" /> is{' '}
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
      <table className="tbl-centered w-full border-collapse">
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

// ── sector leadership — concise Leading / Lagging split (top 5 vs bottom 5), each sector
// EXPANDABLE into the breakdown behind its score: a stocks × lens table. The interactive
// board (client) handles expand; this panel supplies framing + the always-on explainer. ──
import type { SectorRollup, StockLensRow } from './SectorLeadershipBoard'
export type { SectorRollup, StockLensRow } from './SectorLeadershipBoard'
export function SectorLeadershipPanel({ top, weak, stocksBySector }: {
  top: SectorRollup[]
  weak: SectorRollup[]
  stocksBySector: Record<string, StockLensRow[]>
}) {
  return (
    <Panel
      eyebrow="Rotation"
      title="Sector leadership"
      info={{ title: 'How to read this', body: <>Each sector is scored by the <strong>average conviction decile</strong> of its stocks — where each stock sits from 1 (bottom) to 10 (top) versus peers of its own size. <strong>Tech</strong> counts names with leading price action (top three deciles); <strong>fund</strong> counts names with leading financials. <strong>Click any sector to expand it</strong> into a table of its stocks scored across every lens.</>}}
    >
      <p className="mb-2.5 font-sans text-[11.5px] leading-snug text-txt-2">
        The 5 strongest and 5 weakest sectors by their stocks’ average conviction (1–10). <span className="text-txt-1">Click a sector</span> to expand its stocks scored across all five lenses.
      </p>
      <SectorLeadershipBoard top={top} weak={weak} stocksBySector={stocksBySector} />
    </Panel>
  )
}
