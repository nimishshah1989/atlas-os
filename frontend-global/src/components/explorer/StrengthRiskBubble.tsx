'use client'
// src/components/explorer/StrengthRiskBubble.tsx — two thousand funds as one picture.
//
// WHAT THE AXES ARE, AND WHY THEY ARE NOT THE OBVIOUS ONES. India's 2×2 plots strength against a
// leader FLAG, which is 0 or 1, so five hundred stocks stack on two lines and have to be jittered
// apart. Worse, both of its axes are made of the same lens: a chart of a thing against itself is a
// diagonal line, and a diagonal line tells a reader nothing they did not already have from the
// score column.
//
// So this plots the score against what it COSTS to hold:
//
//   x = composite (0–100)                what the methodology thinks of it
//   y = annualised volatility, INVERTED  what you live through to own it — calm at the top, so
//                                        "up and to the right" means better, as it does everywhere
//   size = traded value per day          whether you can actually buy it
//   colour = decile within peer group    the same ramp as every other decile on the board
//
// The two axes are independent by construction: the risk lens carries weight 0 in the ETF blend
// (it is an overlay the FM has not weighted), and the stock blend has no risk lens at all, so no
// part of `vol_ann` is inside `composite`. The top-right quadrant is therefore a real finding —
// strong AND calm — and not an artefact of plotting a number against itself.
//
// PLAIN SVG, NO CHART LIBRARY. Two thousand circles are nothing for the DOM, the design tokens
// apply directly, and the board does not take a dependency to draw forty lines.
//
// NOTHING IS INVENTED. A row missing either axis is not plotted and is COUNTED in the caption —
// an unmeasured fund must not appear at the origin, which would read as "worst score, no risk"
// (rule #0). The quadrant lines are the plotted cohort's own medians, so they move with the
// filters and always split the funds actually on screen.
//
// THE AXIS DOES NOT BELONG TO THE WORST ROW. On 2026-09-10 the y-axis ran 0 → 30,000 percent
// because one fund's stored volatility was about 300 (thirty thousand percent a year — a broken
// price series, not a volatile fund), and every other fund on the board sat on one line at the
// top. A scale set by its single most extreme value shows nothing about the other 1,654. So the
// domain is cut at a high percentile of the plotted cohort — ONLY when the tail is pathological,
// i.e. the maximum is far beyond that percentile — and the rows past it are PINNED at the edge
// with their own marker and counted in the caption. They are not dropped, not clamped in the
// data, and not drawn where they are not: a pinned disc says "off this scale", which is true.
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'
import { instrumentPath, type InstrumentRow } from '@/lib/facts'
import { formatPct, formatUsd } from '@/lib/format'
import { decileColour, peerGroupLabel, peerGroupOf } from '@/lib/scores'

type Point = {
  symbol: string
  name: string | null
  x: number
  y: number
  r: number
  decile: number | null
  peer: string
}

// The drawing surface in user units; the SVG scales to its container through the viewBox.
const W = 1000
const H = 460
const PAD = { top: 18, right: 18, bottom: 40, left: 54 }
const PLOT = { w: W - PAD.left - PAD.right, h: H - PAD.top - PAD.bottom }

/** Circle radius in user units. Area — not radius — is proportional to traded value, because the
 *  eye reads a disc by its area; a radius-linear scale exaggerates the largest fund by its square.
 *  Bounded at both ends so a $500k fund is still visible and a $20bn one does not eat the panel. */
const R_MIN = 3
const R_MAX = 17

function radius(value: number, maxValue: number): number {
  if (!(value > 0) || !(maxValue > 0)) return R_MIN
  const share = Math.sqrt(value / maxValue)
  return R_MIN + share * (R_MAX - R_MIN)
}

const num = (s: string | null | undefined): number | null => {
  if (s == null || s === '') return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const v = [...values].sort((a, b) => a - b)
  const mid = v.length >> 1
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2
}

/** Nice round tick values covering [0, max], at most `count` of them. */
function ticks(max: number, count: number): number[] {
  if (!(max > 0)) return [0]
  const raw = max / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10
  const out: number[] = []
  for (let t = 0; t <= max + step / 2; t += step) out.push(Number(t.toFixed(6)))
  return out
}

/** The p-th percentile of a list, linear interpolation between order statistics. */
function percentile(values: number[], p: number): number {
  const v = [...values].sort((a, b) => a - b)
  if (v.length === 0) return Number.NaN
  const pos = (v.length - 1) * p
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  return v[lo] + (v[hi] - v[lo]) * (pos - lo)
}

/** DISPLAY conventions, not methodology: no score, weight or universe cut reads either number.
 *  The cut sits at the 99th percentile so that on a board of ~1,700 funds at most a dozen or so
 *  can ever be pinned; and it engages only when the maximum is more than TAIL_RATIO times that
 *  percentile — a tail a reader would call broken, not merely long. A crypto fund at three times
 *  the median volatility is a long tail and stays on the scale. */
export const TAIL_PERCENTILE = 0.99
export const TAIL_RATIO = 1.5

/** The top of the y-axis for a set of volatilities, and which of them fall beyond it. */
export function yDomain(values: number[]): { max: number; cut: number | null } {
  if (values.length === 0) return { max: 0, cut: null }
  const max = Math.max(...values)
  if (values.length < 20) return { max, cut: null }
  const p = percentile(values, TAIL_PERCENTILE)
  return max > p * TAIL_RATIO && p > 0 ? { max: p, cut: p } : { max, cut: null }
}

export function StrengthRiskBubble({
  rows,
  assetClass,
  noun,
}: {
  rows: readonly InstrumentRow[]
  assetClass: 'etf' | 'stock'
  noun: string
}) {
  const router = useRouter()
  const [hover, setHover] = useState<Point | null>(null)

  const { points, missing, maxAdv } = useMemo(() => {
    const pts: Point[] = []
    let skipped = 0
    let adv = 0
    for (const r of rows) {
      const composite = num(r.composite)
      const v = num(r.vol_ann)
      if (composite == null || v == null) {
        skipped += 1
        continue
      }
      const a = num(r.adv_usd) ?? 0
      adv = Math.max(adv, a)
      pts.push({
        symbol: r.symbol,
        name: r.name,
        x: composite,
        y: v,
        r: a,
        decile: r.composite_decile,
        peer: peerGroupLabel(peerGroupOf(r)),
      })
    }
    return { points: pts, missing: skipped, maxAdv: adv }
  }, [rows])

  // A single fund would make its own median the only line on the chart, which says nothing.
  const midX = points.length > 3 ? median(points.map((p) => p.x)) : null
  const midY = points.length > 3 ? median(points.map((p) => p.y)) : null

  if (points.length === 0) {
    return (
      <p className="panel px-4 py-3 text-body text-ink-2">
        Nothing to plot: no {noun} in this view carry both a composite and a volatility.
        {missing > 0 && ` ${missing} row(s) are missing one or the other.`}
      </p>
    )
  }

  const domain = yDomain(points.map((p) => p.y))
  const yMax = domain.max * 1.05
  const pinned = domain.cut == null ? 0 : points.filter((p) => p.y > domain.cut!).length
  const sx = (v: number) => PAD.left + (v / 100) * PLOT.w
  // INVERTED: low volatility at the top, so up-and-right is unambiguously the good corner. A
  // reading past the cut sits ON the bottom edge — pinned, never plotted beyond the panel.
  const sy = (v: number) => PAD.top + (Math.min(v, yMax) / yMax) * PLOT.h

  const xTicks = [0, 20, 40, 60, 80, 100]
  const yTicks = ticks(yMax, 5)

  return (
    <div className="panel relative px-3 py-3">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: 'clamp(300px, 46vh, 460px)' }}
        role="img"
        aria-label={`${points.length} ${noun} plotted by composite score against annualised volatility`}
      >
        {/* grid */}
        {xTicks.map((t) => (
          <line key={`x${t}`} x1={sx(t)} y1={PAD.top} x2={sx(t)} y2={PAD.top + PLOT.h} stroke="var(--color-hair)" />
        ))}
        {yTicks.map((t) => (
          <line key={`y${t}`} x1={PAD.left} y1={sy(t)} x2={PAD.left + PLOT.w} y2={sy(t)} stroke="var(--color-hair)" />
        ))}

        {/* the cohort's own medians — they move with the filters */}
        {midX != null && (
          <line x1={sx(midX)} y1={PAD.top} x2={sx(midX)} y2={PAD.top + PLOT.h} stroke="var(--color-ink-2)" strokeDasharray="4 4" opacity="0.55" />
        )}
        {midY != null && (
          <line x1={PAD.left} y1={sy(midY)} x2={PAD.left + PLOT.w} y2={sy(midY)} stroke="var(--color-ink-2)" strokeDasharray="4 4" opacity="0.55" />
        )}
        {midX != null && midY != null && (
          <>
            <text x={PAD.left + PLOT.w - 6} y={PAD.top + 14} textAnchor="end" fontSize="12" fill="var(--color-pos)">
              stronger, calmer
            </text>
            <text x={PAD.left + 6} y={PAD.top + PLOT.h - 6} fontSize="12" fill="var(--color-neg)">
              weaker, more volatile
            </text>
          </>
        )}

        {/* the funds, largest first so a big disc can never bury a small one */}
        <g>
          {[...points]
            .sort((a, b) => b.r - a.r)
            .map((p) => {
              const colour = decileColour(p.decile) ?? 'var(--color-ink-2)'
              const off = domain.cut != null && p.y > domain.cut
              const dim = hover && hover.symbol !== p.symbol
              return (
                <circle
                  key={p.symbol}
                  cx={sx(p.x)}
                  cy={sy(p.y)}
                  r={radius(p.r, maxAdv)}
                  // Off the scale: a hollow, dashed disc on the edge — visibly a different kind
                  // of mark from a plotted fund, so nobody reads it as "very volatile, exactly here".
                  fill={off ? 'none' : colour}
                  fillOpacity={dim ? 0.18 : 0.62}
                  stroke={colour}
                  strokeOpacity={dim ? 0.35 : 0.9}
                  strokeDasharray={off ? '3 2' : undefined}
                  strokeWidth={off ? 1.5 : 1}
                  data-pinned={off ? '' : undefined}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHover(p)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => router.push(instrumentPath(assetClass, p.symbol))}
                >
                  <title>{`${p.symbol} — composite ${p.x.toFixed(1)}, volatility ${formatPct(String(p.y), 1)}${off ? ' (off the scale, pinned at the edge)' : ''}`}</title>
                </circle>
              )
            })}
        </g>

        {/* axes */}
        <line x1={PAD.left} y1={PAD.top + PLOT.h} x2={PAD.left + PLOT.w} y2={PAD.top + PLOT.h} stroke="var(--color-rule)" />
        <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={PAD.top + PLOT.h} stroke="var(--color-rule)" />
        {xTicks.map((t) => (
          <text key={`xt${t}`} x={sx(t)} y={PAD.top + PLOT.h + 16} textAnchor="middle" fontSize="12" fill="var(--color-ink-2)">
            {t}
          </text>
        ))}
        {yTicks.map((t) => (
          <text key={`yt${t}`} x={PAD.left - 8} y={sy(t) + 4} textAnchor="end" fontSize="12" fill="var(--color-ink-2)">
            {(t * 100).toFixed(0)}
          </text>
        ))}
        <text x={PAD.left + PLOT.w / 2} y={H - 6} textAnchor="middle" fontSize="12" fill="var(--color-ink-2)">
          <title>The blended score, 0–100: Σ(weight × lens) ÷ Σ weight over the lenses present.</title>
          Composite score →
        </text>
        <text x={14} y={PAD.top + PLOT.h / 2} textAnchor="middle" fontSize="12" fill="var(--color-ink-2)" transform={`rotate(-90 14 ${PAD.top + PLOT.h / 2})`}>
          <title>Annualised volatility: stdev of daily returns over 252 sessions × √252. Calm is at the top.</title>
          ← Volatility, percent a year
        </text>
      </svg>

      <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-meta text-ink-2">
        <span>
          {hover ? (
            <>
              <span className="font-medium text-ink">{hover.symbol}</span> {hover.name ?? ''} · composite{' '}
              <span className="num">{hover.x.toFixed(1)}</span> · volatility{' '}
              <span className="num">{formatPct(String(hover.y), 1)}</span> · traded{' '}
              <span className="num">{formatUsd(String(hover.r), 0)}</span> a day · {hover.peer}
            </>
          ) : (
            <>Right is a stronger score, up is a calmer fund. Disc size is traded value a day; colour is the decile in the peer group. Hover for the numbers, click to open.</>
          )}
        </span>
        <span className="num">
          {points.length.toLocaleString()} plotted
          {pinned > 0 && domain.cut != null && (
            <span title={`The scale stops at ${formatPct(String(domain.cut), 0)} a year; ${pinned} reading(s) beyond it are drawn on the edge as hollow discs rather than stretching the axis to one fund.`}>
              {` · ${pinned.toLocaleString()} off the scale (above ${formatPct(String(domain.cut), 0)}), pinned at the edge`}
            </span>
          )}
          {missing > 0 && ` · ${missing.toLocaleString()} not scored or not priced`}
        </span>
      </div>
    </div>
  )
}
