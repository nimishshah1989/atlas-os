// The three tables on /funds/compare: trailing returns, rolling-return distribution, and the
// constituent funds. Formatting only — every number comes from lib/fundCategoryCurve.ts, so
// there is exactly one place where the maths can be wrong.
import Link from 'next/link'
import { Panel } from '@/components/ui/Panel'
import {
  PERIODS, rebase, rollingReturns, rollingStats, trailingReturn,
  type CurvePoint, type SpanReturn,
} from '@/lib/fundCategoryCurve'
import type { CompositeRow, ConstituentRow } from '@/lib/queries/fund_category_curve'

const pct = (v: number | null | undefined): string =>
  v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}%`

const tone = (v: number | null | undefined): string =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const num = 'px-3 py-1.5 text-right font-num text-[12px] tabular-nums'
const txt = 'px-3 py-1.5 text-left font-sans text-[12px]'
const head = 'px-3 py-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3'

const pick = (rows: CompositeRow[], key: 'nifty50' | 'nifty500' | 'catIndex'): CurvePoint[] =>
  rows.filter((r) => r[key] != null).map((r) => ({ d: r.d, v: r[key] as number }))

function ReturnCell({ r }: { r: SpanReturn | null }) {
  return (
    <td className={`${num} ${tone(r?.pct)}`} title={r ? `${r.days} days` : 'insufficient history'}>
      {pct(r?.pct)}
      {r?.annualised && <span className="ml-1 text-[9px] text-txt-3">p.a.</span>}
    </td>
  )
}

export function ReturnsTable({
  rows, categoryLabel, indexLabel,
}: { rows: CompositeRow[]; categoryLabel: string; indexLabel: string }) {
  const series: { label: string; pts: CurvePoint[] }[] = [
    { label: `${categoryLabel} composite`, pts: rows.map((r) => ({ d: r.d, v: r.v })) },
    { label: indexLabel, pts: pick(rows, 'catIndex') },
    { label: 'Nifty 500', pts: pick(rows, 'nifty500') },
    { label: 'Nifty 50', pts: pick(rows, 'nifty50') },
  ]

  return (
    <Panel eyebrow="Trailing returns" title="Composite vs benchmarks"
           bodyClassName="overflow-x-auto p-0">
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Series</th>
            {PERIODS.map((p) => <th key={p.key} className={`${head} text-right`}>{p.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.label} className="border-b border-edge-hair last:border-0">
              <td className={`${txt} text-txt-1`}>{s.label}</td>
              {PERIODS.map((p) => (
                <ReturnCell key={p.key} r={trailingReturn(s.pts, p.months)} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 font-sans text-[11px] text-txt-3">
        Absolute return up to one year; CAGR on actual day count beyond it (marked p.a.).
        A dash means the series does not reach back that far — never a zero.
        Benchmarks are price-return and exclude dividends.
      </p>
    </Panel>
  )
}

export function RollingStatsTable({
  rows, shown, windowYears, categoryLabel, indexLabel,
}: {
  /** Full series, reaching back a rolling window before `shown`. */
  rows: CompositeRow[]
  /** The displayed period — windows are trimmed to it so the stats describe what is on screen. */
  shown: CompositeRow[]
  windowYears: number
  categoryLabel: string
  indexLabel: string
}) {
  const from = shown[0]?.d ?? ''
  const trim = (pts: CurvePoint[]) => pts.filter((p) => p.d >= from)
  const comp = trim(rollingReturns(rows.map((r) => ({ d: r.d, v: r.v })), windowYears))
  const bench = trim(rollingReturns(rebase(pick(rows, 'catIndex')), windowYears))
  const cs = rollingStats(comp, bench)
  const bs = rollingStats(bench, [])

  if (!cs) {
    return (
      <Panel eyebrow={`Rolling ${windowYears}-year returns`} title="Distribution">
        <p className="font-sans text-[13px] text-txt-2">
          The selected window is shorter than {windowYears} year{windowYears > 1 ? 's' : ''},
          so there are no rolling windows to summarise.
        </p>
      </Panel>
    )
  }

  const cols: [string, number | null][] = [
    ['Worst', cs.min], ['25th', cs.p25], ['Median', cs.median],
    ['75th', cs.p75], ['Best', cs.max],
  ]
  const bcols: [string, number | null][] = bs
    ? [['Worst', bs.min], ['25th', bs.p25], ['Median', bs.median], ['75th', bs.p75], ['Best', bs.max]]
    : []

  return (
    <Panel eyebrow={`Rolling ${windowYears}-year returns`}
           title={`Distribution across ${cs.n} window${cs.n === 1 ? '' : 's'}`}
           bodyClassName="overflow-x-auto p-0">
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Series</th>
            {cols.map(([l]) => <th key={l} className={`${head} text-right`}>{l}</th>)}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-edge-hair">
            <td className={`${txt} text-txt-1`}>{categoryLabel} composite</td>
            {cols.map(([l, v]) => <td key={l} className={`${num} ${tone(v)}`}>{pct(v)}</td>)}
          </tr>
          {bcols.length > 0 && (
            <tr>
              <td className={`${txt} text-txt-1`}>{indexLabel}</td>
              {bcols.map(([l, v]) => <td key={l} className={`${num} ${tone(v)}`}>{pct(v)}</td>)}
            </tr>
          )}
        </tbody>
      </table>
      <p className="px-3 py-2 font-sans text-[11px] text-txt-2">
        {cs.beatRate == null
          ? `No overlapping ${indexLabel} history to compare against.`
          : `The composite beat ${indexLabel} in ${cs.beatRate.toFixed(0)}% of the ${cs.n} rolling ${windowYears}-year window${cs.n === 1 ? '' : 's'}.`}
        {cs.n < 12 && (
          <span className="text-txt-3">
            {' '}Too few windows to read as a distribution — widen the period, or shorten the
            rolling window, to get overlapping ones.
          </span>
        )}
      </p>
    </Panel>
  )
}

export function ConstituentsTable({
  funds, from, to,
}: { funds: ConstituentRow[]; from: string; to: string }) {
  const partial = funds.filter((f) => !f.full).length
  return (
    <Panel eyebrow="Constituents"
           title={`${funds.length} fund${funds.length === 1 ? '' : 's'} in the composite`}
           bodyClassName="overflow-x-auto p-0">
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Fund</th>
            <th className={`${head} text-left`}>From</th>
            <th className={`${head} text-left`}>To</th>
            <th className={`${head} text-right`}>Return</th>
          </tr>
        </thead>
        <tbody>
          {funds.map((f) => (
            <tr key={f.mstarId} className="border-b border-edge-hair last:border-0">
              <td className={txt}>
                <Link href={`/funds/${f.mstarId}`} className="text-txt-1 no-underline hover:text-brand">
                  {f.name}
                </Link>
                {!f.full && (
                  <span className="ml-2 font-num text-[9px] uppercase tracking-wider text-txt-3">
                    partial
                  </span>
                )}
              </td>
              <td className={`${txt} text-txt-2`}>{f.first}</td>
              <td className={`${txt} text-txt-2`}>{f.last}</td>
              <td className={`${num} ${tone(f.pct)}`}>{pct(f.pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 font-sans text-[11px] text-txt-3">
        Returns are each fund&apos;s own span inside {from} → {to}, so they are not comparable
        across funds with different spans.
        {partial > 0 && ` ${partial} fund${partial > 1 ? 's' : ''} covered only part of the window.`}
      </p>
    </Panel>
  )
}
