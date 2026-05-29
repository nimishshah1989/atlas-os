// frontend/src/components/regime/SignalScorecard.tsx
// 4-tile bottom-up signal scorecard (Trend / Breadth / Momentum / Participation).
//
// 2026-05-29 rebuild per user feedback:
//  - Momentum tile no longer renders the meaningless "-1 net stage-2 flow 5d".
//    Primary signal is now the McClellan Oscillator (industry-standard breadth-
//    momentum gauge) with net 52w highs vs lows as the visceral sub-metric.
//  - Every tile now has 2-3 sub-metrics + a one-line "what this means"
//    commentary so the cards aren't bare. Bullish/bearish chip on each tile.
//  - Component now takes the regime row directly to compute rich content;
//    the legacy ScorecardData prop is kept for the trend/participation primary
//    values it already computes.
'use client'

import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { metric } from '@/lib/metric-registry'
import type { MarketRegimeRow } from '@/lib/queries/regime'

export type ScorecardTile = {
  label: string
  value: string | null
  rawValue: number | null
  source: string
}

export type ScorecardData = {
  trend: ScorecardTile
  breadth: ScorecardTile
  momentum: ScorecardTile
  participation: ScorecardTile
}

const TILE_METRIC_KEYS: Record<keyof ScorecardData, string> = {
  trend:         'scorecard_trend_pct',
  breadth:       'scorecard_breadth_pct',
  momentum:      'scorecard_momentum_net',
  participation: 'scorecard_participation',
}

type Signal = 'pos' | 'neg' | 'neutral'

const SIGNAL_COLOR: Record<Signal, string> = {
  pos:     'text-signal-pos',
  neg:     'text-signal-neg',
  neutral: 'text-signal-warn',
}

const SIGNAL_BG: Record<Signal, string> = {
  pos:     'bg-signal-pos/5 border-signal-pos/20',
  neg:     'bg-signal-neg/5 border-signal-neg/20',
  neutral: 'bg-signal-warn/5 border-signal-warn/20',
}

const CHIP_BG: Record<Signal, string> = {
  pos:     'bg-signal-pos/15 text-signal-pos border-signal-pos/30',
  neg:     'bg-signal-neg/15 text-signal-neg border-signal-neg/30',
  neutral: 'bg-signal-warn/15 text-signal-warn border-signal-warn/30',
}

// ─── value helpers ──────────────────────────────────────────────────────

const f = (s: string | null | undefined): number => (s == null ? NaN : parseFloat(s))
const pctStr = (v: number, d = 0) => `${(v * 100).toFixed(d)}%`
const numStr = (v: number, d = 1) => v.toFixed(d)

// ─── per-tile computation ───────────────────────────────────────────────
// Each returns: primary value + sub-metrics + signal + chip label + 1-line copy.

type TileContent = {
  primary: string
  primarySub: string | null
  subs: { label: string; value: string }[]
  signal: Signal
  chip: string
  commentary: string
}

function buildTrendTile(data: ScorecardData['trend'], r: MarketRegimeRow): TileContent {
  const rv = data.rawValue
  const signal: Signal = rv == null ? 'neutral' : rv >= 0.5 ? 'pos' : rv >= 0.35 ? 'neutral' : 'neg'
  const slope50 = f(r.nifty500_ema_50_slope)
  const slope200 = f(r.nifty500_ema_200_slope)
  const above50 = r.nifty500_above_ema_50
  const above200 = r.nifty500_above_ema_200

  let chip = 'mixed'
  if (above50 && above200 && slope50 > 0 && slope200 > 0) chip = 'trend up'
  else if (!above50 && !above200 && slope50 < 0) chip = 'trend down'
  else if (above50 && !above200) chip = 'turning up'
  else if (!above50 && above200) chip = 'turning down'

  const subs: { label: string; value: string }[] = []
  if (Number.isFinite(slope50))
    subs.push({ label: '50D slope', value: `${slope50 >= 0 ? '+' : ''}${pctStr(slope50, 2)}/d` })
  if (above50 != null)
    subs.push({ label: 'Px vs 50D', value: above50 ? 'above' : 'below' })
  if (above200 != null)
    subs.push({ label: 'Px vs 200D', value: above200 ? 'above' : 'below' })

  const commentary = signal === 'pos'
    ? 'Primary trend up; breadth confirms.'
    : signal === 'neg'
      ? 'Trend deteriorating across both 50D and 200D references.'
      : 'Trend in flux — wait for a clean cross before adding.'

  return {
    primary: data.value ?? 'n/a',
    primarySub: '% stocks in stage 2',
    subs,
    signal,
    chip,
    commentary,
  }
}

function buildBreadthTile(data: ScorecardData['breadth'], r: MarketRegimeRow): TileContent {
  const above50 = f(r.pct_above_ema_50)
  const above200 = f(r.pct_above_ema_200)
  const adRatio = f(r.ad_ratio)
  const adLine = f(r.ad_line)
  const adSlope = f(r.ad_line_slope_21)

  const signal: Signal = !Number.isFinite(above50)
    ? 'neutral'
    : above50 >= 0.6 ? 'pos' : above50 >= 0.45 ? 'neutral' : 'neg'

  let chip = 'mixed'
  if (above50 >= 0.6 && adRatio > 1) chip = 'expanding'
  else if (above50 < 0.4 && adRatio < 1) chip = 'narrowing'
  else if (above50 >= 0.5) chip = 'broad'
  else chip = 'narrow'

  const subs: { label: string; value: string }[] = []
  if (Number.isFinite(above200))
    subs.push({ label: '% > 200D EMA', value: pctStr(above200) })
  if (Number.isFinite(adRatio))
    subs.push({ label: 'A/D ratio', value: numStr(adRatio, 2) })
  if (Number.isFinite(adSlope))
    subs.push({ label: 'A/D 21d slope', value: `${adSlope >= 0 ? '+' : ''}${pctStr(adSlope, 1)}` })

  const commentary = signal === 'pos'
    ? `Majority above 50D EMA and advances outweigh declines (${adRatio.toFixed(2)}×).`
    : signal === 'neg'
      ? 'Breadth narrowing — fewer stocks holding up the index.'
      : 'Mixed — leadership concentrated in a few names.'

  return {
    primary: data.value ?? 'n/a',
    primarySub: '% stocks > 50D EMA',
    subs,
    signal,
    chip,
    commentary,
  }
}

function buildMomentumTile(_data: ScorecardData['momentum'], r: MarketRegimeRow): TileContent {
  // 2026-05-29 user feedback: dropped "net stage-2 flow 5d" (delta of 1-2
  // doesn't communicate anything). Replaced with McClellan Oscillator (the
  // industry-standard breadth-momentum gauge) + net new highs.
  const mc = f(r.mcclellan_oscillator)
  const mcSum = f(r.mcclellan_summation)
  const newHighs = r.new_52w_highs ?? null
  const newLows = r.new_52w_lows ?? null
  const netHL = newHighs != null && newLows != null ? newHighs - newLows : null
  const adRatio = f(r.ad_ratio)

  const signal: Signal = !Number.isFinite(mc)
    ? 'neutral'
    : mc > 5 ? 'pos' : mc > -5 ? 'neutral' : 'neg'

  let chip = 'mixed'
  if (mc > 20) chip = 'thrust up'
  else if (mc > 0) chip = 'rising'
  else if (mc > -20) chip = 'fading'
  else chip = 'washout'

  const subs: { label: string; value: string }[] = []
  if (netHL != null)
    subs.push({ label: 'Net 52w H/L', value: `${netHL >= 0 ? '+' : ''}${netHL} (${newHighs}/${newLows})` })
  if (Number.isFinite(mcSum))
    subs.push({ label: 'McClellan Sum', value: numStr(mcSum, 0) })
  if (Number.isFinite(adRatio))
    subs.push({ label: 'A/D ratio', value: numStr(adRatio, 2) })

  const commentary = signal === 'pos'
    ? `McClellan rising — breadth momentum confirming with ${newHighs ?? '?'} new highs.`
    : signal === 'neg'
      ? 'McClellan deep negative — breadth thrust is broken.'
      : 'Momentum stalled — breadth flat, waiting for direction.'

  return {
    primary: Number.isFinite(mc) ? numStr(mc, 1) : 'n/a',
    primarySub: 'McClellan Oscillator',
    subs,
    signal,
    chip,
    commentary,
  }
}

function buildParticipationTile(data: ScorecardData['participation'], r: MarketRegimeRow): TileContent {
  const rv = data.rawValue
  const pctStrong = f(r.pct_in_strong_states)
  const pctWein = f(r.pct_weinstein_pass)

  const signal: Signal = rv == null
    ? 'neutral'
    : rv >= 0.6 ? 'pos' : rv >= 0.4 ? 'neutral' : 'neg'

  let chip = 'mixed'
  if (rv != null && rv >= 0.7) chip = 'broad'
  else if (rv != null && rv >= 0.5) chip = 'firming'
  else if (rv != null && rv >= 0.3) chip = 'narrow'
  else chip = 'thin'

  const subs: { label: string; value: string }[] = []
  if (Number.isFinite(pctStrong))
    subs.push({ label: '% in strong states', value: pctStr(pctStrong) })
  if (Number.isFinite(pctWein))
    subs.push({ label: '% Weinstein-pass', value: pctStr(pctWein) })

  const commentary = signal === 'pos'
    ? 'Many stocks participating, not just mega-caps. Low concentration risk.'
    : signal === 'neg'
      ? 'Narrow — index move driven by a few names. Concentration risk elevated.'
      : 'Some participation; primary uptrend candidates still scarce.'

  return {
    primary: data.value ?? 'n/a',
    primarySub: 'cross-sectional spread',
    subs,
    signal,
    chip,
    commentary,
  }
}

// ─── tile renderer ──────────────────────────────────────────────────────

type Props = {
  data: ScorecardData
  regime: MarketRegimeRow
}

function buildContent(key: keyof ScorecardData, data: ScorecardData, regime: MarketRegimeRow): TileContent {
  switch (key) {
    case 'trend':         return buildTrendTile(data.trend, regime)
    case 'breadth':       return buildBreadthTile(data.breadth, regime)
    case 'momentum':      return buildMomentumTile(data.momentum, regime)
    case 'participation': return buildParticipationTile(data.participation, regime)
  }
}

function ScorecardTileCard({
  tileKey,
  tile,
  content,
}: {
  tileKey: keyof ScorecardData
  tile: ScorecardTile
  content: TileContent
}) {
  const metricDef = metric(TILE_METRIC_KEYS[tileKey])
  const sectionId = `section-${tileKey}`

  return (
    <a
      href={`#${sectionId}`}
      className={`border rounded-sm p-3 flex flex-col gap-2 ${SIGNAL_BG[content.signal]} hover:ring-2 hover:ring-accent/30 transition-all cursor-pointer no-underline`}
      data-testid={`scorecard-tile-${tileKey}`}
    >
      {/* Header — label + chip + tooltip */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          {tile.label}
        </span>
        <span className="flex items-center gap-1">
          <span className={`inline-flex items-center px-1.5 py-0.5 text-[9px] font-medium tracking-wide rounded-sm border ${CHIP_BG[content.signal]}`}>
            {content.chip}
          </span>
          {metricDef && (
            <InfoTooltip
              content={`${metricDef.definition} Formula: ${metricDef.formula}`}
            />
          )}
        </span>
      </div>

      {/* Primary value */}
      <div className="flex items-baseline gap-2 leading-none">
        <span className={`font-mono text-2xl font-semibold tabular-nums ${SIGNAL_COLOR[content.signal]}`}>
          {content.primary}
        </span>
        {content.primarySub && (
          <span className="font-sans text-[10px] text-ink-tertiary leading-tight">
            {content.primarySub}
          </span>
        )}
      </div>

      {/* Sub-metrics — small 2-col grid */}
      {content.subs.length > 0 && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-0.5">
          {content.subs.map(s => (
            <div key={s.label} className="flex items-baseline justify-between gap-1">
              <span className="font-sans text-[9px] text-ink-tertiary truncate">{s.label}</span>
              <span className="font-mono text-[10px] tabular-nums text-ink-secondary">
                {s.value}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Commentary — one-line what this means */}
      <div className="font-sans text-[10px] text-ink-tertiary leading-snug border-t border-paper-rule pt-1.5 mt-0.5">
        {content.commentary}
      </div>
    </a>
  )
}

export function SignalScorecard({ data, regime }: Props) {
  const tiles: Array<{
    key: keyof ScorecardData
    tile: ScorecardTile
    content: TileContent
  }> = [
    { key: 'trend',         tile: data.trend,         content: buildContent('trend', data, regime) },
    { key: 'breadth',       tile: data.breadth,       content: buildContent('breadth', data, regime) },
    { key: 'momentum',      tile: data.momentum,      content: buildContent('momentum', data, regime) },
    { key: 'participation', tile: data.participation, content: buildContent('participation', data, regime) },
  ]

  return (
    <div className="px-6 py-4 border-b border-paper-rule">
      <div className="mb-3">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          Bottom-Up Signal Scorecard
        </div>
        <div className="font-sans text-[10px] text-ink-tertiary/60 mt-0.5">
          Built from individual stock states — the engine&apos;s own breadth read.
          Click any tile to jump to the detail section.
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map(({ key, tile, content }) => (
          <ScorecardTileCard key={key} tileKey={key} tile={tile} content={content} />
        ))}
      </div>
    </div>
  )
}
