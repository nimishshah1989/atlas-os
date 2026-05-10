import type { StockRowWithSector } from '@/lib/queries/stocks'

type Props = {
  stocks: StockRowWithSector[]
}

function Tile({ label, value, sub, tone = 'neutral' }: {
  label: string
  value: string
  sub?: string
  tone?: 'pos' | 'neg' | 'warn' | 'neutral'
}) {
  const valueColor = tone === 'pos' ? 'text-signal-pos' : tone === 'neg' ? 'text-signal-neg' : tone === 'warn' ? 'text-signal-warn' : 'text-ink-primary'
  return (
    <div className="flex flex-col gap-1 px-4 py-3 border-r border-paper-rule last:border-0">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap">{label}</div>
      <div className={`font-mono text-sm font-semibold tabular-nums ${valueColor}`}>{value}</div>
      {sub && <div className="font-sans text-[10px] text-ink-tertiary">{sub}</div>}
    </div>
  )
}

export function StockMetricTiles({ stocks }: Props) {
  const n = stocks.length
  if (n === 0) return null

  const leaderStrong = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const investable   = stocks.filter(s => s.is_investable).length
  const accelImpr    = stocks.filter(s => s.momentum_state === 'Accelerating' || s.momentum_state === 'Improving').length
  const volAccum     = stocks.filter(s => s.volume_state === 'Accumulation' || s.volume_state === 'Steady-Buying').length

  const pctiles = stocks.map(s => s.rs_pctile_3m ? parseFloat(s.rs_pctile_3m) : null).filter(v => v != null) as number[]
  pctiles.sort((a, b) => a - b)
  const medianPctile = pctiles.length > 0 ? pctiles[Math.floor(pctiles.length / 2)] : null

  const ret3ms = stocks.map(s => s.ret_3m ? parseFloat(s.ret_3m) : null).filter(v => v != null) as number[]
  const avgRet3m = ret3ms.length > 0 ? ret3ms.reduce((a, b) => a + b, 0) / ret3ms.length : null

  const pctLeaderStrong = leaderStrong / n
  const leaderTone = pctLeaderStrong >= 0.3 ? 'pos' : pctLeaderStrong >= 0.15 ? 'warn' : 'neg'
  const accelTone  = accelImpr / n >= 0.25 ? 'pos' : 'neutral'
  const retTone    = avgRet3m != null ? (avgRet3m >= 0.05 ? 'pos' : avgRet3m >= 0 ? 'neutral' : 'neg') : 'neutral'

  return (
    <div className="flex overflow-x-auto border border-paper-rule rounded-sm bg-paper divide-x divide-paper-rule">
      <Tile label="Leaders" value={`${leaderStrong}`} sub={`${(pctLeaderStrong * 100).toFixed(0)}% of universe`} tone={leaderTone} />
      <Tile label="Investable" value={`${investable}`} sub={`${(investable / n * 100).toFixed(0)}% of universe`} tone={investable > 0 ? 'pos' : 'neutral'} />
      <Tile label="Median RS" value={medianPctile != null ? `${(medianPctile * 100).toFixed(0)}th` : '—'} />
      <Tile label="Accel/Impr" value={`${accelImpr}`} sub={`${(accelImpr / n * 100).toFixed(0)}% gaining momentum`} tone={accelTone} />
      <Tile label="Vol Accum" value={`${volAccum}`} sub={`${(volAccum / n * 100).toFixed(0)}% buying pressure`} tone={volAccum / n >= 0.2 ? 'pos' : 'neutral'} />
      <Tile
        label="Avg 3M Ret"
        value={avgRet3m != null ? `${avgRet3m >= 0 ? '+' : ''}${(avgRet3m * 100).toFixed(1)}%` : '—'}
        tone={retTone}
      />
    </div>
  )
}
