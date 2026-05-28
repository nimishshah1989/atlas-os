'use client'
// frontend/src/components/v6/india-pulse/MacroCards.tsx
//
// Section 7 — Macro context: 8 cards with sparklines + narrative ribbon.
// Client component for Recharts sparklines.

import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import type { MacroCard, NarrativeRibbon } from '@/lib/queries/v6/india_pulse'
import { CHART_COLORS } from '@/lib/chart-colors'

type Props = {
  macro_cards: MacroCard[]
  narrative_ribbon: NarrativeRibbon | null
}

function fmtValue(card: MacroCard): string {
  if (card.value == null) return '—'
  const { id, value } = card
  switch (id) {
    case 'usdinr':
      return value.toFixed(2)
    case 'india_10y':
    case 'us_10y':
      return `${value.toFixed(2)}%`
    case 'real_yield':
      // value already in percentage points (e.g. 1.83 means 1.83%); do NOT *100
      return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
    case 'brent_inr':
      return `₹${Math.round(value).toLocaleString('en-IN')}`
    case 'fii_flow_1m':
    case 'dii_flow_1m': {
      const abs = Math.abs(value)
      const prefix = value < 0 ? '−₹' : '+₹'
      return `${prefix}${Math.round(abs).toLocaleString('en-IN')} cr`
    }
    case 'dxy':
      return value.toFixed(1)
    default:
      return value.toFixed(2)
  }
}

function fmtDelta(card: MacroCard): string {
  const { id, ret_1d } = card
  if (ret_1d == null) return ''

  switch (id) {
    case 'usdinr':
      return `${ret_1d >= 0 ? '+' : ''}${ret_1d.toFixed(2)} today`
    case 'india_10y':
    case 'us_10y': {
      // ret_1d is yield change in percentage POINTS (e.g. 0.20 = 20 bps).
      // 1pp = 100 bps; do NOT multiply by 10000.
      const bps = Math.round(ret_1d * 100)
      return `${bps >= 0 ? '+' : ''}${bps} bps today`
    }
    case 'brent_inr': {
      const change = ret_1d * 100
      return `${change >= 0 ? '+' : ''}${change.toFixed(1)}% today`
    }
    case 'fii_flow_1m':
    case 'dii_flow_1m': {
      const abs = Math.abs(ret_1d)
      return `${ret_1d < 0 ? '−' : '+'}₹${Math.round(abs).toLocaleString('en-IN')} cr today`
    }
    case 'dxy': {
      const change = ret_1d * 100
      return `${change >= 0 ? '+' : ''}${change.toFixed(1)}% today`
    }
    default:
      return ''
  }
}

function fmtRetM(card: MacroCard): string {
  const { id, ret_1m } = card
  if (ret_1m == null) return ''
  switch (id) {
    case 'usdinr':
    case 'brent_inr':
    case 'dxy': {
      const pct = ret_1m * 100
      return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}% 1M`
    }
    case 'india_10y':
    case 'us_10y': {
      // ret_1m is yield change in percentage POINTS (e.g. 0.20 = 20 bps).
      // 1pp = 100 bps; do NOT multiply by 10000.
      const bps = Math.round(ret_1m * 100)
      return `${bps >= 0 ? '+' : ''}${bps} bps 1M`
    }
    default:
      return ''
  }
}

function valueColor(card: MacroCard): string {
  const { id, value, ret_1m } = card
  if (value == null) return 'text-ink-primary'
  switch (id) {
    case 'usdinr':
    case 'brent_inr':
    case 'india_10y':
    case 'us_10y':
    case 'dxy':
      return ret_1m != null && ret_1m > 0 ? 'text-signal-warn' : 'text-ink-primary'
    case 'real_yield':
      return value > 0.015 ? 'text-signal-pos' : 'text-signal-warn'
    case 'fii_flow_1m':
      return value < 0 ? 'text-signal-neg' : 'text-signal-pos'
    case 'dii_flow_1m':
      return value > 0 ? 'text-signal-pos' : 'text-signal-neg'
    default:
      return 'text-ink-primary'
  }
}

function deltaColor(card: MacroCard): string {
  const { id, ret_1d } = card
  if (ret_1d == null) return 'text-ink-tertiary'
  switch (id) {
    case 'usdinr':
    case 'india_10y':
    case 'us_10y':
    case 'brent_inr':
    case 'dxy':
      return ret_1d > 0 ? 'text-signal-neg' : 'text-signal-pos'
    case 'fii_flow_1m':
      return ret_1d < 0 ? 'text-signal-neg' : 'text-signal-pos'
    case 'dii_flow_1m':
      return ret_1d > 0 ? 'text-signal-pos' : 'text-signal-neg'
    default:
      return 'text-ink-secondary'
  }
}

function macroNote(card: MacroCard): string {
  const { id, value, ret_1m } = card
  switch (id) {
    case 'usdinr':
      return ret_1m != null && ret_1m > 0
        ? 'INR weak. USD strength is a tailwind for IT, headwind for oil importers.'
        : 'INR relatively stable. No major currency pressure on imports/exports.'
    case 'india_10y':
      return ret_1m != null && ret_1m > 0
        ? 'Yields rising into weakening equity tape. P/E compression risk — historically 6-week lagged signal.'
        : 'Yields stable or declining. Bond market not signaling stress.'
    case 'brent_inr':
      return ret_1m != null && ret_1m > 0.03
        ? 'Imported-inflation risk. Twin pressure: INR weakness + USD oil bid.'
        : 'Crude prices stable. No major input-cost pressure.'
    case 'real_yield':
      return value != null && value > 0.015
        ? 'Bonds genuinely attractive vs equities. Real yield above 5-year average.'
        : 'Real yields moderate. Equity risk premium intact.'
    case 'fii_flow_1m':
      return value != null && value < 0
        ? 'Foreign capital exiting. Watch for stabilization signal.'
        : 'Foreign investors buying. Positive flow backdrop for equities.'
    case 'dii_flow_1m':
      return value != null && value > 0
        ? 'Domestic buying absorbing selling pressure. SIP-driven persistent flow.'
        : 'Domestic institutions reducing exposure.'
    case 'us_10y':
      return ret_1m != null && ret_1m > 0
        ? 'Global rates higher. EM risk premium under pressure. FII outflow is the visible symptom.'
        : 'US yields stable. EM allocation risk neutral.'
    case 'dxy':
      return ret_1m != null && ret_1m > 0.01
        ? 'Dollar bid globally. DXY-up coincides with EM-equity-down 70% of the time over 1M windows.'
        : 'Dollar neutral. No major headwind for EM from currency.'
    default:
      return ''
  }
}

type SparkTooltipProps = {
  active?: boolean
  payload?: { value: unknown }[]
}

function SparkTooltip({ active, payload }: SparkTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-paper border border-paper-rule rounded-sm px-1.5 py-1 shadow-sm text-[10px] font-mono">
      {payload[0]?.value != null ? (payload[0].value as number).toFixed(4) : '—'}
    </div>
  )
}

function MacroCardItem({ card }: { card: MacroCard }) {
  const sparkData = (card.sparkline_30d ?? [])
    .filter(p => p.v != null)
    .map(p => ({ v: p.v }))

  const sparkColor = deltaColor(card) === 'text-signal-neg' ? CHART_COLORS.rsWeak
    : deltaColor(card) === 'text-signal-warn' ? CHART_COLORS.rsConsolidating
    : CHART_COLORS.rsLeader

  return (
    <div className="bg-paper border border-paper-rule rounded-sm p-4">
      <div className="text-[10px] uppercase tracking-[0.15em] text-ink-tertiary font-semibold mb-1">
        {card.label}
      </div>
      <div className={`font-mono text-[24px] font-medium leading-tight ${valueColor(card)}`}>
        {fmtValue(card)}
      </div>
      {(fmtDelta(card) || fmtRetM(card)) && (
        <div className={`font-mono text-[11px] font-medium mt-0.5 ${deltaColor(card)}`}>
          {[fmtDelta(card), fmtRetM(card)].filter(Boolean).join(' · ')}
        </div>
      )}

      {/* Sparkline */}
      {sparkData.length > 1 ? (
        <div className="w-full h-7 mt-2 mb-1.5">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkData}>
              <Line
                type="monotone"
                dataKey="v"
                stroke={sparkColor}
                strokeWidth={1.5}
                dot={false}
              />
              <Tooltip content={<SparkTooltip />} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-7 mt-2 mb-1.5 bg-paper-deep rounded-sm opacity-50" />
      )}

      <div className="text-[11px] text-ink-tertiary leading-[1.5] pt-1.5 border-t border-paper-rule">
        {macroNote(card) || '—'}
      </div>
    </div>
  )
}

export function MacroCards({ macro_cards, narrative_ribbon }: Props) {
  if (macro_cards.length === 0) {
    return (
      <div className="text-sm text-ink-tertiary py-4">
        No macro data available.
      </div>
    )
  }

  const india10y = narrative_ribbon?.india_10y_yield
  const realYield = narrative_ribbon?.real_yield
  const fiiFlow = narrative_ribbon?.fii_flow_1m_cr

  return (
    <>
      <div className="grid grid-cols-4 gap-3">
        {macro_cards.map(card => (
          <MacroCardItem key={card.id} card={card} />
        ))}
      </div>

      {/* Narrative ribbon */}
      {narrative_ribbon && (
        <div className="mt-4 bg-paper border border-paper-rule border-l-[3px] border-l-signal-info rounded-sm p-[18px_22px]">
          <div className="text-[10px] uppercase tracking-[0.18em] text-signal-info font-bold mb-2">
            Bond vs equity · the trade behind the trade
          </div>
          <div className="text-[13.5px] text-ink-secondary leading-[1.55]">
            {india10y != null && realYield != null ? (
              <>
                India 10Y at{' '}
                <strong className="text-ink-primary">{india10y.toFixed(2)}%</strong>{' '}
                with real yield at{' '}
                <strong className={realYield > 1.5 ? 'text-signal-pos' : 'text-ink-primary'}>
                  {realYield >= 0 ? '+' : ''}{realYield.toFixed(2)}%
                </strong>
                {realYield > 1.5
                  ? ' — bonds offer genuine risk-adjusted value relative to equities. '
                  : '. '
                }
                {fiiFlow != null && fiiFlow < 0 && (
                  <>
                    Coupled with FII outflows of{' '}
                    <strong className="text-ink-primary">
                      ₹{Math.abs(Math.round(fiiFlow)).toLocaleString('en-IN')} cr
                    </strong>
                    , the macro signals a{' '}
                    <strong className="text-ink-primary">quality-rotation regime</strong>
                    {' '}— leadership migrating to large-cap and defensive assets.
                  </>
                )}
                {fiiFlow != null && fiiFlow >= 0 && (
                  <>
                    With FII inflows of{' '}
                    <strong className="text-ink-primary">
                      ₹{Math.round(fiiFlow).toLocaleString('en-IN')} cr
                    </strong>
                    , foreign capital is supporting equities.
                  </>
                )}
              </>
            ) : (
              'Macro context data unavailable for narrative computation.'
            )}
          </div>
        </div>
      )}
    </>
  )
}
