'use client'
// src/components/portfolios/BasketChart.tsx — the NAV rebased to 100 beside SPY's close_tr
// rebased to 100 on the basket's first NAV date. Display arithmetic over the stored series.
import { useMemo } from 'react'
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import type { BasketDetail } from '@/lib/queries/baskets'

export function BasketChart({ d }: { d: BasketDetail }) {
  const series = useMemo<ChartSeries[]>(() => {
    const base = d.nav[0]?.nav
    const out: ChartSeries[] = []
    if (base && base > 0)
      out.push({ name: d.summary.name, color: 'accent', data: d.nav.map((p) => ({ time: p.d, value: (p.nav / base) * 100 })) })
    const spy0 = d.bench[0]?.close_tr
    if (spy0 && spy0 > 0)
      out.push({ name: 'SPY', color: 'ink', lineWidth: 1, data: d.bench.map((p) => ({ time: p.d, value: (p.close_tr / spy0) * 100 })) })
    return out
  }, [d])
  return <AtlasLightweightChart series={series} height={300} precision={2} />
}
