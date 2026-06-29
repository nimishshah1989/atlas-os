'use client'

// SectorStock2x2 — two 2x2 maps of the sector's stocks, deciles cut within cap cohort (D27):
//   A) Momentum (Technical decile) × Quality (Fundamental decile)
//   B) Strength (avg conviction decile) × Leadership (# of 4 lenses top-decile)
// Bubble SIZE = cap tier (large→largest … micro→smallest), a market-cap proxy.
// Dot COLOUR = leadership badge. Click a dot → /stocks/<symbol>. Theme-aware: colours
// come from useThemeTokens so the chart recolours live with the day/night toggle.
// Custom Recharts scatter (TV can't draw XY scatter).
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import { useRouter } from 'next/navigation'
import type { SectorStock } from '@/lib/queries/v6/sector_lens'
import { useThemeTokens } from '@/components/v4/ui/useThemeTokens'

// Cap tier → z value (a market-cap proxy). ZAxis range maps these to bubble area.
const CAP_Z: Record<string, number> = { large: 4, mid: 3, small: 2, micro: 1 }
const capZ = (cap: string) => CAP_Z[cap] ?? 1

type Pt = { x: number; y: number; z: number; symbol: string; lead: number; cap: string }

function Quad({ data, xLabel, yLabel, xDomain, yDomain, xMid, yMid }: {
  data: Pt[]; xLabel: string; yLabel: string
  xDomain: [number, number]; yDomain: [number, number]; xMid: number; yMid: number
}) {
  const router = useRouter()
  const t = useThemeTokens()
  const leadColor = (lead: number) =>
    !t ? '#888888' : lead >= 2 ? t.pos : lead === 1 ? t.warn : t.tick

  const grid = t?.grid ?? '#88888822'
  const tick = t?.tick ?? '#888888'
  const label = t?.label ?? '#888888'
  const ref = t?.rule ?? '#88888844'

  return (
    <div className="rounded-tile border border-edge-hair bg-surface-inset/50 p-3">
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 12, right: 16, bottom: 28, left: 8 }}>
          <CartesianGrid stroke={grid} />
          <XAxis type="number" dataKey="x" domain={xDomain} tick={{ fontSize: 10, fill: tick }}
            label={{ value: xLabel, position: 'bottom', fontSize: 11, fill: label }} />
          <YAxis type="number" dataKey="y" domain={yDomain} tick={{ fontSize: 10, fill: tick }}
            label={{ value: yLabel, angle: -90, position: 'insideLeft', fontSize: 11, fill: label }} />
          <ZAxis type="number" dataKey="z" domain={[1, 4]} range={[120, 600]} />
          <ReferenceLine x={xMid} stroke={ref} strokeDasharray="3 3" />
          <ReferenceLine y={yMid} stroke={ref} strokeDasharray="3 3" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as Pt
              return (
                <div className="rounded-tile border border-edge-rule bg-surface-raised px-2.5 py-1.5 font-num text-[11px] tabular-nums text-txt-1 shadow-panel">
                  {p.symbol} · {xLabel.split(' ')[0]} {p.x} / {yLabel.split(' ')[0]} {p.y} · {p.lead}/2 · {p.cap}
                </div>
              )
            }} />
          <Scatter
            data={data}
            isAnimationActive={false}
            style={{ cursor: 'pointer' }}
            onClick={(node) => {
              const p = (node as { payload?: Pt }).payload
              if (p?.symbol) router.push('/stocks/' + p.symbol)
            }}
          >
            {data.map((p, i) => <Cell key={i} fill={leadColor(p.lead)} fillOpacity={0.85} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

export function SectorStock2x2({ stocks }: { stocks: SectorStock[] }) {
  const momQual: Pt[] = stocks
    .filter(s => s.d_tech != null && s.d_fund != null)
    .map(s => ({ x: s.d_tech as number, y: s.d_fund as number, z: capZ(s.cap), symbol: s.symbol, lead: s.lead, cap: s.cap }))
  const strLead: Pt[] = stocks
    .filter(s => s.strength != null)
    .map(s => ({ x: Math.round((s.strength as number) * 10) / 10, y: s.lead, z: capZ(s.cap), symbol: s.symbol, lead: s.lead, cap: s.cap }))

  return (
    <section className="px-8 py-10 border-b border-edge-hair" aria-label="Sector stocks 2x2">
      <div className="mb-5">
        <h2 className="font-display text-[28px] font-normal tracking-tight text-txt-1">
          The sector&apos;s stocks · 2×2 <span className="font-num text-[15px] text-txt-3">· {stocks.length} constituent{stocks.length === 1 ? '' : 's'}</span>
        </h2>
        <p className="font-sans text-[13px] text-txt-3 max-w-[760px] leading-[1.45] mt-1">
          Each dot is a constituent; deciles are cut within its cap cohort. Bubble size = cap tier
          (large → micro). Colour = how many of the 2 active lenses (Technical &amp; Flow) it leads at
          D9/D10 (grey 0 · amber 1 · green 2). Click a dot → that stock. A small sector simply has few
          dots (e.g. a 4-name sector shows 4).
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div>
          <div className="font-num text-[11px] text-txt-3 uppercase tracking-wider mb-2">Momentum × Quality <span className="text-txt-2">· {momQual.length} plotted</span></div>
          <Quad data={momQual} xLabel="Technical decile" yLabel="Fundamental decile"
            xDomain={[0.5, 10.5]} yDomain={[0.5, 10.5]} xMid={5.5} yMid={5.5} />
        </div>
        <div>
          <div className="font-num text-[11px] text-txt-3 uppercase tracking-wider mb-2">Strength × Leadership <span className="text-txt-2">· {strLead.length} plotted</span></div>
          <Quad data={strLead} xLabel="Strength (avg decile)" yLabel="Leadership (# of 2)"
            xDomain={[0.5, 10.5]} yDomain={[-0.3, 2.3]} xMid={5.5} yMid={1.5} />
        </div>
      </div>
    </section>
  )
}
