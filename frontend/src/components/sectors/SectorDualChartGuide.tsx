'use client'
import type { SectorDecision } from '@/lib/sectors-decision'
import type { SectorSnapshot } from '@/lib/queries/sectors'

type SectorWithDecision = SectorSnapshot & { decision: SectorDecision }

type Props = {
  sectors: SectorWithDecision[]
}

const COMBOS = [
  {
    matrix:  'Leaders',
    rrg:     'Leading',
    signal:  'Confirmed strength',
    color:   '#22c55e',
    bgColor: '#f0fdf4',
    detail:  'RS outperformance + broad participation + accelerating momentum. All three signals agree.',
    action:  'Core overweight — size up on dips, not on strength.',
  },
  {
    matrix:  'Narrowing',
    rrg:     'Weakening',
    signal:  'Fragile leadership',
    color:   '#f59e0b',
    bgColor: '#fffbeb',
    detail:  'Price RS positive but fewer stocks participating; momentum now fading.',
    action:  'Trim. Breadth divergence resolves to the downside.',
  },
  {
    matrix:  'Recovering',
    rrg:     'Improving',
    signal:  'Early rotation',
    color:   '#14b8a6',
    bgColor: '#f0fdfa',
    detail:  'Breadth recovering before RS confirms. Momentum turning positive from a lagging base.',
    action:  'Scale in with tight stop. Confirm: cross into Leaders + Leading.',
  },
  {
    matrix:  'Laggards',
    rrg:     'Lagging',
    signal:  'Confirmed avoid',
    color:   '#ef4444',
    bgColor: '#fef2f2',
    detail:  'Underperforming on RS, weak breadth, and decelerating. Double negative.',
    action:  'No new exposure. Rotate to confirmed Leaders.',
  },
]

function matrixQuadrant(rs: number, participation: number): string {
  const right = rs > 0
  const top   = participation > 0.5
  if (right && top)  return 'Leaders'
  if (!right && top) return 'Recovering'
  if (right && !top) return 'Narrowing'
  return 'Laggards'
}

function rrgQuadrant(rs: number, meanRS: number, momentum: number): string {
  const right = (rs - meanRS) > 0
  const top   = momentum > 0
  if (right && top)  return 'Leading'
  if (right && !top) return 'Weakening'
  if (!right && top) return 'Improving'
  return 'Lagging'
}

export function SectorDualChartGuide({ sectors }: Props) {
  if (sectors.length === 0) return null

  const rsValues = sectors
    .map(s => parseFloat(s.bottomup_rs_3m_nifty500 ?? 'NaN'))
    .filter(v => !isNaN(v))
  const meanRS = rsValues.length > 0 ? rsValues.reduce((a, b) => a + b, 0) / rsValues.length : 0

  const examples: Array<{ sector: string; matrix: string; rrg: string; action: string }> = []
  const usedCombos = new Set<string>()

  for (const s of sectors) {
    const rs            = parseFloat(s.bottomup_rs_3m_nifty500 ?? 'NaN')
    const participation = parseFloat(s.participation_50 ?? 'NaN')
    const momentum      = parseFloat(s.rs_momentum ?? 'NaN')
    if (isNaN(rs) || isNaN(participation) || isNaN(momentum)) continue

    const mq  = matrixQuadrant(rs, participation)
    const rq  = rrgQuadrant(rs, meanRS, momentum)
    const key = `${mq}:${rq}`
    if (usedCombos.has(key)) continue

    const combo = COMBOS.find(c => c.matrix === mq && c.rrg === rq)
    if (!combo) continue

    usedCombos.add(key)
    examples.push({ sector: s.sector_name, matrix: mq, rrg: rq, action: combo.action })
    if (examples.length >= 3) break
  }

  return (
    <div className="px-6 py-5 border-b border-paper-rule bg-paper-rule/5">
      <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
        Reading Both Charts Together
      </h2>
      <p className="font-sans text-[11px] text-ink-tertiary mb-4 max-w-2xl leading-relaxed">
        The Positioning Matrix (breadth vs RS) and the RRG (momentum direction) measure different dimensions of the same rotation. Cross-referencing them filters out false signals — a sector reads as strong only when both agree.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-4">
        {COMBOS.map(c => (
          <div
            key={c.signal}
            className="rounded-sm border border-paper-rule p-3"
            style={{ background: c.bgColor }}
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <span
                className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: c.color }}
              />
              <span className="font-sans text-[10px] font-semibold uppercase tracking-wider" style={{ color: c.color }}>
                {c.signal}
              </span>
            </div>
            <div className="font-sans text-[10px] text-ink-tertiary mb-1.5">
              Matrix: <span className="font-medium text-ink-secondary">{c.matrix}</span>
              {' · '}
              RRG: <span className="font-medium text-ink-secondary">{c.rrg}</span>
            </div>
            <p className="font-sans text-[11px] text-ink-secondary leading-relaxed mb-1.5">{c.detail}</p>
            <p className="font-sans text-[11px] font-medium text-ink-primary leading-relaxed">{c.action}</p>
          </div>
        ))}
      </div>

      {examples.length > 0 && (
        <div className="border-t border-paper-rule pt-3">
          <div className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary mb-2">
            Today&apos;s examples
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-1">
            {examples.map(ex => (
              <span key={ex.sector} className="font-sans text-[11px] text-ink-secondary">
                <span className="font-medium text-ink-primary">{ex.sector}</span>
                {' '}({ex.matrix} + {ex.rrg}) →{' '}
                <span className="italic">{ex.action}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
