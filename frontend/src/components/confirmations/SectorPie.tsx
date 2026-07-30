'use client'
// Sector allocation of the resulting book. Fixed width/height on purpose:
// ResponsiveContainer measures the viewport, which collapses when printing.
import { Cell, Legend, Pie, PieChart, Tooltip } from 'recharts'

import type { BookPosition } from '@/lib/confirmations'

// Muted, print-safe. Saturated wheels are a retail-app tell.
const PALETTE = [
  '#25394A', '#B8860B', '#2C6B41', '#AB4425', '#5C6B7A',
  '#8A6D3B', '#41626F', '#7A5C52', '#4A5D3F', '#6B5B7A',
]

export function SectorPie({ book, cash }: { book: BookPosition[]; cash: number }) {
  const bySector = new Map<string, number>()
  for (const p of book) {
    const s = p.sector ?? 'Unmapped'
    bySector.set(s, (bySector.get(s) ?? 0) + p.weightPct)
  }
  const data = [...bySector.entries()]
    .map(([name, value]) => ({ name, value: Number(value.toFixed(1)) }))
    .sort((a, b) => b.value - a.value)
  if (cash > 0) data.push({ name: 'Cash', value: Number(cash.toFixed(1)) })

  if (data.length === 0) return null

  return (
    <PieChart width={420} height={280}>
      <Pie data={data} dataKey="value" nameKey="name" cx={130} cy={130} outerRadius={100} isAnimationActive={false}>
        {data.map((d, i) => (
          <Cell key={d.name} fill={d.name === 'Cash' ? '#9AA5AF' : PALETTE[i % PALETTE.length]} />
        ))}
      </Pie>
      <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
      <Legend layout="vertical" align="right" verticalAlign="middle" iconSize={9} />
    </PieChart>
  )
}
