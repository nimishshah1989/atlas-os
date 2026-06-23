'use client'

// SectorStock2x2 — two 2x2 maps of the sector's stocks, deciles cut within cap cohort (D27):
//   A) Momentum (Technical decile) × Quality (Fundamental decile)
//   B) Strength (avg conviction decile) × Leadership (# of 4 lenses top-decile)
// Dot colour = leadership badge. Custom Recharts scatter (TV can't draw XY scatter).
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import type { SectorStock } from '@/lib/queries/v6/sector_lens'

const leadColor = (lead: number) =>
  lead >= 3 ? '#2F6B43' : lead === 2 ? '#1D9E75' : lead === 1 ? '#C68B2E' : '#9A8F82'

type Pt = { x: number; y: number; symbol: string; lead: number }

function Quad({ data, xLabel, yLabel, xDomain, yDomain, xMid, yMid }: {
  data: Pt[]; xLabel: string; yLabel: string
  xDomain: [number, number]; yDomain: [number, number]; xMid: number; yMid: number
}) {
  return (
    <div className="bg-paper border border-paper-rule rounded-sm p-3">
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 12, right: 16, bottom: 28, left: 8 }}>
          <CartesianGrid stroke="#F1ECDF" />
          <XAxis type="number" dataKey="x" domain={xDomain} tick={{ fontSize: 10, fill: '#8A8578' }}
            label={{ value: xLabel, position: 'bottom', fontSize: 11, fill: '#6B6157' }} />
          <YAxis type="number" dataKey="y" domain={yDomain} tick={{ fontSize: 10, fill: '#8A8578' }}
            label={{ value: yLabel, angle: -90, position: 'insideLeft', fontSize: 11, fill: '#6B6157' }} />
          <ZAxis range={[40, 40]} />
          <ReferenceLine x={xMid} stroke="#C9C5BA" strokeDasharray="3 3" />
          <ReferenceLine y={yMid} stroke="#C9C5BA" strokeDasharray="3 3" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as Pt
              return (
                <div className="bg-ink-primary text-paper px-2 py-1 rounded-sm font-mono text-[11px]">
                  {p.symbol} · {xLabel.split(' ')[0]} {p.x} / {yLabel.split(' ')[0]} {p.y} · {p.lead}/4
                </div>
              )
            }} />
          <Scatter data={data}>
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
    .map(s => ({ x: s.d_tech as number, y: s.d_fund as number, symbol: s.symbol, lead: s.lead }))
  const strLead: Pt[] = stocks
    .filter(s => s.strength != null)
    .map(s => ({ x: Math.round((s.strength as number) * 10) / 10, y: s.lead, symbol: s.symbol, lead: s.lead }))

  return (
    <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector stocks 2x2">
      <div className="mb-5">
        <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">The sector's stocks · 2×2</h2>
        <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
          Each dot is a constituent. Deciles are cut within its cap cohort. Dot colour = how many of the 4
          conviction lenses it leads (grey 0 · amber 1 · teal 2 · green 3–4).
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div>
          <div className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-2">Momentum × Quality</div>
          <Quad data={momQual} xLabel="Technical decile" yLabel="Fundamental decile"
            xDomain={[0.5, 10.5]} yDomain={[0.5, 10.5]} xMid={5.5} yMid={5.5} />
        </div>
        <div>
          <div className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-2">Strength × Leadership</div>
          <Quad data={strLead} xLabel="Strength (avg decile)" yLabel="Leadership (# lenses)"
            xDomain={[0.5, 10.5]} yDomain={[-0.3, 4.3]} xMid={5.5} yMid={2} />
        </div>
      </div>
    </section>
  )
}
