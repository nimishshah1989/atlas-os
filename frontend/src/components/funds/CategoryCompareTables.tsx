// The three tables on /funds/compare: trailing returns, rolling-return distribution, and the
// constituent funds. Formatting only — every number comes from lib/fundCategoryCurve.ts, so
// there is exactly one place where the maths can be wrong.
import Link from 'next/link'
import { Panel } from '@/components/ui/Panel'
import {
  growthReturn, PERIODS, rebase, rollingReturns, rollingStats, spanReturn, trailingReturn,
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
    // Skipped when the category index IS Nifty 500 (Flexi Cap, ELSS, Focused) — it was
    // listing the same series twice under two spellings.
    ...(indexLabel.toUpperCase() === 'NIFTY 500'
      ? [] : [{ label: 'Nifty 500', pts: pick(rows, 'nifty500') }]),
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

/**
 * Which funds actually delivered — the point of the table, and what a raw return column alone
 * cannot answer. Each fund is shown against the category composite and against the benchmark,
 * ranked into quartiles, with its size.
 *
 * Only full-window funds are ranked. A fund present for three months of a three-year window has
 * a return that is not comparable to the rest, and sorting it in beside them (as this table
 * first did) invites exactly the wrong read; those rows are listed separately with their span.
 */
export function ConstituentsTable({
  funds, rows, from, to, categoryLabel, indexLabel,
}: {
  funds: ConstituentRow[]
  /** Displayed-period composite, for the category and benchmark yardsticks. */
  rows: CompositeRow[]
  from: string
  to: string
  categoryLabel: string
  indexLabel: string
}) {
  const compPts = rows.map((r) => ({ d: r.d, v: r.v }))
  const benchPts = pick(rows, 'catIndex')

  // Every comparison is made over the FUND'S OWN span. The first cut compared each fund's
  // cumulative return against the composite's CAGR — different units, so every fund "beat"
  // the category and the excess column read +123%. Annualising both, over the same dates,
  // is the only way the subtraction means anything.
  const between = (pts: CurvePoint[], a: string, b: string): SpanReturn | null =>
    spanReturn(pts.filter((p) => p.d >= a && p.d <= b))
  const days = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000)

  const withRet = funds.map((f) => {
    const self = growthReturn(1 + f.pct / 100, days(f.first, f.last))
    const cat = between(compPts, f.first, f.last)
    const bench = between(benchPts, f.first, f.last)
    return {
      ...f,
      ret: self,
      vsCat: self && cat ? self.pct - cat.pct : null,
      vsBench: self && bench ? self.pct - bench.pct : null,
    }
  })
  type Row = (typeof withRet)[number]

  const bySelf = (a: Row, b: Row) => (b.ret?.pct ?? -Infinity) - (a.ret?.pct ?? -Infinity)
  const ranked = withRet.filter((f) => f.full).sort(bySelf)
  const partial = withRet.filter((f) => !f.full).sort(bySelf)
  const beatCat = ranked.filter((f) => (f.vsCat ?? -1) > 0).length
  const beatBench = ranked.filter((f) => (f.vsBench ?? -1) > 0).length
  const catWhole = spanReturn(compPts)
  const benchWhole = spanReturn(benchPts)

  const quartile = (i: number): string =>
    ranked.length < 4 ? '' : `Q${Math.min(4, Math.floor((i * 4) / ranked.length) + 1)}`

  const aum = (v: number | null): string =>
    v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)

  const row = (f: Row, i: number | null) => (
    <tr key={f.mstarId} className="border-b border-edge-hair last:border-0">
      <td className={txt}>
        <Link href={`/funds/${f.mstarId}`} className="text-txt-1 no-underline hover:text-brand hover:underline">
          {f.name}
        </Link>
        {f.amc && <span className="ml-2 font-sans text-[10px] text-txt-3">{f.amc}</span>}
      </td>
      <td className={`${num} text-txt-2`}>{aum(f.aumCr)}</td>
      <td className={`${num} ${tone(f.ret?.pct)}`}>
        {pct(f.ret?.pct)}
        {f.ret?.annualised && <span className="ml-1 text-[9px] text-txt-3">p.a.</span>}
      </td>
      <td className={`${num} ${tone(f.vsCat)}`}>{pct(f.vsCat)}</td>
      <td className={`${num} ${tone(f.vsBench)}`}>{pct(f.vsBench)}</td>
      <td className={`${num} text-txt-3`}>
        {i == null ? `${f.first} → ${f.last}` : quartile(i)}
      </td>
    </tr>
  )

  return (
    <Panel eyebrow="Constituents"
           title={`${ranked.length} fund${ranked.length === 1 ? '' : 's'} across the full window`}
           info={{
             title: 'Reading this table',
             body: (
               <>Ranked on return over the whole window, so every fund here is measured on the
               same span. <strong>vs Category</strong> is the fund minus the equal-weighted
               composite; <strong>vs {indexLabel}</strong> is the fund minus the benchmark.
               Quartiles are within this category. Funds that joined or left mid-window are
               listed underneath, unranked — their returns cover a different span and are not
               comparable.</>
             ),
           }}
           bodyClassName="overflow-x-auto p-0">
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Fund</th>
            <th className={`${head} text-right`}>AUM ₹cr</th>
            <th className={`${head} text-right`}>Return</th>
            <th className={`${head} text-right`}>vs Category</th>
            <th className={`${head} text-right`}>vs {indexLabel}</th>
            <th className={`${head} text-right`}>Quartile</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((f, i) => row(f, i))}
          {partial.length > 0 && (
            <tr className="border-b border-edge-rule bg-surface-raised">
              <td colSpan={6} className={`${head} text-left`}>
                Partial window — not ranked ({partial.length})
              </td>
            </tr>
          )}
          {partial.map((f) => row(f, null))}
        </tbody>
      </table>
      <p className="px-3 py-2 font-sans text-[11px] text-txt-3">
        {ranked.length > 0 ? (
          <>
            <strong className="text-txt-2">{beatCat} of {ranked.length}</strong> beat the{' '}
            {categoryLabel} composite ({pct(catWhole?.pct)}) and{' '}
            <strong className="text-txt-2">{beatBench} of {ranked.length}</strong> beat{' '}
            {indexLabel} ({pct(benchWhole?.pct)}) over {from} → {to}.{' '}
          </>
        ) : (
          <>Returns cover {from} → {to}. </>
        )}
        Half the funds beating an equal-weighted composite is arithmetic, not skill — the
        benchmark column is the one that carries information.
      </p>
    </Panel>
  )
}
