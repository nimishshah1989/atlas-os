// src/components/entity/HistorySection.tsx — ten years, as the two questions an FM actually asks
// of a track record: how did it do each year AGAINST THE INDEX, and how bad has it ever got.
//
// The FM: "the kind of data we have, there is so much historical context we can give. We can build
// really rich instrument pages" — with "more visual elements like line charts" and "using baseline
// to compare stuff everywhere".
//
// BOTH BASELINES ARE ZERO, AND ZERO IS DRAWN. A year bar reads against a line at nought, and the
// index bar sits beside it on the same axis, so "up 14 percent" and "up 14 while the index made
// 26" are visibly different sentences. The drawdown curve hangs from a line at nought, which is
// the instrument's own running high — the only baseline a drawdown has.
//
// NO NEW QUERY. Both come from the SAME close_tr series the chart above already drew (see
// lib/history.ts). A second query would be a second opinion about one instrument's own past.
import { Section } from '@/components/ui/Section'
import { InfoTip } from '@/components/ui/InfoTip'
import { formatIsoDate, formatPct } from '@/lib/format'
import { calendarYears, underwater, type ClosePoint } from '@/lib/history'

/** The widest bar on the chart, so one outlier year does not flatten every other row to a sliver.
 *  A minimum keeps a quiet decade from magnifying half a percent into a full-width bar. */
const floorScale = (values: number[]) => Math.max(0.1, ...values.map((v) => Math.abs(v)))

function YearBar({ value, scale, token }: { value: number | null; scale: number; token: string }) {
  if (value == null) return <span className="text-ink-3">—</span>
  const half = (Math.min(Math.abs(value) / scale, 1) * 50).toFixed(1)
  return (
    <span className="relative block h-[13px] w-full">
      {/* the baseline: nought, down the middle, drawn rather than implied */}
      <span className="absolute inset-y-0 left-1/2 w-px bg-edge-strong" />
      <span
        className="absolute inset-y-[2px] rounded-[2px]"
        style={{
          background: token,
          ...(value >= 0 ? { left: '50%', width: `${half}%` } : { right: '50%', width: `${half}%` }),
        }}
      />
    </span>
  )
}

function Years({ points, benchmark, symbol }: { points: readonly ClosePoint[]; benchmark: readonly ClosePoint[]; symbol: string }) {
  const rows = calendarYears(points, benchmark)
  if (rows.length === 0) return null
  const scale = floorScale(rows.flatMap((r) => [r.fund ?? 0, r.spy ?? 0]))

  return (
    <Section
      title="Year by year, against the S&P 500"
      note="total return on close_tr — splits and dividends"
    >
      <div className="panel overflow-x-auto">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>Year</th>
              <th style={{ textAlign: 'right' }}>{symbol}</th>
              <th style={{ width: '26%' }}>&nbsp;</th>
              <th style={{ textAlign: 'right' }}>S&P 500</th>
              <th style={{ width: '26%' }}>&nbsp;</th>
              <th style={{ textAlign: 'right' }}>
                Difference{' '}
                <InfoTip title="What is left after the index">
                  The fund&apos;s year minus the index&apos;s, in points, measured between the SAME
                  two sessions — never the fund&apos;s year against the index&apos;s calendar,
                  which would compare different numbers of trading days and call the gap skill.
                </InfoTip>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.year}>
                <td className="text-ink">
                  {r.year}
                  {r.partial && (
                    <span
                      className="ml-1 text-ink-3"
                      title={`Part year — measured from ${formatIsoDate(r.from)}, the earliest session on this board's spine, not from the previous 31 December.`}
                    >
                      part
                    </span>
                  )}
                </td>
                <td
                  className="num r text-ink"
                  title={`${formatIsoDate(r.from)} → ${formatIsoDate(r.to)}`}
                >
                  {formatPct(r.fund, 1, { sign: true })}
                </td>
                <td>
                  <YearBar value={r.fund} scale={scale} token={(r.fund ?? 0) >= 0 ? 'var(--color-pos)' : 'var(--color-neg)'} />
                </td>
                <td className="num r text-ink-2">{formatPct(r.spy, 1, { sign: true })}</td>
                <td>
                  <YearBar value={r.spy} scale={scale} token="var(--color-ink-3)" />
                </td>
                <td
                  className="num r"
                  style={{
                    color: r.excess == null ? undefined : r.excess >= 0 ? 'var(--color-pos)' : 'var(--color-neg)',
                  }}
                >
                  {formatPct(r.excess, 1, { sign: true })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

const W = 900
const H = 130

function Underwater({ points, symbol }: { points: readonly ClosePoint[]; symbol: string }) {
  const { curve, worst, current } = underwater(points)
  if (curve.length < 2 || worst == null || current == null) return null
  const depth = Math.min(worst.dd, -0.02) // a floor, so a serene fund still draws a readable band
  const x = (i: number) => (i / (curve.length - 1)) * W
  const y = (dd: number) => (dd / depth) * H
  const area =
    `M0,0 ` + curve.map((p, i) => `L${x(i).toFixed(1)},${y(p.dd).toFixed(1)}`).join(' ') + ` L${W},0 Z`

  return (
    <Section
      title="How far below its own high"
      note={`${formatIsoDate(curve[0].date)} → ${formatIsoDate(curve[curve.length - 1].date)}`}
    >
      <div className="panel px-3 py-3">
        <div className="mb-2 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-body">
          <span className="text-ink-2">
            Worst:{' '}
            <span className="num font-semibold" style={{ color: 'var(--color-neg)' }}>
              {formatPct(worst.dd, 1)}
            </span>{' '}
            <span className="text-ink-3">on {formatIsoDate(worst.date)}</span>
          </span>
          <span className="text-ink-2">
            Today:{' '}
            <span className="num font-semibold text-ink">{formatPct(current.dd, 1)}</span>{' '}
            <span className="text-ink-3">below its high of {formatIsoDate(current.peak)}</span>
          </span>
        </div>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="block h-[130px] w-full"
          role="img"
          aria-label={`${symbol}: distance below its running high, worst ${formatPct(worst.dd, 1)} on ${worst.date}`}
        >
          {/* the baseline IS the running high — every point hangs from it */}
          <line x1="0" y1="0.5" x2={W} y2="0.5" stroke="var(--color-edge-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          <path d={area} fill="var(--color-neg)" fillOpacity="0.16" />
          <polyline
            points={curve.map((p, i) => `${x(i).toFixed(1)},${y(p.dd).toFixed(1)}`).join(' ')}
            fill="none"
            stroke="var(--color-neg)"
            strokeWidth="1.25"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        <p className="mt-1 text-meta text-ink-3">
          Nought is a new high; the floor of the panel is {formatPct(depth, 0)}. Two funds at the
          same volatility are not the same fund if one of them spent a year this far under.
        </p>
      </div>
    </Section>
  )
}

/** The two history readings, drawn only where the spine carries enough to draw them. */
export function HistorySection({
  series,
  symbol,
}: {
  series: { points: readonly ClosePoint[]; benchmark: readonly ClosePoint[] }
  symbol: string
}) {
  if (series.points.length < 2) return null
  return (
    <>
      <Years points={series.points} benchmark={series.benchmark} symbol={symbol} />
      <Underwater points={series.points} symbol={symbol} />
    </>
  )
}
