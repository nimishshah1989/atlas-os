'use client'

// StocksBubble2x2 — the ONE strong 2×2 for the /stocks screener:
//   x = Strength (avg conviction decile) · y = Leadership (# of 4 lenses top-decile)
//   bubble SIZE = ~20-session liquidity (₹ Cr) · bubble COLOUR = leadership badge.
// Click a dot → /stocks/<symbol>. Custom Recharts scatter (TV can't draw XY scatter).
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import { useRouter } from 'next/navigation'
import type { StockListRow } from '@/lib/queries/v6/stock_lens'

const leadColor = (lead: number) =>
  lead >= 3 ? '#2F6B43' : lead === 2 ? '#1D9E75' : lead === 1 ? '#C68B2E' : '#9A8F82'

type Pt = { x: number; y: number; z: number; symbol: string; lead: number; liq: number }

export function StocksBubble2x2({ stocks }: { stocks: StockListRow[] }) {
  const router = useRouter()

  const scored = stocks.filter(s => s.strength != null)
  // null liquidity → the dataset's smallest known value, so the bubble still renders
  // at the floor of the size scale rather than collapsing to nothing.
  const liqVals = scored.map(s => s.liq_cr).filter((v): v is number => v != null)
  const liqFloor = liqVals.length ? Math.min(...liqVals) : 1

  const data: Pt[] = scored.map(s => {
    const liq = s.liq_cr ?? liqFloor
    return {
      x: Math.round((s.strength as number) * 10) / 10,
      y: s.lead,
      z: liq,
      symbol: s.symbol,
      lead: s.lead,
      liq,
    }
  })

  return (
    <div className="bg-paper border border-paper-rule rounded-sm p-3 cursor-pointer">
      <ResponsiveContainer width="100%" height={360}>
        <ScatterChart margin={{ top: 12, right: 16, bottom: 28, left: 8 }}>
          <CartesianGrid stroke="#F1ECDF" />
          <XAxis type="number" dataKey="x" domain={[0.5, 10.5]} tick={{ fontSize: 10, fill: '#8A8578' }}
            label={{ value: 'Strength (avg decile)', position: 'bottom', fontSize: 11, fill: '#6B6157' }} />
          <YAxis type="number" dataKey="y" domain={[-0.3, 4.3]} tick={{ fontSize: 10, fill: '#8A8578' }}
            label={{ value: 'Leadership (# lenses)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#6B6157' }} />
          <ZAxis type="number" dataKey="z" range={[30, 400]} />
          <ReferenceLine x={5.5} stroke="#C9C5BA" strokeDasharray="3 3" />
          <ReferenceLine y={2} stroke="#C9C5BA" strokeDasharray="3 3" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as Pt
              return (
                <div className="bg-ink-primary text-paper px-2 py-1 rounded-sm font-mono text-[11px]">
                  {p.symbol} · Strength {p.x.toFixed(1)} / Lead {p.lead}/4 · ₹{Math.round(p.liq)}cr
                </div>
              )
            }} />
          <Scatter
            data={data}
            isAnimationActive={false}  /* ~2k points — skip the per-node mount animation */
            style={{ cursor: 'pointer' }}
            onClick={(node) => {
              // Recharts passes a ScatterPointItem; the row we supplied lives on `.payload`.
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
