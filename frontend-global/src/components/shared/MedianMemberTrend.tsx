'use client'
// MedianMemberTrend — how a sector OR A THEME has actually been doing, against the index, over
// three years. It lives here rather than under sectors/ because the FM's sub-thematic calls are
// made at the theme level and the line is the same line.
//
// The FM: "we can have much better representations of sectors at the theme level: different
// visuals… line charts, historic data, and how these sectors have been doing."
//
// WHAT THE LINE IS, EXACTLY. Each member fund is rebased to its OWN close on the window's first
// session; the sector is the MEDIAN of those growth factors, rebased to 100. Median, not mean and
// not AUM-weighted — one $30bn fund is not a sector or a theme — which is the same rule every roll-up on this
// board follows. SPY on the same two axes is the baseline, so "up 40" and "up 40 while the index
// made 55" are visibly different pictures.
//
// AND WHAT IT IS NOT. Membership is fixed at the window's start, so this is a survivorship claim
// and the caption says so: a fund listed since is not in the line, and one that closed is not
// either. A chained index over changing membership is a producer's job, not a page's, and
// inventing one here would be a number nobody computed (rule #0).
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import type { SectorPoint } from '@/lib/sectors'

export function MedianMemberTrend({ name, points }: { name: string; points: readonly SectorPoint[] }) {
  if (points.length < 2) return null
  const series: ChartSeries[] = [
    { name, data: points.map((p) => ({ time: p.date, value: p.index })), color: 'accent', lineWidth: 2 },
  ]
  const spy = points.filter((p) => p.spy != null)
  if (spy.length > 1) {
    series.push({
      name: 'S&P 500',
      data: spy.map((p) => ({ time: p.date, value: p.spy as number })),
      color: 'ink',
      lineWidth: 1,
    })
  }
  return <AtlasLightweightChart series={series} height={260} precision={1} />
}
