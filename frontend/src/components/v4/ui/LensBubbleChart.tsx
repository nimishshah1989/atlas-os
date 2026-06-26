// LensBubbleChart — v4 theme-aware SVG bubble/scatter for the ETF + Fund landscapes
// (FM 2026-06-26: make the ETF/Fund pages dynamic, not just tables). Pure server
// component: every bubble is a real <a> link with a native <title> tooltip, so it works
// with zero client JS and survives hydration. Colours use the locked v4 signal tokens
// (var(--color-sig-*)) so it's correct in both Daylight + Graphite themes.

export type BubblePoint = {
  id: string
  label: string
  x: number          // domain value (e.g. breadth %, return %)
  y: number          // domain value (e.g. lens / composite score)
  size: number       // bubble area driver (e.g. AUM, holdings) — ≥0
  tone: 'pos' | 'neg' | 'neutral'
  href: string
  sub?: string       // extra tooltip line
}

const TONE_VAR: Record<BubblePoint['tone'], string> = {
  pos: 'var(--color-sig-pos)',
  neg: 'var(--color-sig-neg)',
  neutral: 'var(--color-txt-3)',
}

const W = 820
const H = 440
const PADL = 60
const PADR = 28
const PADT = 30
const PADB = 54

function niceDomain(vals: number[]): [number, number] {
  if (vals.length === 0) return [0, 1]
  let lo = Math.min(...vals)
  let hi = Math.max(...vals)
  if (lo === hi) { lo -= 1; hi += 1 }
  const pad = (hi - lo) * 0.08
  return [lo - pad, hi + pad]
}
function median(vals: number[]): number {
  if (vals.length === 0) return 0
  const s = [...vals].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

export function LensBubbleChart({
  points, xLabel, yLabel, sizeLabel,
  xFmt = (v: number) => v.toFixed(0),
  yFmt = (v: number) => v.toFixed(0),
}: {
  points: BubblePoint[]
  xLabel: string
  yLabel: string
  sizeLabel: string
  xFmt?: (v: number) => string
  yFmt?: (v: number) => string
}) {
  if (points.length === 0) {
    return <div className="flex h-64 items-center justify-center rounded-tile border border-edge-hair bg-surface-panel font-sans text-[13px] text-txt-3">No data available.</div>
  }
  const plotW = W - PADL - PADR
  const plotH = H - PADT - PADB
  const [x0, x1] = niceDomain(points.map((p) => p.x))
  const [y0, y1] = niceDomain(points.map((p) => p.y))
  const sMax = Math.max(...points.map((p) => Math.max(0, p.size)), 1)
  const sx = (v: number) => PADL + ((v - x0) / (x1 - x0)) * plotW
  const sy = (v: number) => PADT + plotH - ((v - y0) / (y1 - y0)) * plotH
  // area-proportional radius (sqrt), clamped to a legible 6–26px
  const rr = (s: number) => 6 + Math.sqrt(Math.max(0, s) / sMax) * 20
  const xMed = sx(median(points.map((p) => p.x)))
  const yMed = sy(median(points.map((p) => p.y)))
  const xTicks = [x0, (x0 + x1) / 2, x1]
  const yTicks = [y0, (y0 + y1) / 2, y1]
  // largest bubbles drawn first so small ones stay clickable on top
  const ordered = [...points].sort((a, b) => b.size - a.size)

  return (
    <div className="rounded-tile border border-edge-hair bg-surface-panel">
      <div className="flex flex-wrap items-center gap-3 border-b border-edge-hair px-4 py-2">
        <span className="font-num text-[10px] uppercase tracking-wider text-txt-3">Bubble size = {sizeLabel}</span>
        <span className="ml-auto font-num text-[10px] tabular-nums text-txt-3">{points.length} instruments · hover for detail, click to open</span>
      </div>
      <div className="px-2 py-2">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${yLabel} vs ${xLabel} bubble chart`} className="font-num">
          {/* gridlines + ticks */}
          {xTicks.map((t, i) => (
            <g key={`x${i}`}>
              <line x1={sx(t)} y1={PADT} x2={sx(t)} y2={PADT + plotH} stroke="var(--color-edge-hair)" strokeWidth={1} />
              <text x={sx(t)} y={PADT + plotH + 18} textAnchor="middle" fontSize={10} fill="var(--color-txt-3)">{xFmt(t)}</text>
            </g>
          ))}
          {yTicks.map((t, i) => (
            <g key={`y${i}`}>
              <line x1={PADL} y1={sy(t)} x2={PADL + plotW} y2={sy(t)} stroke="var(--color-edge-hair)" strokeWidth={1} />
              <text x={PADL - 8} y={sy(t) + 3} textAnchor="end" fontSize={10} fill="var(--color-txt-3)">{yFmt(t)}</text>
            </g>
          ))}
          {/* median crosshairs */}
          <line x1={xMed} y1={PADT} x2={xMed} y2={PADT + plotH} stroke="var(--color-edge-rule)" strokeDasharray="4 3" strokeWidth={1} />
          <line x1={PADL} y1={yMed} x2={PADL + plotW} y2={yMed} stroke="var(--color-edge-rule)" strokeDasharray="4 3" strokeWidth={1} />
          {/* axis labels */}
          <text x={PADL + plotW / 2} y={H - 8} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--color-txt-2)">{xLabel}</text>
          <text x={16} y={PADT + plotH / 2} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--color-txt-2)" transform={`rotate(-90 16 ${PADT + plotH / 2})`}>{yLabel}</text>
          {/* bubbles — plain SVG <a> (full nav, works without hydration; targets are pre-warmed) */}
          {ordered.map((p) => (
            <a key={p.id} href={p.href} aria-label={p.label}>
              <circle
                cx={sx(p.x)} cy={sy(p.y)} r={rr(p.size)}
                fill={TONE_VAR[p.tone]} fillOpacity={0.62}
                stroke={TONE_VAR[p.tone]} strokeWidth={1}
                style={{ cursor: 'pointer' }}
              >
                <title>{`${p.label}\n${xLabel}: ${xFmt(p.x)} · ${yLabel}: ${yFmt(p.y)}${p.sub ? `\n${p.sub}` : ''}`}</title>
              </circle>
            </a>
          ))}
        </svg>
      </div>
    </div>
  )
}
